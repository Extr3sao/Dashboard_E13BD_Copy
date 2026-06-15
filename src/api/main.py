import os
import sys
import json
import datetime
import io
import logging
import os
import csv
import html
import glob
import re
import shutil
import copy
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, List, Optional, Dict
import pandas as pd
import yaml
from xhtml2pdf import pisa

# Afegim el directori arrel al path per poder importar els nostres mÃ²duls
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.config_loader import ConfigLoader
from src.core.db_manager import OracleDBManager
from src.core.ai_assistant import AIAssistant
from src.core.openrouter_client import OpenRouterClient, OpenRouterSettings
from src.analytics.queries_oracle import OracleQueries
from src.analytics.scoring_engine import ScoringEngine
from src.core.internal_db import InternalDBManager
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_isoformat, utc_now
from src.api.audit_engine import AuditEngine
from src.api.automation_service import AutomationService, SEVERITY_OPTIONS, compute_next_run
from src.api.post_crq_audit import (
    _criticality_label,
    _resolve_check_criticality,
    build_post_crq_markdown_report,
    build_post_crq_pdf_report,
    is_post_crq_audit_data,
    parse_post_crq_checks,
    run_post_crq_audit,
)
from src.api.post_crq_delivery_reports import (
    build_post_crq_general_artifact,
    build_post_crq_provider_artifact,
    build_post_crq_zip_bundle,
)
from src.api.post_crq_lot_status import normalize_distribution_job_config
from src.api.post_crq_experimental_pdf import build_post_crq_experimental_pdf, filter_post_crq_report_for_lot
from src.api.post_crq_scheduler import classify_check_category, resolve_scheduler_config, timeout_for_category
from src.api.post_crq_operational_docs import (
    list_post_crq_operational_document_history,
    list_post_crq_operational_documents,
    update_post_crq_operational_document,
)
from src.api.master_lot_backfill import apply_master_lot_backfill, build_master_lot_backfill_preview
from src.api.automation_analytics_pdf import build_automation_analytics_monthly_pdf
from src.api.report_builder import (
    build_standard_markdown,
    build_standard_pdf)
from src.core.automation_store import AutomationStore
from src.api.checks_admin_router import router as checks_admin_router


SCHEMA_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_$#]*$")
logger = logging.getLogger(__name__)

# Managers globals
config_loader = ConfigLoader()
internal_db = InternalDBManager(resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db"))
automation_store = AutomationStore(resolve_sqlite_path("AUTOMATION_DB_PATH", "automation.db"))
scoring_engine = ScoringEngine()
automation_service = AutomationService(automation_store, config_loader)


@asynccontextmanager
async def lifespan(_: FastAPI):
    automation_service.start()
    try:
        yield
    finally:
        automation_service.stop()


app = FastAPI(title="Oracle Audit API", version="4.6", lifespan=lifespan)
logger.info("Starting Oracle Audit API v4.6 (Query Management Module Active)")
app.include_router(checks_admin_router)

# Configurar CORS per permetre al frontend de React (Vite) connectar-se
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:8011",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
class FrameOptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        if "content-security-policy" in response.headers:
            del response.headers["content-security-policy"]
        return response

app.add_middleware(FrameOptionsMiddleware)


def _resolve_profile_key(profile_value: Optional[str], profiles: Dict) -> Optional[str]:
    requested = profile_value or config_loader.get_env_var("DEFAULT_PROFILE")
    return config_loader.resolve_profile_name(requested, profiles)


def _report_timestamp_slug() -> str:
    return utc_now().strftime("%Y%m%d_%H%M%S")


def _stream_attachment(
    content: bytes | str | io.BytesIO,
    media_type: str,
    filename: str,
    *,
    extra_headers: Optional[Dict[str, str]] | None = None,
) -> StreamingResponse:
    if isinstance(content, str):
        payload = io.BytesIO(content.encode("utf-8"))
    elif isinstance(content, bytes):
        payload = io.BytesIO(content)
    else:
        payload = content
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        payload,
        media_type=media_type,
        headers=headers,
    )


def _raise_internal_http_error(stage: str, exc: Exception) -> None:
    logger.exception("Error intern a %s", stage)
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_with_internal_http_error(stage: str, operation):
    try:
        return operation()
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_http_error(stage, exc)


async def _run_with_oracle_profile(stage: str, profile_value: Optional[str], operation, *, require_profile: bool = True):
    dbm = None
    try:
        profiles = config_loader.load_connections()
        selected_profile = _resolve_profile_key(profile_value, profiles)
        if require_profile and not selected_profile:
            raise HTTPException(status_code=404, detail="Perfil no trobat")
        if selected_profile and selected_profile in profiles:
            dbm = OracleDBManager(profiles[selected_profile])
        return await operation(selected_profile, dbm)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_http_error(stage, exc)
    finally:
        if dbm:
            dbm.close()


def _read_repo_text_file(filename: str, not_found_detail: str) -> Dict[str, str]:
    doc_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", filename))
    if not os.path.exists(doc_path):
        raise HTTPException(status_code=404, detail=not_found_detail)
    try:
        with open(doc_path, "r", encoding="utf-8") as handle:
            return {"content": handle.read()}
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_http_error(f"read_repo_text_file:{filename}", exc)


def _list_openrouter_models_or_fallback(client: OpenRouterClient) -> List[str]:
    try:
        models = client.list_models()
        return sorted(
            {
                str(model.get("id") or "").strip()
                for model in models
                if client._is_free_model(model)
            }
        )
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        logger.warning("No s'ha pogut obtenir la llista de models OpenRouter; s'usa el fallback", exc_info=exc)
        return ["openrouter/free"]


def _build_oracle_manager_or_none(profile_name: Optional[str], profiles: Dict[str, Any]) -> Optional[OracleDBManager]:
    if not profile_name or profile_name not in profiles:
        return None
    try:
        return OracleDBManager(profiles[profile_name])
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        logger.warning("No s'ha pogut connectar a Oracle %s", profile_name, exc_info=exc)
        return None


def _resolve_post_crq_report_payload(payload: Dict) -> tuple[str, Dict[str, Any], bool]:
    report_data = payload.get("report_data")
    if is_post_crq_audit_data(report_data) and (report_data.get("report_model") or report_data.get("results_by_check")):
        cached_profile = (
            (report_data.get("context") or {}).get("profile")
            or ((report_data.get("report_model") or {}).get("execution_parameters") or {}).get("profile")
        )
        selected_profile = str(payload.get("profile") or cached_profile or "").strip()
        if not selected_profile:
            raise HTTPException(status_code=400, detail="Cal informar el perfil per generar el report Post-CRQ.")
        return selected_profile, copy.deepcopy(report_data), True

    profile = payload.get("profile")
    profiles = config_loader.load_connections()
    selected_profile = _resolve_profile_key(profile, profiles)
    if not selected_profile:
        raise HTTPException(status_code=404, detail="Perfil no trobat")

    dbm = OracleDBManager(profiles[selected_profile])
    try:
        report = run_post_crq_audit(
            db_manager=dbm,
            selected_checks=payload.get("selected_checks") or [],
            schemas=payload.get("schemas") or [],
            time_filter=payload.get("time_filter") or {},
            profile=selected_profile,
            criticality_overrides=payload.get("criticality_overrides") or {},
            scheduler_options=payload.get("scheduler_options") or {},
        )
    finally:
        dbm.close()

    return selected_profile, report, False


def _normalize_post_crq_criticality_overrides(raw_overrides: Any) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    allowed = {"CRITIC", "MITJA", "BAIX"}
    for key, value in (raw_overrides or {}).items():
        check_id = str(key or "").strip().upper()
        override = str(value or "").strip().upper()
        if check_id and override in allowed:
            normalized[check_id] = override
    return normalized


def _normalize_post_crq_scheduler_options(raw_options: Any) -> Dict[str, Any]:
    source = raw_options or {}

    def _as_int(name: str) -> Optional[int]:
        value = source.get(name)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Valor no valid per {name}") from None

    normalized: Dict[str, Any] = {}
    for key in (
        "max_concurrency",
        "max_concurrency_upper_bound",
        "max_heavy_concurrency",
        "max_medium_concurrency",
        "max_light_concurrency",
        "max_retries",
    ):
        value = _as_int(key)
        if value is not None:
            normalized[key] = value
    if "enable_auto_throttle" in source:
        normalized["enable_auto_throttle"] = bool(source.get("enable_auto_throttle"))
    return normalized


def _normalize_post_crq_job_config(payload: Dict) -> Dict[str, Any]:
    base_config = payload.get("job_config") or {}
    return {
        **base_config,
        "criticality_overrides": _normalize_post_crq_criticality_overrides(
            payload.get("criticality_overrides")
            if "criticality_overrides" in payload
            else base_config.get("criticality_overrides")
        ),
        "scheduler_options": _normalize_post_crq_scheduler_options(
            payload.get("scheduler_options")
            if "scheduler_options" in payload
            else base_config.get("scheduler_options")
        ),
    }


def _normalize_automation_job_payload(payload: Dict) -> Dict:
    profiles = config_loader.load_connections()
    selected_profile = _resolve_profile_key(payload.get("profile"), profiles)
    if not selected_profile:
        raise HTTPException(status_code=404, detail="Perfil no trobat")

    audit_type = (payload.get("audit_type") or "").strip().lower()
    if audit_type not in {"deep_scan", "obsolets", "post_crq", "post_crq_distribution"}:
        raise HTTPException(status_code=400, detail="Tipus d'auditoria no valid")

    schedule_type = (payload.get("schedule_type") or "once").strip().lower()
    if schedule_type not in {"once", "daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="Recurrencia no valida")

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Cal indicar un nom per al job")

    schemas = [str(item).strip().upper() for item in (payload.get("schemas") or []) if str(item).strip()]
    checks = [str(item).strip() for item in (payload.get("checks") or payload.get("selected_checks") or []) if str(item).strip()]
    schedule_config = payload.get("schedule_config") or {}
    next_run_at = compute_next_run(schedule_type, schedule_config)
    if not schedule_config.get("start_at"):
        raise HTTPException(status_code=400, detail="Cal indicar data i hora inicial")

    delivery_targets = payload.get("delivery_targets") or []
    severity_rules = payload.get("severity_rules") or []

    for rule in severity_rules:
        severity = (rule.get("severity") or "").strip().upper()
        if severity not in SEVERITY_OPTIONS:
            raise HTTPException(status_code=400, detail=f"Severitat no valida: {severity}")

    default_report_format = "pdf" if audit_type == "post_crq_distribution" else "markdown"
    report_format = (payload.get("report_format") or default_report_format).lower()
    if report_format not in {"markdown", "pdf"}:
        raise HTTPException(status_code=400, detail="Format de report no valid")
    if audit_type == "post_crq_distribution":
        report_format = "pdf"
        job_config = {
            **normalize_distribution_job_config(payload.get("job_config") or {}),
            **_normalize_post_crq_job_config(payload),
        }
        if job_config["lot_scope"]["mode"] == "selected" and not job_config["lot_scope"]["selected_lots"]:
            raise HTTPException(status_code=400, detail="Cal indicar almenys un lot quan l ambit es manual")
        if not job_config["report_options"]["include_summary"] and not job_config["report_options"]["include_lot_reports"]:
            raise HTTPException(status_code=400, detail="Cal generar almenys un tipus de report per al job")
    elif audit_type == "post_crq":
        job_config = _normalize_post_crq_job_config(payload)
    else:
        job_config = payload.get("job_config") or {}

    return {
        "name": name,
        "enabled": bool(payload.get("enabled", True)),
        "audit_type": audit_type,
        "profile": selected_profile,
        "schemas": schemas,
        "checks": checks,
        "time_filter": payload.get("time_filter") or {},
        "report_format": report_format,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "job_config": job_config,
        "timeout_seconds": int(payload.get("timeout_seconds") or 300),
        "next_run_at": next_run_at,
        "last_run_at": payload.get("last_run_at"),
        "delivery_targets": delivery_targets,
        "severity_rules": severity_rules,
    }


def _normalize_delivery_routes_payload(payload: Dict) -> Dict:
    tic_summary_recipients = []
    for item in (payload.get("tic_summary_recipients") or []):
        if isinstance(item, dict):
            email = str(item.get("email") or "").strip()
            if email:
                tic_summary_recipients.append({
                    "email": email,
                    "enabled": bool(item.get("enabled", True))
                })
        else:
            email = str(item or "").strip()
            if email:
                tic_summary_recipients.append({
                    "email": email,
                    "enabled": True
                })
    providers = []
    for item in payload.get("providers") or []:
        provider_code = str(item.get("provider_code") or "").strip()
        if not provider_code:
            raise HTTPException(status_code=400, detail="Cada ruta de proveidor ha d'informar provider_code")
        providers.append(
            {
                "provider_code": provider_code,
                "label": str(item.get("label") or provider_code).strip() or provider_code,
                "emails": [
                    str(email).strip()
                    for email in (item.get("emails") or [])
                    if str(email).strip()
                ],
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return {
        "tic_summary_recipients": tic_summary_recipients,
        "providers": providers,
    }


def _normalize_master_lots_payload(payload: Dict) -> List[Dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        code = str(item.get("code") or "").strip().upper()
        if not code:
            raise HTTPException(status_code=400, detail="Cada lot ha d'informar code")
        normalized.append(
            {
                "code": code,
                "label": str(item.get("label") or code).strip() or code,
                "description": str(item.get("description") or "").strip(),
                "enabled": bool(item.get("enabled", True)),
                "metadata": item.get("metadata") or {},
            }
        )
    return normalized


def _normalize_lot_routes_payload(payload: Dict) -> List[Dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        lot_code = str(item.get("lot_code") or item.get("provider_code") or "").strip().upper()
        if not lot_code:
            raise HTTPException(status_code=400, detail="Cada ruta ha d'informar lot_code")
        normalized.append(
            {
                "lot_code": lot_code,
                "audience": str(item.get("audience") or "provider").strip().lower(),
                "label": str(item.get("label") or lot_code).strip() or lot_code,
                "emails": [str(email).strip() for email in (item.get("emails") or []) if str(email).strip()],
                "enabled": bool(item.get("enabled", True)),
                "source": str(item.get("source") or "automation").strip() or "automation",
            }
        )
    return normalized


def _normalize_delivery_templates_payload(payload: Dict) -> List[Dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        template_key = str(item.get("template_key") or "").strip()
        if not template_key:
            raise HTTPException(status_code=400, detail="Cada plantilla ha d'informar template_key")
        normalized.append(
            {
                "template_key": template_key,
                "audience": str(item.get("audience") or "provider").strip().lower(),
                "subject_template": str(item.get("subject_template") or "").strip(),
                "body_template": str(item.get("body_template") or "").strip(),
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return normalized


def _normalize_schema_lots_payload(payload: Dict) -> List[Dict[str, str]]:
    items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
    normalized: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in items or []:
        schema_name = str(item.get("schema_name") or "").strip().upper()
        lot_name = str(item.get("lot_name") or "").strip().upper()
        if not schema_name:
            raise HTTPException(status_code=400, detail="Cada mapping ha d'informar schema_name")
        if not SCHEMA_NAME_PATTERN.fullmatch(schema_name):
            raise HTTPException(status_code=400, detail=f"Format de schema_name no valid: {schema_name}")
        if schema_name in seen:
            raise HTTPException(status_code=400, detail=f"Schema duplicat al mapping: {schema_name}")
        normalized.append({"schema_name": schema_name, "lot_name": lot_name or "SENSE LOT"})
        seen.add(schema_name)
    return normalized


def _change_context_from_payload(payload: Dict) -> Dict[str, Any]:
    return {
        "actor": str(payload.get("actor") or "").strip() or None,
        "reason": str(payload.get("reason") or "").strip() or None,
    }


def _delete_report_artifacts(report_paths: List[str]) -> Dict[str, int]:
    deleted_files = 0
    deleted_dirs = 0
    for raw_path in report_paths or []:
        path = str(raw_path or "").strip()
        if not path:
            continue
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted_files += 1
            except OSError:
                pass
        artifacts_dir = f"{os.path.splitext(path)[0]}_artifacts"
        if os.path.isdir(artifacts_dir):
            try:
                shutil.rmtree(artifacts_dir)
                deleted_dirs += 1
            except OSError:
                pass
    return {
        "deleted_report_files": deleted_files,
        "deleted_report_dirs": deleted_dirs,
    }

@app.get("/api/profiles")
async def get_profiles():
    """Retorna la llista de connexions Oracle configurades."""
    def operation():
        profiles = config_loader.load_connections()
        default = config_loader.get_env_var("DEFAULT_PROFILE")
        return {"profiles": list(profiles.keys()), "default": default}

    return _run_with_internal_http_error("get_profiles", operation)


@app.post("/api/audit")
async def run_audit(schemas: List[str] = Body(...), profile: Optional[str] = None):
    """Executa l'auditoria transparent sobre els esquemes seleccionats."""
    async def operation(_selected_profile, dbm):
        query = OracleQueries.get_summary_query(schemas)
        data, cols = dbm.execute_query(query)

        if not data:
            return {"results": [], "summary": "No s'han trobat dades."}

        # Aplicar Scoring
        df = pd.DataFrame(data, columns=cols)
        results = []
        for _, row in df.iterrows():
            results.append(row.to_dict() | scoring_engine.classify_schema(row))

        return {"results": results, "count": len(results)}

    return await _run_with_oracle_profile("run_audit", profile, operation)

@app.get("/api/knowledge")
async def get_knowledge(search: Optional[str] = None):
    """Cerca al repositori de coneixement intern."""
    def operation():
        queries = internal_db.get_queries()
        if search:
            needle = search.lower()
            queries = [
                q
                for q in queries
                if needle in str(q[1] or "").lower() or needle in str(q[2] or "").lower()
            ]

        return [
            {"id": q[0], "sql": q[1], "explanation": q[2], "source": q[3], "date": q[4]}
            for q in queries
        ]

    return _run_with_internal_http_error("get_knowledge", operation)


@app.post("/api/ai/chat")
async def ai_chat(query: str = Body(...), context: Optional[str] = Body(None), model: Optional[str] = Body(None)):
    """Interaccio amb l'assistent IA."""
    def operation():
        current_model = model or config_loader.get_env_var("AI_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
        assistant = AIAssistant(model_name=current_model)
        prompt = query if not context else f"Context addicional:\n{context}\n\nConsulta:\n{query}"
        response = assistant.generate_response(prompt)
        return {"response": response}

    return _run_with_internal_http_error("ai_chat", operation)


@app.post("/api/queries/save")
async def save_query(sql: str = Body(...), tags: List[str] = Body([]), model: str = Body(None)):
    """Analitza amb IA i guarda una consulta a la BBDD interna."""
    def operation():
        current_model = model or config_loader.get_env_var("AI_MODEL", "google/gemini-2.0-flash-exp:free")
        assistant = AIAssistant(model_name=current_model)
        explanation = assistant.generate_response(
            "Explica breument aquesta consulta SQL Oracle i detecta riscos principals en 2-3 frases.\n\n"
            f"{sql}"
        )
        internal_db.add_query(sql, explanation=explanation, source="USER", tags=tags)
        return {"status": "success", "explanation": explanation}

    return _run_with_internal_http_error("save_query", operation)


@app.get("/api/config")
async def get_config():
    """Retorna la configuracio actual d'IA de forma dinamica."""
    try:
        client = OpenRouterClient(settings=OpenRouterSettings.from_config(config_loader), config=config_loader)
        final_list = _list_openrouter_models_or_fallback(client)
        selected_model, _ = client.select_model()
        if "openrouter/free" not in final_list:
            final_list.append("openrouter/free")

        return {
            "current_model": config_loader.get_env_var("OPENROUTER_MODEL") or config_loader.get_env_var("AI_MODEL") or selected_model,
            "available_models": final_list,
        }
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Error a get_config; s'usa configuracio fallback", exc_info=exc)
        return {
            "current_model": config_loader.get_env_var("OPENROUTER_MODEL") or config_loader.get_env_var("AI_MODEL") or "openrouter/free",
            "available_models": ["openrouter/free"],
        }


@app.post("/api/config/openrouter")
async def update_openrouter_key(key: str = Body(..., embed=True)):
    """Actualitza la clau d'OpenRouter al .env."""
    if not key or not key.strip():
        raise HTTPException(status_code=400, detail="La clau no pot estar buida")
    if config_loader.save_env_var("OPENROUTER_API_KEY", key):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Error desant la clau")

@app.get("/api/config/openrouter")
async def get_openrouter_key():
    """Retorna si hi ha una clau configurada (emmascarada)."""
    key = config_loader.get_env_var("OPENROUTER_API_KEY", "")
    if key:
        return {"configured": True, "masked": f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"}
    return {"configured": False}

@app.get("/api/audit/deep-scan")
async def deep_scan_alt(username: str = "SYSTEM", profile: Optional[str] = None):
    """Deep scan usant query params per a mÃ xima compatibilitat."""
    return await deep_scan_handler(username, profile)

@app.get("/api/audit/deep-scan/{username:path}")
async def deep_scan_legacy(username: str, profile: Optional[str] = None):
    """Mantenim la ruta de path per si el frontend no s'ha actualitzat."""
    return await deep_scan_handler(username, profile)

async def deep_scan_handler(username: str, profile: Optional[str]):
    """Realitza una analisi profunda d'un o mes esquemes."""
    import urllib.parse
    import re

    decoded_username = urllib.parse.unquote(username)
    logger.debug("Bulk Deep Scan sollicitat per %s (perfil=%s)", decoded_username, profile)

    cleaned = decoded_username.replace("'", "").replace('"', "")
    raw_list = re.split(r'[;,\s]+', cleaned)
    clean_schemas = [s.strip().upper() for s in raw_list if s.strip()]

    if not clean_schemas or (len(clean_schemas) == 1 and clean_schemas[0] == ""):
        clean_schemas = ["SYSTEM"]

    dbm = None
    profiles = config_loader.load_connections()
    selected_profile = _resolve_profile_key(profile, profiles)

    dbm = _build_oracle_manager_or_none(selected_profile, profiles)

    engine = AuditEngine(dbm)
    all_results = []
    try:
        for schema in clean_schemas:
            logger.debug("Processant esquema %s", schema)
            try:
                result = await engine.get_deep_schema_audit(schema)
                all_results.append(result)
            except (RuntimeError, ValueError, TypeError, OSError) as exc:
                logger.exception("Error auditant l'esquema %s", schema)
                all_results.append(
                    {
                        "username": schema,
                        "error": str(exc),
                        "obsolescence_score": 0,
                        "summary": {"STATUS": "FAILED"},
                    }
                )
        return all_results
    finally:
        if dbm:
            dbm.close()


@app.post("/api/audit/dashboard-stats")
async def get_dashboard_stats(schemas: List[str] = Body(...), profile: Optional[str] = None):
    """Genera estadistiques agregades per al dashboard visual."""
    try:
        profiles = config_loader.load_connections()
        selected_profile = _resolve_profile_key(profile, profiles)

        dbm = _build_oracle_manager_or_none(selected_profile, profiles)

        engine = AuditEngine(dbm)
        all_results = []
        try:
            tasks = [engine.get_deep_schema_audit(s) for s in schemas]
            import asyncio
            all_results = await asyncio.gather(*tasks)
        finally:
            if dbm:
                dbm.close()

        stats = {
            "total_gb": 0,
            "recovered_gb": 0,
            "distribution": [0, 0, 0, 0, 0],
            "status_counts": {"CRITIC": 0, "RISC": 0, "OK": 0},
            "apex_total": 0,
            "top_candidates": [],
        }

        for res in all_results:
            score = res.get("obsolescence_score", 0)
            size = (res.get("summary") or {}).get("SIZE_GB") or 0

            stats["total_gb"] += size
            if score > 70:
                stats["recovered_gb"] += size
                stats["status_counts"]["CRITIC"] += 1
            elif score > 30:
                stats["status_counts"]["RISC"] += 1
            else:
                stats["status_counts"]["OK"] += 1

            bin_idx = min(4, score // 20)
            stats["distribution"][bin_idx] += 1

            if res.get("apex_apps"):
                stats["apex_total"] += 1

            stats["top_candidates"].append(
                {
                    "username": res["username"],
                    "score": score,
                    "size": size,
                    "priority": score * (size + 0.1),
                }
            )

        stats["top_candidates"].sort(key=lambda x: x["priority"], reverse=True)
        stats["top_candidates"] = stats["top_candidates"][:5]
        return stats
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        _raise_internal_http_error("get_dashboard_stats", exc)


@app.get("/api/docs/technical-audit")
async def get_technical_audit_docs():
    """
    Retorna el contingut del fitxer AUDITORIA_BBDD_DOC.md en format text.
    """
    return _read_repo_text_file("AUDITORIA_BBDD_DOC.md", "Fitxer de documentaci? no trobat")


@app.get("/api/docs/automation")
async def get_automation_docs():
    """
    Retorna el contingut del fitxer automatitzacions-ajuda.md en format text.
    """
    return _read_repo_text_file("automatitzacions-ajuda.md", "Fitxer de documentaci? d'automatitzacions no trobat")


@app.get("/api/docs/post-crq-operational")
async def get_post_crq_operational_docs():
    """Retorna els documents operatius editables associats al flux Post-CRQ."""
    return _run_with_internal_http_error(
        "get_post_crq_operational_docs",
        list_post_crq_operational_documents,
    )


@app.put("/api/docs/post-crq-operational/{document_id}")
async def update_post_crq_operational_docs(document_id: str, payload: Dict = Body(...)):
    """Desa un document operatiu Post-CRQ controlant conflictes per versio."""

    def operation():
        content = payload.get("content")
        expected_version = payload.get("expected_version")
        force_overwrite = bool(payload.get("force_overwrite", False))
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="El camp content ha de ser text")
        if expected_version is not None and not isinstance(expected_version, str):
            raise HTTPException(status_code=400, detail="El camp expected_version ha de ser text")
        if "force_overwrite" in payload and not isinstance(payload.get("force_overwrite"), bool):
            raise HTTPException(status_code=400, detail="El camp force_overwrite ha de ser boolea")
        return update_post_crq_operational_document(
            document_id,
            content,
            expected_version=expected_version,
            force_overwrite=force_overwrite,
        )

    return _run_with_internal_http_error("update_post_crq_operational_docs", operation)


@app.get("/api/docs/post-crq-operational/{document_id}/history")
async def get_post_crq_operational_doc_history(document_id: str, limit: int = 10):
    """Retorna l'historial recent de versions desades d'un document operatiu Post-CRQ."""

    def operation():
        return list_post_crq_operational_document_history(document_id, limit=limit)

    return _run_with_internal_http_error("get_post_crq_operational_doc_history", operation)


@app.get("/api/audit/post-crq/checks")
async def list_post_crq_checks():
    """Llista els checks disponibles definits al markdown post-CRQ."""
    def operation():
        from src.api.post_crq_audit import resolve_post_crq_markdown_path

        path = resolve_post_crq_markdown_path()
        checks = parse_post_crq_checks(path)
        enriched_checks = []
        for item in checks:
            criticality_key = _resolve_check_criticality(item.get("check_id"), default_severity=item.get("severitat"))
            query_category = classify_check_category(item.get("check_id"), item.get("sql") or "")
            scheduler_config = resolve_scheduler_config()
            enriched_checks.append(
                {
                    **item,
                    "severitat_original": item.get("severitat"),
                    "criticitat_key": criticality_key,
                    "criticitat": _criticality_label(criticality_key),
                    "configurable_criticitat": True,
                    "query_category": query_category.value,
                    "timeout_seconds": timeout_for_category(scheduler_config, query_category),
                }
            )
        return {"checks": enriched_checks, "count": len(enriched_checks), "source_file": os.path.basename(path), "source_path": path}

    return _run_with_internal_http_error("list_post_crq_checks", operation)


@app.post("/api/audit/post-crq/run")
async def run_post_crq(payload: Dict = Body(...)):
    """Executa una auditoria tecnica post-CRQ basada en checks del markdown."""
    async def operation(selected_profile, dbm):
        profile = payload.get("profile")
        schemas = payload.get("schemas") or []
        time_filter = payload.get("time_filter") or {}
        selected_checks = payload.get("selected_checks") or []
        criticality_overrides = payload.get("criticality_overrides") or {}
        scheduler_options = payload.get("scheduler_options") or {}

        report = run_post_crq_audit(
            db_manager=dbm,
            selected_checks=selected_checks,
            schemas=schemas,
            time_filter=time_filter,
            profile=selected_profile,
            criticality_overrides=criticality_overrides,
            scheduler_options=scheduler_options,
        )
        return report

    return await _run_with_oracle_profile("run_post_crq", payload.get("profile"), operation)


@app.post("/api/audit/post-crq/generate-by-lots")
async def generate_post_crq_by_lots(payload: Dict = Body(...)):
    """
    Executa l'auditoria Post-CRQ i retorna un ZIP amb el resum general i informes individuals per lot.
    """
    async def operation(selected_profile, dbm):
        schemas = payload.get("schemas") or []
        time_filter = payload.get("time_filter") or {}
        selected_checks = payload.get("selected_checks") or []
        criticality_overrides = payload.get("criticality_overrides") or {}
        scheduler_options = payload.get("scheduler_options") or {}

        # 1. Executar l'auditoria una sola vegada (Model Global)
        report = run_post_crq_audit(
            db_manager=dbm,
            selected_checks=selected_checks,
            schemas=schemas,
            time_filter=time_filter,
            profile=selected_profile,
            criticality_overrides=criticality_overrides,
            scheduler_options=scheduler_options,
        )
        
        # 2. Generar el ZIP mitjançant la nova funció
        zip_bytes = build_post_crq_zip_bundle(selected_profile, report)
        
        filename = f"auditoria_lots_{selected_profile}_{_report_timestamp_slug()}.zip"
        return _stream_attachment(zip_bytes, "application/zip", filename)

    return await _run_with_oracle_profile("download_post_crq_reports_zip", payload.get("profile"), operation)


@app.post("/api/audit/post-crq/reports")
async def generate_post_crq_reports(payload: Dict = Body(...)):
    def operation():
        variant = (payload.get("variant") or "general").strip().lower()
        summary_version = (payload.get("summary_version") or "v1").strip().lower()
        provider_code = (payload.get("provider_code") or "").strip()

        if variant not in {"general", "provider", "all"}:
            raise HTTPException(status_code=400, detail="El camp variant ha de ser 'general', 'provider' o 'all'.")
        if variant == "provider" and not provider_code:
            raise HTTPException(status_code=400, detail="Cal informar provider_code per generar el report per proveidor.")
        if summary_version not in {"v1", "v2", "experimental"}:
            raise HTTPException(status_code=400, detail="El camp summary_version ha de ser 'v1' o 'v2'.")
        if variant != "general" and summary_version != "v1":
            raise HTTPException(status_code=400, detail="La versió experimental només està disponible per al resum general.")

        selected_profile, report, _used_cached_report = _resolve_post_crq_report_payload(payload)

        timestamp = _report_timestamp_slug()
        if variant == "general":
            if summary_version in {"v2", "experimental"}:
                pdf_bytes = build_post_crq_experimental_pdf(selected_profile, report)
                filename = f"report_auditoria_post_crq_general_{selected_profile}_{timestamp}_v2.pdf"
                return _stream_attachment(
                    pdf_bytes,
                    "application/pdf",
                    filename,
                    extra_headers={"X-Post-CRQ-Summary-Version": "v2"},
                )

            artifact = build_post_crq_general_artifact(selected_profile, report)
            filename = f"report_auditoria_post_crq_general_{selected_profile}_{timestamp}.pdf"
            return _stream_attachment(
                artifact["content"],
                "application/pdf",
                filename,
                extra_headers={"X-Post-CRQ-Summary-Version": "v1"},
            )

        if variant == "provider":
            try:
                artifact = build_post_crq_provider_artifact(selected_profile, report, provider_code)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            artifact_key = artifact["filename"].replace(".pdf", "")
            filename = f"report_auditoria_post_crq_provider_{selected_profile}_{artifact_key}_{timestamp}.pdf"
            return _stream_attachment(
                artifact["content"],
                "application/pdf",
                filename,
                extra_headers={"X-Post-CRQ-Summary-Version": "v1"},
            )

        zip_bytes = build_post_crq_zip_bundle(selected_profile, report)
        filename = f"auditoria_proveidors_{selected_profile}_{timestamp}.zip"
        return _stream_attachment(
            zip_bytes,
            "application/zip",
            filename,
            extra_headers={"X-Post-CRQ-Summary-Version": "v1"},
        )

    return _run_with_internal_http_error("generate_post_crq_reports", operation)


@app.get("/api/automation/jobs")
async def list_automation_jobs():
    return _run_with_internal_http_error("list_automation_jobs", lambda: {"items": automation_store.list_jobs()})


@app.post("/api/automation/jobs")
async def create_automation_job(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_automation_job_payload(payload)
        return automation_store.create_job(normalized)

    return _run_with_internal_http_error("create_automation_job", operation)


@app.put("/api/automation/jobs/{job_id}")
async def update_automation_job(job_id: int, payload: Dict = Body(...)):
    def operation():
        current = automation_store.get_job(job_id)
        if not current:
            raise HTTPException(status_code=404, detail="Job no trobat")
        normalized = _normalize_automation_job_payload({**current, **payload})
        updated = automation_store.update_job(job_id, normalized)
        if not updated:
            raise HTTPException(status_code=404, detail="Job no trobat")
        return updated

    return _run_with_internal_http_error("update_automation_job", operation)


@app.delete("/api/automation/jobs/{job_id}")
async def delete_automation_job(job_id: int):
    def operation():
        deleted = automation_store.delete_job(job_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Job no trobat")
        return {"status": "success"}

    return _run_with_internal_http_error("delete_automation_job", operation)


@app.post("/api/automation/jobs/{job_id}/run-now")
async def run_automation_job_now(job_id: int):
    def operation():
        if not automation_store.get_job(job_id):
            raise HTTPException(status_code=404, detail="Job no trobat")
        started = automation_service.run_job(job_id, manual=True)
        if not started:
            raise HTTPException(status_code=409, detail="El job ja s'esta executant")
        return {"status": "started", "job_id": job_id}

    return _run_with_internal_http_error("run_automation_job_now", operation)


@app.get("/api/automation/runs")
async def list_automation_runs(job_id: Optional[int] = None, limit: int = 100):
    return _run_with_internal_http_error(
        "list_automation_runs",
        lambda: {"items": automation_store.list_runs(job_id=job_id, limit=limit)},
    )


@app.get("/api/automation/runs/{run_id}")
async def get_automation_run(run_id: int):
    def operation():
        run = automation_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Execucio no trobada")
        return run

    return _run_with_internal_http_error("get_automation_run", operation)


@app.get("/api/automation/runs/{run_id}/lots")
async def list_automation_run_lots(
    run_id: int,
    status: Optional[str] = None,
    search: Optional[str] = None,
    audience: Optional[str] = None,
    delivery_result: Optional[str] = None,
):
    def operation():
        run = automation_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Execucio no trobada")
        return {
            "items": automation_store.list_run_lot_statuses(
                run_id,
                status=status,
                search=search,
                audience=audience,
                delivery_result=delivery_result,
            )
        }

    return _run_with_internal_http_error("list_automation_run_lots", operation)


@app.get("/api/automation/runs/{run_id}/lots/export.csv")
async def export_automation_run_lots_csv(
    run_id: int,
    status: Optional[str] = None,
    search: Optional[str] = None,
    audience: Optional[str] = None,
    delivery_result: Optional[str] = None,
):
    def operation():
        run = automation_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Execucio no trobada")
        rows = automation_store.list_run_lot_statuses(
            run_id,
            status=status,
            search=search,
            audience=audience,
            delivery_result=delivery_result,
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "job_id",
                "execution_id",
                "executed_at",
                "lot",
                "detection_status",
                "num_findings",
                "delivery_audience",
                "delivery_result",
                "report_generated",
                "email_sent",
                "motivo_sin_envio",
                "observaciones",
            ],
        )
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "job_id": item.get("job_id"),
                    "execution_id": item.get("execution_id"),
                    "executed_at": item.get("executed_at"),
                    "lot": item.get("lot"),
                    "detection_status": item.get("detection_status"),
                    "num_findings": item.get("num_findings"),
                    "delivery_audience": item.get("delivery_audience"),
                    "delivery_result": item.get("delivery_result"),
                    "report_generated": item.get("report_generated"),
                    "email_sent": item.get("email_sent"),
                    "motivo_sin_envio": item.get("motivo_sin_envio"),
                    "observaciones": item.get("observaciones"),
                }
            )
        filename = f"automation_run_{run_id}_lots.csv"
        return _stream_attachment(buffer.getvalue(), "text/csv; charset=utf-8", filename)

    return _run_with_internal_http_error("export_automation_run_lots_csv", operation)


@app.get("/api/automation/runs/{run_id}/report")
async def download_automation_run_report(run_id: int):
    run = automation_store.get_run(run_id)
    if not run or not run.get("report_path"):
        raise HTTPException(status_code=404, detail="Report no trobat")
    if not os.path.exists(run["report_path"]):
        raise HTTPException(status_code=404, detail="Fitxer de report no disponible")
    return FileResponse(run["report_path"], filename=os.path.basename(run["report_path"]))


@app.get("/api/automation/runs/{run_id}/report-data")
async def get_automation_run_report_data(run_id: int):
    def operation():
        run = automation_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Execucio no trobada")
        if str(run.get("audit_type") or "").strip().lower() not in {"post_crq", "post_crq_distribution"}:
            raise HTTPException(status_code=400, detail="Nomes disponible per execucions Post-CRQ")
        report_path = str(run.get("report_path") or "").strip()
        if not report_path:
            raise HTTPException(status_code=404, detail="No hi ha snapshot disponible per aquesta execucio")
        artifacts_dir = f"{os.path.splitext(report_path)[0]}_artifacts"
        report_data_path = os.path.join(artifacts_dir, "report_data.json")
        if not os.path.exists(report_data_path):
            raise HTTPException(status_code=404, detail="Snapshot report_data no disponible")
        with open(report_data_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    return _run_with_internal_http_error("get_automation_run_report_data", operation)


@app.get("/api/automation/tasks")
async def list_automation_tasks(status: Optional[str] = None, limit: int = 200):
    return _run_with_internal_http_error(
        "list_automation_tasks",
        lambda: {"items": automation_store.list_tasks(status=status, limit=limit)},
    )


@app.put("/api/automation/tasks/{task_id}")
async def update_automation_task(task_id: int, payload: Dict = Body(...)):
    def operation():
        updated = automation_store.update_task(task_id, payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Tasca no trobada")
        return updated

    return _run_with_internal_http_error("update_automation_task", operation)


@app.get("/api/automation/severity-rules")
async def list_automation_rules(scope: Optional[str] = None, job_id: Optional[int] = None):
    return _run_with_internal_http_error(
        "list_automation_rules",
        lambda: {"items": automation_store.list_severity_rules(scope=scope, job_id=job_id)},
    )


@app.post("/api/automation/severity-rules")
async def create_automation_rule(payload: Dict = Body(...)):
    def operation():
        severity = (payload.get("severity") or "").strip().upper()
        if severity not in SEVERITY_OPTIONS:
            raise HTTPException(status_code=400, detail="Severitat no valida")
        return automation_store.create_severity_rule(
            {
                "scope": payload.get("scope", "global"),
                "job_id": payload.get("job_id"),
                "severity": severity,
                "create_task": bool(payload.get("create_task", False)),
                "task_priority": payload.get("task_priority", "normal"),
                "send_email": bool(payload.get("send_email", False)),
                "attach_report": bool(payload.get("attach_report", True)),
                "recipients": payload.get("recipients") or [],
                "conditions": payload.get("conditions") or {},
                "enabled": bool(payload.get("enabled", True)),
            }
        )

    return _run_with_internal_http_error("create_automation_rule", operation)


@app.put("/api/automation/severity-rules/{rule_id}")
async def update_automation_rule(rule_id: int, payload: Dict = Body(...)):
    def operation():
        if "severity" in payload:
            severity = (payload.get("severity") or "").strip().upper()
            if severity not in SEVERITY_OPTIONS:
                raise HTTPException(status_code=400, detail="Severitat no valida")
            payload["severity"] = severity
        updated = automation_store.update_severity_rule(rule_id, payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Regla no trobada")
        return updated

    return _run_with_internal_http_error("update_automation_rule", operation)


@app.get("/api/automation/delivery-config")
async def get_automation_delivery_config():
    return _run_with_internal_http_error("get_automation_delivery_config", automation_store.get_delivery_config)


@app.put("/api/automation/delivery-config")
async def update_automation_delivery_config(payload: Dict = Body(...)):
    return _run_with_internal_http_error(
        "update_automation_delivery_config",
        lambda: automation_store.update_delivery_config(payload),
    )


@app.get("/api/automation/delivery-routes")
async def get_automation_delivery_routes():
    return _run_with_internal_http_error("get_automation_delivery_routes", automation_store.get_delivery_routes)


@app.put("/api/automation/delivery-routes")
async def update_automation_delivery_routes(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_delivery_routes_payload(payload or {})
        change_context = _change_context_from_payload(payload or {})
        before = automation_store.get_delivery_routes()
        updated = automation_store.update_delivery_routes(normalized)
        if before != updated:
            automation_store.record_change_event(
                entity_type="delivery_routes_config",
                entity_key="global",
                action="update",
                actor=change_context["actor"],
                reason=change_context["reason"],
                before=before,
                after=updated,
                context={"source": "api"},
            )
        return updated

    return _run_with_internal_http_error("update_automation_delivery_routes", operation)


@app.get("/api/automation/master-lots")
async def list_automation_master_lots(enabled_only: bool = False):
    return _run_with_internal_http_error(
        "list_automation_master_lots",
        lambda: {"items": automation_store.list_master_lots(enabled_only=enabled_only)},
    )


@app.get("/api/automation/schema-lots")
async def list_automation_schema_lots():
    return _run_with_internal_http_error(
        "list_automation_schema_lots",
        lambda: {"items": internal_db.list_schema_lots()},
    )


@app.put("/api/automation/schema-lots")
async def update_automation_schema_lots(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_schema_lots_payload(payload or {})
        change_context = _change_context_from_payload(payload or {})
        before = internal_db.list_schema_lots()
        updated = internal_db.upsert_schema_lots(normalized)
        if before != updated:
            automation_store.record_change_event(
                entity_type="schema_lot_mapping",
                entity_key="global",
                action="update",
                actor=change_context["actor"],
                reason=change_context["reason"],
                before=before,
                after=updated,
                context={"source": "api"},
            )
        return {"items": updated}

    return _run_with_internal_http_error("update_automation_schema_lots", operation)



@app.put("/api/automation/master-lots")
async def update_automation_master_lots(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_master_lots_payload(payload or {})
        change_context = _change_context_from_payload(payload or {})
        return {
            "items": automation_store.upsert_master_lots(
                normalized,
                actor=change_context["actor"],
                reason=change_context["reason"],
                context={"source": "api"},
            )
        }

    return _run_with_internal_http_error("update_automation_master_lots", operation)


@app.get("/api/automation/master-lots/backfill-runs")
async def list_automation_master_lot_backfill_runs(limit: int = 20):
    return _run_with_internal_http_error(
        "list_automation_master_lot_backfill_runs",
        lambda: {"items": automation_store.list_master_lot_backfill_runs(limit=limit)},
    )


@app.get("/api/automation/master-lots/backfill-preview")
async def preview_automation_master_lot_backfill(actor: Optional[str] = None, reason: Optional[str] = None):
    def operation():
        preview = build_master_lot_backfill_preview(
            automation_store,
            actor=(actor or "").strip() or None,
            reason=(reason or "").strip() or None,
        )
        return preview

    return _run_with_internal_http_error("preview_automation_master_lot_backfill", operation)


@app.post("/api/automation/master-lots/backfill-apply")
async def apply_automation_master_lot_backfill(payload: Dict = Body(...)):
    def operation():
        run_id = int(payload.get("run_id"))
        selected = [
            str(item).strip().upper()
            for item in (payload.get("selected_lot_codes") or [])
            if str(item).strip()
        ]
        actor = str(payload.get("actor") or "").strip() or None
        reason = str(payload.get("reason") or "").strip() or None
        return apply_master_lot_backfill(
            automation_store,
            run_id=run_id,
            selected_lot_codes=selected,
            actor=actor,
            reason=reason,
        )

    return _run_with_internal_http_error("apply_automation_master_lot_backfill", operation)


@app.get("/api/automation/lot-routes")
async def list_automation_lot_routes(audience: Optional[str] = None):
    return _run_with_internal_http_error(
        "list_automation_lot_routes",
        lambda: {"items": automation_store.list_lot_routes(audience=audience)},
    )


@app.put("/api/automation/lot-routes")
async def update_automation_lot_routes(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_lot_routes_payload(payload or {})
        change_context = _change_context_from_payload(payload or {})
        updated = automation_store.upsert_lot_routes(
            normalized,
            actor=change_context["actor"],
            reason=change_context["reason"],
            context={"source": "api"},
        )
        if any(item.get("audience") == "provider" for item in normalized):
            provider_payload = {
                "providers": [
                    {
                        "provider_code": item["lot_code"],
                        "label": item.get("label") or item["lot_code"],
                        "emails": item.get("emails") or [],
                        "enabled": bool(item.get("enabled", True)),
                    }
                    for item in updated
                    if item.get("audience") == "provider"
                ]
            }
            automation_store.update_delivery_routes(provider_payload)
        return {"items": updated}

    return _run_with_internal_http_error("update_automation_lot_routes", operation)


@app.get("/api/automation/delivery-templates")
async def list_automation_delivery_templates(audience: Optional[str] = None):
    return _run_with_internal_http_error(
        "list_automation_delivery_templates",
        lambda: {"items": automation_store.list_delivery_templates(audience=audience)},
    )


@app.put("/api/automation/delivery-templates")
async def update_automation_delivery_templates(payload: Dict = Body(...)):
    def operation():
        normalized = _normalize_delivery_templates_payload(payload or {})
        change_context = _change_context_from_payload(payload or {})
        return {
            "items": automation_store.upsert_delivery_templates(
                normalized,
                actor=change_context["actor"],
                reason=change_context["reason"],
                context={"source": "api"},
            )
        }

    return _run_with_internal_http_error("update_automation_delivery_templates", operation)


@app.get("/api/automation/change-events")
async def list_automation_change_events(entity_type: Optional[str] = None, entity_key: Optional[str] = None, limit: int = 100):
    return _run_with_internal_http_error(
        "list_automation_change_events",
        lambda: {
            "items": automation_store.list_change_events(
                entity_type=entity_type,
                entity_key=entity_key,
                limit=limit,
            )
        },
    )


@app.get("/api/automation/delivery-attempts")
async def list_automation_delivery_attempts(
    run_id: Optional[int] = None,
    lot: Optional[str] = None,
    audience: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
):
    return _run_with_internal_http_error(
        "list_automation_delivery_attempts",
        lambda: {
            "items": automation_store.list_delivery_attempts(
                run_id=run_id,
                lot=lot,
                audience=audience,
                status=status,
                limit=limit,
            )
        },
    )


@app.get("/api/automation/retry-queue")
async def list_automation_retry_queue(
    status: Optional[str] = None,
    run_id: Optional[int] = None,
    audience: Optional[str] = None,
    retry_mode: Optional[str] = None,
    due_only: bool = False,
    limit: int = 200,
):
    return _run_with_internal_http_error(
        "list_automation_retry_queue",
        lambda: {
            "items": automation_store.list_retry_queue(
                status=status,
                run_id=run_id,
                audience=audience,
                retry_mode=retry_mode,
                due_only=due_only,
                limit=limit,
            )
        },
    )


@app.get("/api/automation/maintenance/summary")
async def get_automation_maintenance_summary(retain_days: int = 30):
    return _run_with_internal_http_error(
        "get_automation_maintenance_summary",
        lambda: automation_store.get_maintenance_summary(retain_days=retain_days),
    )


@app.get("/api/automation/analytics/overview")
async def get_automation_analytics_overview(month: Optional[str] = None):
    return _run_with_internal_http_error(
        "get_automation_analytics_overview",
        lambda: automation_store.get_post_crq_analytics_overview(month=month),
    )


@app.get("/api/automation/analytics/lots")
async def list_automation_analytics_lots(month: Optional[str] = None, limit: int = 100):
    return _run_with_internal_http_error(
        "list_automation_analytics_lots",
        lambda: {"items": automation_store.list_post_crq_lot_analytics(month=month, limit=limit)},
    )


@app.get("/api/automation/analytics/schemas")
async def list_automation_analytics_schemas(month: Optional[str] = None, limit: int = 100):
    return _run_with_internal_http_error(
        "list_automation_analytics_schemas",
        lambda: {"items": automation_store.list_post_crq_schema_analytics(month=month, limit=limit)},
    )


@app.get("/api/automation/analytics/checks")
async def list_automation_analytics_checks(month: Optional[str] = None, limit: int = 100):
    return _run_with_internal_http_error(
        "list_automation_analytics_checks",
        lambda: {"items": automation_store.list_post_crq_check_analytics(month=month, limit=limit)},
    )


@app.get("/api/automation/analytics/monthly-report.pdf")
async def download_automation_analytics_monthly_pdf(month: Optional[str] = None, limit: int = 100):
    def operation():
        current_month = month or utc_now().strftime("%Y-%m")
        overview = automation_store.get_post_crq_analytics_overview(month=current_month)
        lots = automation_store.list_post_crq_lot_analytics(month=current_month, limit=limit)
        schemas = automation_store.list_post_crq_schema_analytics(month=current_month, limit=limit)
        checks = automation_store.list_post_crq_check_analytics(month=current_month, limit=limit)
        pdf_bytes = build_automation_analytics_monthly_pdf(
            month=current_month,
            overview=overview,
            lots=lots,
            schemas=schemas,
            checks=checks,
        )
        filename = f"dashboard_automatitzacions_{current_month}.pdf"
        return _stream_attachment(pdf_bytes, "application/pdf", filename)

    return _run_with_internal_http_error("download_automation_analytics_monthly_pdf", operation)


@app.post("/api/automation/maintenance/purge-history")
async def purge_automation_history(payload: Dict = Body(...)):
    def operation():
        retain_days = int(payload.get("retain_days") or 30)
        delete_reports = bool(payload.get("delete_reports", True))
        result = automation_store.purge_history(retain_days=retain_days)
        deleted_artifacts = {"deleted_report_files": 0, "deleted_report_dirs": 0}
        if delete_reports:
            deleted_artifacts = _delete_report_artifacts(result.get("report_paths") or [])
        return {
            **result,
            **deleted_artifacts,
        }

    return _run_with_internal_http_error("purge_automation_history", operation)


@app.post("/api/automation/maintenance/purge-retry-queue")
async def purge_automation_retry_queue(payload: Dict = Body(...)):
    def operation():
        statuses = payload.get("statuses") or []
        return automation_store.purge_retry_queue(statuses=statuses)

    return _run_with_internal_http_error("purge_automation_retry_queue", operation)


@app.post("/api/automation/retry-queue")
async def enqueue_automation_retry(payload: Dict = Body(...)):
    def operation():
        run_id = int(payload.get("run_id"))
        audience = str(payload.get("audience") or "provider").strip().lower()
        lot = payload.get("lot")
        requested_by = str(payload.get("requested_by") or "manual").strip() or "manual"
        return automation_service.enqueue_manual_retry(run_id=run_id, lot=lot, audience=audience, requested_by=requested_by)

    return _run_with_internal_http_error("enqueue_automation_retry", operation)


@app.post("/api/automation/retry-queue/{queue_id}/run-now")
async def run_automation_retry_now(queue_id: int):
    return _run_with_internal_http_error(
        "run_automation_retry_now",
        lambda: automation_service.process_retry_queue_item(queue_id),
    )


@app.post("/api/automation/delivery-config/test-email")
async def test_automation_email(payload: Dict = Body(...)):
    def operation():
        recipient = (payload.get("recipient") or "").strip()
        if not recipient:
            raise HTTPException(status_code=400, detail="Cal indicar un destinatari")
        if payload:
            automation_store.update_delivery_config(payload)
        return automation_service.send_test_email(recipient)

    return _run_with_internal_http_error("test_automation_email", operation)


@app.post("/api/audit/plan-execution")
async def run_plan_execution(
    schemas: List[str] = Body(...),
    profile: Optional[str] = Body(None),
    export: bool = Body(False),
):
    """Executa el pla complet Q01-Q19 i opcionalment exporta resultats a resources/."""
    async def operation(selected_profile, dbm):
        engine = AuditEngine(dbm)
        report = await engine.run_plan_audit(schemas)

        if export:
            stamp = _report_timestamp_slug()
            os.makedirs("resources", exist_ok=True)
            json_path = os.path.join("resources", f"audit_plan_{stamp}.json")
            csv_path = os.path.join("resources", f"audit_plan_summary_{stamp}.csv")

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, default=str, indent=2)

            summary_rows = []
            for item in report.get("audits", []):
                summary = item.get("summary") or {}
                summary_rows.append({
                    "username": item.get("username"),
                    "score": item.get("obsolescence_score"),
                    "result": item.get("audit_result"),
                    "size_gb": summary.get("SIZE_GB"),
                    "inbound_refs": summary.get("INBOUND_REFERENCES"),
                    "active_jobs": summary.get("ACTIVE_JOBS"),
                    "apex_apps": summary.get("APEX_APPLICATIONS"),
                    "enabled_triggers": summary.get("ENABLED_TRIGGERS"),
                })

            pd.DataFrame(summary_rows).to_csv(csv_path, index=False)
            report["exports"] = {"json": json_path, "csv": csv_path}

        return report

    return await _run_with_oracle_profile("run_plan_execution", profile, operation, require_profile=False)


@app.post("/api/queries/execute")
async def execute_query(sql: str = Body(..., embed=True), profile: Optional[str] = Body(None, embed=True)):
    """Executa una consulta SQL i retorna els resultats en format apte per a taules."""
    async def operation(_selected_profile, dbm):
        data, cols = dbm.execute_query(sql)

        if data is None:
            raise HTTPException(status_code=400, detail="Error en l'execucio de la consulta")

        results = [dict(zip(cols, row)) for row in data]
        return {"results": results, "columns": cols}

    return await _run_with_oracle_profile("execute_query", profile, operation)


@app.post("/api/db/test")
async def test_db(
    user: Optional[str] = Body(None),
    password: Optional[str] = Body(None),
    dsn: Optional[str] = Body(None),
    profile: Optional[str] = Body(None)
):
    """Prova una connexio Oracle (per dades manuals o perfil existent)."""
    dbm = None
    try:
        if profile:
            params = config_loader.get_profile(profile)
            if not params:
                return {"status": "error", "message": f"Perfil '{profile}' no trobat"}
            resolved_profile = params.get("PROFILE_NAME", profile)
        else:
            params = {"USER": user, "PASSWORD": password, "DSN": dsn}
            resolved_profile = None

        dbm = OracleDBManager(params)
        data, _ = dbm.execute_query("SELECT 'OK' FROM DUAL")

        if data and data[0][0] == 'OK':
            if resolved_profile:
                return {"status": "success", "message": f"Connexio perfil {resolved_profile} OK"}
            return {"status": "success", "message": "Connexio OK"}
        return {"status": "error", "message": "Resposta inesperada de la BBDD"}
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        logger.warning("Error provant la connexio Oracle", exc_info=exc)
        return {"status": "error", "message": str(exc)}
    finally:
        if dbm:
            dbm.close()


@app.post("/api/db/add")
async def add_db(name: str = Body(...), user: str = Body(...), password: str = Body(...), dsn: str = Body(...)):
    """Afegeix una nova connexiÃ³ permanent."""
    if config_loader.save_connection(name, user, password, dsn):
        return {"status": "success", "profile": name}
    raise HTTPException(status_code=500, detail="Error desant la connexiÃ³")

@app.post("/api/queries/import")
async def import_queries(text: str = Body(...), model: Optional[str] = Body(None)):
    """Importa consultes des de text (format .txt), les analitza amb IA i les desa."""
    def operation():
        current_model = model or config_loader.get_env_var("AI_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
        assistant = AIAssistant(model_name=current_model)

        raw_queries = [q.strip() for q in text.split(";") if q.strip()]
        imported_count = 0

        for sql in raw_queries:
            if len(sql) < 10:
                continue

            prompt = f"Explica aquesta consulta SQL en MAXIM 2 linies de text, de forma molt concisa:\n{sql}"
            explanation = assistant.generate_response(prompt)

            explanation_lines = explanation.strip().split("\n")[:2]
            final_explanation = " ".join(explanation_lines)

            internal_db.add_query(sql, explanation=final_explanation, source="IMPORT_TXT", tags=["IMPORTAT"])
            imported_count += 1

        return {"status": "success", "count": imported_count}

    return _run_with_internal_http_error("import_queries", operation)


def _is_post_crq_data(data: Any) -> bool:
    return isinstance(data, dict) and data.get("audit_type") == "post_crq"


QUERY_EXPLANATIONS = {
    "Q01_SUMMARY_360": "Consolida activitat, mida, dependÃ¨ncies i alarmes globals de risc.",
    "Q02_SIZE": "Calcula volum real ocupat per segments de l'esquema.",
    "Q03_USER_ACCOUNT": "Mostra estat de compte, perfil i dates de seguretat/login.",
    "Q04_ACTIVITY_CLASS": "Classifica activitat recent (DDL, stats i modificacions DML).",
    "Q05_OBJECTS_BY_TYPE": "Inventari d'objectes per tipus i extrem de dates DDL/creaciÃ³.",
    "Q06_RECENT_DDL": "Detall d'objectes amb canvis estructurals recents.",
    "Q07_TABLE_STATS": "VigÃ¨ncia d'estadÃ­stiques i volum de taules.",
    "Q08_DEPS_INCOMING": "DependÃ¨ncies entrants (bloquejador principal de baixa).",
    "Q09_DEPS_OUTGOING": "DependÃ¨ncies sortints cap a altres esquemes.",
    "Q10_SYNONYMS": "SinÃ²nims relacionats amb l'esquema (propis i externs).",
    "Q11_GRANTS_GIVEN": "Permisos atorgats per l'esquema a tercers.",
    "Q12_GRANTS_RECEIVED": "Permisos rebuts sobre objectes externs.",
    "Q13_SYS_PRIVS": "Privilegis de sistema de l'esquema.",
    "Q14_CODE_REFS_SOURCE": "ReferÃ¨ncies literals en codi PL/SQL (DBA_SOURCE).",
    "Q14_CODE_REFS_VIEWS": "ReferÃ¨ncies literals en definicions de vistes.",
    "Q14_CODE_REFS_TRIGGERS": "ReferÃ¨ncies literals en clÃ usules WHEN de triggers.",
    "Q15_JOBS": "Inventari de jobs scheduler i estat d'execuciÃ³.",
    "Q16_TRIGGERS_ENABLED": "Triggers habilitats i events associats.",
    "Q17_APEX_APPS": "Aplicacions APEX associades a l'esquema.",
    "Q18_DB_LINKS": "DB links que poden afectar dependÃ¨ncies remotes.",
    "Q19_INVALID_OBJECTS": "Objectes invÃ lids amb risc funcional.",
}


def _is_deep_audit_data(data: List[Dict]) -> bool:
    if not isinstance(data, list) or not data:
        return False
    first = data[0]
    return isinstance(first, dict) and ("executed_queries" in first or "summary" in first and "obsolescence_score" in first)


def _safe_text(value, max_len: int = 120) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _safe_html_text(value, max_len: int = 160) -> str:
    return html.escape(_safe_text(value, max_len))


import re as _re

def _md_to_html(text: str) -> str:
    """Converteix Markdown bÃ sic (negreta, cursiva, llistes, taules) a HTML per a xhtml2pdf."""
    def _fmt(s):
        s = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = _re.sub(r'\*(.+?)\*',     r'<em>\1</em>', s)
        return s

    lines = text.split('\n')
    result = []
    in_ul = False
    in_table = False
    table_rows = []   # accumulem files de la taula per emetre-les juntes

    def flush_table():
        """Emet la taula acumulada com a HTML."""
        if not table_rows:
            return
        out = ['<table>']
        for i, row in enumerate(table_rows):
            cells = [c.strip() for c in row.strip('|').split('|')]
            if i == 0:
                out.append('<thead><tr>')
                for c in cells:
                    out.append(f'<th>{_fmt(c)}</th>')
                out.append('</tr></thead><tbody>')
            else:
                out.append('<tr>')
                for c in cells:
                    out.append(f'<td>{_fmt(c)}</td>')
                out.append('</tr>')
        out.append('</tbody></table>')
        result.extend(out)
        table_rows.clear()

    for line in lines:
        stripped = line.strip()

        # --- Taula Markdown: lÃ­nia amb | ---
        is_table_line = stripped.startswith('|') and stripped.endswith('|')
        is_separator  = _re.match(r'^\|[-| :]+\|$', stripped) is not None

        if is_table_line:
            in_table = True
            if in_ul:
                result.append('</ul>')
                in_ul = False
            if not is_separator:          # ignorem la lÃ­nia |---|---|
                table_rows.append(stripped)
            continue
        else:
            if in_table:
                flush_table()
                in_table = False

        # --- Llista ---
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_ul:
                result.append('<ul>')
                in_ul = True
            result.append(f'<li>{_fmt(stripped[2:])}</li>')
            continue
        else:
            if in_ul:
                result.append('</ul>')
                in_ul = False

        # --- Buits, capÃ§aleres, parÃ grafs ---
        if not stripped:
            continue
        elif stripped.startswith('### '):
            result.append(f'<h3>{_fmt(stripped[4:])}</h3>')
        elif stripped.startswith('## '):
            result.append(f'<h3>{_fmt(stripped[3:])}</h3>')
        elif stripped.startswith('# '):
            result.append(f'<h3>{_fmt(stripped[2:])}</h3>')
        else:
            result.append(f'<p>{_fmt(stripped)}</p>')

    # Tancar blocs oberts
    if in_ul:
        result.append('</ul>')
    if in_table:
        flush_table()

    return '\n'.join(result)


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace("%", "").strip()
        return float(s)
    except (TypeError, ValueError):
        return default


def _recommendation(decision: str) -> str:
    decision = str(decision).upper()
    if "ELIMINAR" in decision and "NO" not in decision:
        return "Executar DROP (previ backup)."
    if "PRECAUCIO" in decision or "RISC" in decision:
        return "Monitoritzar o demanar validaciÃ³ humana."
    return "Mantenir esquema intacte."


def _normalize_report_rows(data: List[Dict]) -> List[Dict]:
    """Converteix format frontend, deep audit o resultats raw en llista plana per al report resum."""
    if not isinstance(data, list):
        data = [data]

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue

        if "schema" in item:
            rows.append(
                {
                    "schema": item.get("schema", "N/A"),
                    "decision": item.get("decision", "PRECAUCIO"),
                    "risk": item.get("risk") or "N/A",
                    "score": _to_float(item.get("score")),
                    "size_gb": _to_float(item.get("size_gb")),
                    "blockers": item.get("blockers") or "",
                    "inbound_refs": int(_to_float(item.get("inbound_refs"))),
                    "active_jobs": int(_to_float(item.get("active_jobs"))),
                    "apex_apps": int(_to_float(item.get("apex_apps"))),
                    "enabled_triggers": int(_to_float(item.get("enabled_triggers"))),
                    "reason": item.get("reason") or "",
                }
            )
        elif "USERNAME" in item and "SIZE_GB" in item:
            rows.append(
                {
                    "schema": item.get("USERNAME", "N/A"),
                    "decision": item.get("DECISIO") or item.get("decisio") or "N/A",
                    "risk": item.get("RISC") or item.get("risc") or "N/A",
                    "score": _to_float(item.get("SCORE") or item.get("score")),
                    "size_gb": _to_float(item.get("SIZE_GB")),
                    "blockers": item.get("RAO") or item.get("rao") or "",
                    "inbound_refs": int(_to_float(item.get("INBOUND_REFERENCES"))),
                    "active_jobs": int(_to_float(item.get("ACTIVE_JOBS"))),
                    "apex_apps": int(_to_float(item.get("APEX_APPLICATIONS"))),
                    "enabled_triggers": int(_to_float(item.get("ENABLED_TRIGGERS"))),
                    "reason": item.get("RAO") or "",
                }
            )
        elif "username" in item or "summary" in item:
            sumry = item.get("summary") or {}
            rows.append(
                {
                    "schema": item.get("username", "N/A"),
                    "decision": item.get("audit_result", "N/A"),
                    "risk": "N/A",
                    "score": _to_float(item.get("obsolescence_score")),
                    "size_gb": _to_float(sumry.get("SIZE_GB")),
                    "blockers": f"Jobs:{sumry.get('ACTIVE_JOBS', 0)}, APEX:{sumry.get('APEX_APPLICATIONS', 0)}",
                    "inbound_refs": int(_to_float(sumry.get("INBOUND_REFERENCES"))),
                    "active_jobs": int(_to_float(sumry.get("ACTIVE_JOBS"))),
                    "apex_apps": int(_to_float(sumry.get("APEX_APPLICATIONS"))),
                    "enabled_triggers": int(_to_float(sumry.get("ENABLED_TRIGGERS"))),
                    "reason": str(item.get("audit_result", "")),
                }
            )
    return rows



def _rows_to_md_table(rows: List[Dict], max_rows: int = 8) -> str:
    if not rows:
        return "_Sense files retornades._"
    sample = rows[:max_rows]
    cols = list(sample[0].keys())[:8]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in sample:
        vals = [_safe_text(row.get(c, "")) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    if len(rows) > max_rows:
        lines.append(f"_... {len(rows) - max_rows} files addicionals no mostrades._")
    return "\n".join(lines)

def _rows_to_html_table(rows: List[Dict], max_rows: int = 5, max_cols: int = 6) -> str:
    if not rows:
        return "<p><i>Sense dades addicionals rellevants.</i></p>"
    sample = rows[:max_rows]
    cols = list(sample[0].keys())[:max_cols]
    html_res = "<table><tr>"
    for c in cols:
        html_res += f"<th>{_safe_html_text(c, 30)}</th>"
    html_res += "</tr>"
    for row in sample:
        html_res += "<tr>"
        for c in cols:
            val = str(row.get(c, ''))
            if len(val) > 40 and " " not in val[:40]:
                val = " ".join(val[i:i+40] for i in range(0, len(val), 40))
            html_res += f"<td>{_safe_html_text(val, 80)}</td>"
        html_res += "</tr>"
    html_res += "</table>"
    if len(rows) > max_rows:
        html_res += f"<p><i>... {len(rows) - max_rows} files addicionals no mostrades.</i></p>"
    return html_res

def _deep_query_payload(schema_item: Dict, query_id: str) -> List[Dict]:
    if query_id == "Q01_SUMMARY_360":
        summary = schema_item.get("summary") or {}
        return [summary] if summary else []
    if query_id == "Q02_SIZE":
        return schema_item.get("size_segments") or []
    if query_id == "Q03_USER_ACCOUNT":
        account = schema_item.get("account") or {}
        return [account] if account else []
    if query_id == "Q04_ACTIVITY_CLASS":
        act = schema_item.get("activity_classification") or {}
        return [act] if act else []
    if query_id == "Q05_OBJECTS_BY_TYPE":
        return schema_item.get("object_types") or []
    if query_id == "Q06_RECENT_DDL":
        return (schema_item.get("activity") or {}).get("ddl") or []
    if query_id == "Q07_TABLE_STATS":
        return schema_item.get("table_stats") or []
    if query_id == "Q08_DEPS_INCOMING":
        return (schema_item.get("dependencies") or {}).get("incoming") or []
    if query_id == "Q09_DEPS_OUTGOING":
        return (schema_item.get("dependencies") or {}).get("outgoing") or []
    if query_id == "Q10_SYNONYMS":
        return schema_item.get("synonyms") or []
    if query_id == "Q11_GRANTS_GIVEN":
        return schema_item.get("grants_given") or []
    if query_id == "Q12_GRANTS_RECEIVED":
        return schema_item.get("grants_received") or []
    if query_id == "Q13_SYS_PRIVS":
        return schema_item.get("sys_privs") or []
    if query_id in ("Q14_CODE_REFS_SOURCE", "Q14_CODE_REFS_VIEWS", "Q14_CODE_REFS_TRIGGERS"):
        return schema_item.get("code_refs") or []
    if query_id == "Q15_JOBS":
        return schema_item.get("active_jobs") or []
    if query_id == "Q16_TRIGGERS_ENABLED":
        return schema_item.get("enabled_triggers") or []
    if query_id == "Q17_APEX_APPS":
        return schema_item.get("apex_apps") or []
    if query_id == "Q18_DB_LINKS":
        return schema_item.get("db_links") or []
    if query_id == "Q19_INVALID_OBJECTS":
        return schema_item.get("invalid_objects") or []
    return []

def _build_deep_markdown_report(profile: str, data: List[Dict]) -> str:
    now = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    total_gb = sum(_to_float((item.get("summary") or {}).get("SIZE_GB"), 0) for item in data)
    avg_score = round(sum(int(_to_float(item.get("obsolescence_score"))) for item in data) / len(data), 2) if data else 0

    md: List[str] = []
    md.append(f"# Informe d'Auditoria Oracle - Perfil: {profile}")
    md.append("")
    md.append("## Context")
    md.append(f"- Perfil actiu: **{profile}**")
    md.append("- Pla executat: **Q01..Q19**")
    md.append(f"- Data de generaciÃ³: **{now}**")
    md.append("")
    md.append("## Objectiu")
    md.append("- Determinar una decisiÃ³ de neteja segura amb evidÃ¨ncia reproduÃ¯ble.")
    md.append("")
    md.append("## Resum Executiu")
    md.append(f"- Esquemes analitzats: **{len(data)}**")
    md.append(f"- Mida total analitzada: **{total_gb:.2f} GB**")
    md.append(f"- Score mitjÃ : **{avg_score}%**")
    md.append("")
    md.append("## Narrativa")
    md.append("- El score final integra activitat, dependÃ¨ncies, impacte de mida i bloquejadors operatius.")
    md.append("")

    for schema_item in data:
        schema = schema_item.get("username") or (schema_item.get("summary") or {}).get("USERNAME") or "N/A"
        summary = schema_item.get("summary") or {}
        decision = schema_item.get("audit_result", "PRECAUCIO")
        score = int(_to_float(schema_item.get("obsolescence_score")))

        in_deps = int(_to_float(summary.get('INBOUND_REFERENCES'), 0))
        jobs = int(_to_float(summary.get('ACTIVE_JOBS'), 0))
        apex = int(_to_float(summary.get('APEX_APPLICATIONS'), 0))
        trigs = int(_to_float(summary.get('ENABLED_TRIGGERS'), 0))
        
        if score >= 100 and (in_deps + jobs + apex + trigs) == 0 and decision == "PRECAUCIO":
            decision = "ELIMINAR"

        md.append(f"## Esquema: `{schema}`")
        md.append("")
        md.append(f"- DecisiÃ³ final: **{decision}**")
        md.append(f"- Score obsolescÃ¨ncia: **{score}%**")
        md.append(f"- Mida: **{_to_float(summary.get('SIZE_GB'), 0):.2f} GB**")
        md.append(f"- DependÃ¨ncies entrants: **{in_deps}**")
        md.append(f"- Jobs actius: **{jobs}**")
        md.append(f"- APEX apps: **{apex}**")
        md.append(f"- Triggers habilitats: **{trigs}**")
        md.append("")

        breakdown = schema_item.get("score_breakdown") or []
        if breakdown:
            md.append("### Motius de l'anÃ lisi (scoring)")
            md.append('<table style="width:100%;border-collapse:collapse;table-layout:fixed;">')
            md.append('<colgroup><col style="width:24%"><col style="width:10%"><col style="width:66%"></colgroup>')
            md.append("<thead><tr><th align=\"left\">Factor</th><th align=\"left\">Punts</th><th align=\"left\">ExplicaciÃ³</th></tr></thead>")
            md.append("<tbody>")
            for b in breakdown:
                md.append(
                    f"<tr><td>{_safe_html_text(b.get('factor'), 80)}</td>"
                    f"<td>{_safe_html_text(b.get('pts'), 20)}</td>"
                    f"<td>{_safe_html_text(b.get('desc'), 220)}</td></tr>"
                )
            md.append("</tbody></table>")
            md.append("")

        md.append("### TraÃ§abilitat de consultes Q01..Q19")
        md.append('<table style="width:100%;border-collapse:collapse;table-layout:fixed;">')
        md.append('<colgroup><col style="width:19%"><col style="width:12%"><col style="width:8%"><col style="width:61%"></colgroup>')
        md.append("<thead><tr><th align=\"left\">Consulta</th><th align=\"left\">Estat</th><th align=\"left\">Files</th><th align=\"left\">Que valida</th></tr></thead>")
        md.append("<tbody>")
        for q in schema_item.get("executed_queries") or []:
            qid = q.get("query", "N/A")
            md.append(
                f"<tr><td>{_safe_html_text(qid, 60)}</td>"
                f"<td>{_safe_html_text(q.get('status'), 20)}</td>"
                f"<td>{_safe_html_text(q.get('rows'), 10)}</td>"
                f"<td>{_safe_html_text(QUERY_EXPLANATIONS.get(qid, '-'), 220)}</td></tr>"
            )
        md.append("</tbody></table>")
        md.append("")

        for q in schema_item.get("executed_queries") or []:
            qid = q.get("query")
            rows = _deep_query_payload(schema_item, qid)
            md.append(f"### {qid} - {QUERY_EXPLANATIONS.get(qid, 'Consulta d auditoria')}")
            md.append(f"- Files retornades: **{len(rows)}**")
            md.append(_rows_to_md_table(rows))
            md.append("")

        md.append("### RecomanaciÃ³ operativa")
        md.append(f"- {_recommendation(decision)}")
        md.append("")

    return "\n".join(md)

def _get_api_insights(profile: str, data: List[Dict]) -> str:
    """Genera un resum executiu utilitzant IA (Gemini)."""
    try:
        from src.core.ai_assistant import AIAssistant
        assistant = AIAssistant()

        schema_lines = []
        for item in data:
            s = item.get("username") or (item.get("summary") or {}).get("USERNAME") or "N/A"
            sum_data = item.get("summary") or {}
            dec = item.get("audit_result", "PRECAUCIO")
            score = int(_to_float(item.get("obsolescence_score")))
            mida = _to_float(sum_data.get("SIZE_GB"))
            in_deps = int(_to_float(sum_data.get("INBOUND_REFERENCES")))
            jobs = int(_to_float(sum_data.get("ACTIVE_JOBS")))
            apex = int(_to_float(sum_data.get("APEX_APPLICATIONS")))
            trigs = int(_to_float(sum_data.get("ENABLED_TRIGGERS")))

            if score >= 100 and (in_deps + jobs + apex + trigs) == 0 and dec == "PRECAUCIO":
                dec = "ELIMINAR"

            schema_lines.append(
                f"- Esquema: {s} | Score: {score}% | Decisio: {dec} | "
                f"Mida: {mida:.2f} GB | Deps.entrants: {in_deps} | "
                f"Jobs: {jobs} | APEX: {apex} | Triggers: {trigs}"
            )

        total_schemas = len(data)
        prompt = f"""Ets un DBA Oracle Senior i Consultor Estrategic per al perfil '{profile}'. 
DADES D'ENTRADA ({total_schemas} esquemes):
{chr(10).join(schema_lines)}
"""
        return assistant.generate_response(prompt)
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("Error generant insights", exc_info=exc)
        return "IA no disponible."


@app.post("/api/report/generate")
async def generate_report(payload: Dict = Body(...)):
    """Genera un report professional en format markdown o pdf."""
    def operation():
        data = payload.get("data", [])
        profile = payload.get("profile", "default")
        fmt = payload.get("format", "markdown")

        rows = _normalize_report_rows(data)
        if _is_deep_audit_data(data) or _is_post_crq_data(data) or rows:
            # IA deshabilitada per defecte, es pot activar des del payload
            ai_active = payload.get("ai_active", False)
            
            # Post-CRQ Case
            if _is_post_crq_data(data):
                if fmt == "pdf":
                    try:
                        pdf_bytes = build_post_crq_pdf_report(profile, data)
                    except (RuntimeError, ValueError, TypeError, OSError) as exc:
                        raise HTTPException(
                            status_code=500,
                            detail=f"report_generation_stage=classic_post_crq_pdf; {exc}",
                        ) from exc
                    filename = f"report_auditoria_post_crq_{profile}_{_report_timestamp_slug()}.pdf"
                    return _stream_attachment(pdf_bytes, "application/pdf", filename)
                report_content = build_post_crq_markdown_report(profile, data)
                filename = f"report_auditoria_post_crq_{profile}_{_report_timestamp_slug()}.md"
                return _stream_attachment(report_content, "text/markdown; charset=utf-8", filename)

            # Deep Scan / Obsolets Case
            if _is_deep_audit_data(data):
                report_data = data
            else:
                report_data = [
                    {
                        "username": r["schema"], 
                        "audit_result": r["decision"], 
                        "obsolescence_score": r["score"],
                        "summary": {
                            "SIZE_GB": r["size_gb"], 
                            "INBOUND_REFERENCES": r["inbound_refs"], 
                            "ACTIVE_JOBS": r["active_jobs"], 
                            "APEX_APPLICATIONS": r["apex_apps"], 
                            "ENABLED_TRIGGERS": r["enabled_triggers"]
                        },
                        "reason": r["reason"]
                    } for r in rows
                ]

            from src.api.report_builder import build_standard_pdf, build_standard_markdown
            if fmt == "pdf":
                pdf_bytes = build_standard_pdf(profile, report_data, ai_active=ai_active)
                prefix = "report_auditoria_detallat" if _is_deep_audit_data(data) else "report_auditoria"
                filename = f"{prefix}_{profile}_{_report_timestamp_slug()}.pdf"
                return _stream_attachment(pdf_bytes, "application/pdf", filename)

            report_content = build_standard_markdown(profile, report_data, ai_active=ai_active)
            prefix = "report_auditoria_detallat" if _is_deep_audit_data(data) else "report_auditoria"
            filename = f"{prefix}_{profile}_{_report_timestamp_slug()}.md"
            return _stream_attachment(report_content, "text/markdown; charset=utf-8", filename)

        raise HTTPException(status_code=400, detail="No hi ha dades d'auditoria per generar el report")

    return _run_with_internal_http_error("generate_report", operation)


@app.post("/api/report/generate-experimental")
async def generate_experimental_report(payload: Dict = Body(...)):
    """Genera un PDF experimental del post-CRQ sense afectar el flux oficial."""
    def operation():
        data = payload.get("data", [])
        profile = payload.get("profile", "default")
        variant = (payload.get("variant") or "general").strip().lower()
        lot_code = (payload.get("lot_code") or "").strip()

        if not _is_post_crq_data(data):
            raise HTTPException(status_code=400, detail="La versió experimental només està disponible per a l'auditoria post-CRQ.")
        if not isinstance(data, dict) or not data.get("report_model"):
            raise HTTPException(status_code=400, detail="Cal executar abans l'auditoria post-CRQ perquè el report_model estigui disponible.")

        if variant not in {"general", "lot"}:
            raise HTTPException(status_code=400, detail="El camp variant ha de ser 'general' o 'lot'.")
        if variant == "lot":
            if not lot_code:
                raise HTTPException(status_code=400, detail="Cal informar lot_code per generar el PDF per lot.")
            try:
                data = filter_post_crq_report_for_lot(data, lot_code)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        pdf_bytes = build_post_crq_experimental_pdf(profile, data)
        lot_suffix = f"_{lot_code}" if variant == "lot" else ""
        filename = f"report_auditoria_post_crq_experimental_{profile}{lot_suffix}_{_report_timestamp_slug()}.pdf"
        return _stream_attachment(pdf_bytes, "application/pdf", filename)

    return _run_with_internal_http_error("generate_experimental_report", operation)

@app.post("/api/queries/export")
async def export_query_results(data: List[Dict] = Body(...)):
    """Genera un fitxer Excel a partir de resultats i el retorna."""
    def operation():
        import io
        
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Resultats')
        
        buffer.seek(0)
        return _stream_attachment(
            buffer,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "resultats_consulta.xlsx",
        )

    return _run_with_internal_http_error("export_query_results", operation)

# --- Unified React API additions: Snapshots + Obsolets registry ---

def _load_app_config() -> Dict:
    try:
        with open("config/config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _snapshots_dir() -> str:
    cfg = _load_app_config()
    rel = ((cfg.get("paths") or {}).get("snapshots")) or "data/snapshots"
    return os.path.abspath(rel)


def _list_parquet_files(dir_path: str) -> List[str]:
    if not os.path.isdir(dir_path):
        return []
    return glob.glob(os.path.join(dir_path, "*.parquet"))


def _parquet_num_rows(path: str) -> Optional[int]:
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        return int(pf.metadata.num_rows)
    except (ImportError, OSError, ValueError) as exc:
        logger.warning("No s'han pogut llegir les files del parquet %s", path, exc_info=exc)
        return None


def _apply_snapshot_filters(df: pd.DataFrame, schemas, recommendations, min_score):
    out = df
    if schemas:
        out = out[out["schema"].isin([str(s) for s in schemas])]
    if recommendations:
        recs = {str(r).upper() for r in recommendations}
        out = out[out["recommendation"].astype(str).str.upper().isin(recs)]
    if min_score is not None:
        try:
            ms = float(min_score)
            out = out[out["score"].astype(float) >= ms]
        except (TypeError, ValueError):
            logger.debug("min_score invalid ignorat al filtre de snapshots: %r", min_score)
    return out


def _ctime_to_utc_iso(created_at: float) -> str:
    return utc_isoformat(datetime.datetime.fromtimestamp(created_at, tz=datetime.timezone.utc))


def _resolve_snapshot_path(snapshot_dir: str, snapshot_id: str, files: List[str]) -> str:
    if not files:
        raise HTTPException(status_code=404, detail="No hi ha snapshots")

    if snapshot_id:
        path = os.path.abspath(os.path.join(snapshot_dir, snapshot_id))
        if not path.startswith(os.path.abspath(snapshot_dir) + os.sep) or not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Snapshot no trobat")
        return path

    return max(files, key=lambda p: os.path.getctime(p))


@app.get("/api/snapshots")
async def list_snapshots():
    """Llista snapshots (parquet) disponibles."""
    def operation():
        d = _snapshots_dir()
        files = _list_parquet_files(d)
        items = []
        for p in files:
            try:
                created = os.path.getctime(p)
                created_iso = _ctime_to_utc_iso(created)
            except OSError:
                created_iso = None
            items.append(
                {
                    "snapshot_id": os.path.basename(p),
                    "created_at": created_iso,
                    "rows_estimated": _parquet_num_rows(p),
                }
            )
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return {"snapshots": items, "dir": d}

    return _run_with_internal_http_error("list_snapshots", operation)


@app.get("/api/snapshots/latest")
async def latest_snapshot():
    """Retorna el snapshot mes recent (parquet)."""
    def operation():
        d = _snapshots_dir()
        files = _list_parquet_files(d)
        if not files:
            return {"snapshot": None, "dir": d}
        latest = max(files, key=lambda p: os.path.getctime(p))
        created = os.path.getctime(latest)
        return {
            "snapshot": {
                "snapshot_id": os.path.basename(latest),
                "created_at": _ctime_to_utc_iso(created),
                "rows_estimated": _parquet_num_rows(latest),
            },
            "dir": d,
        }

    return _run_with_internal_http_error("latest_snapshot", operation)


@app.post("/api/snapshots/query")
async def query_snapshots(payload: Dict = Body(...)):
    """Query server-side del snapshot (filtres + paginaciÃ³ + sort)."""
    def operation():
        d = _snapshots_dir()
        snapshot_id = (payload.get("snapshot_id") or "").strip()
        files = _list_parquet_files(d)
        if not files:
            return {"rows": [], "summary": {"total_objects": 0}, "facets": {"schemas": [], "recommendations": []}}
        path = _resolve_snapshot_path(d, snapshot_id, files)

        df = pd.read_parquet(path)
        facets = {
            "schemas": sorted({str(x) for x in df.get("schema", pd.Series(dtype=str)).dropna().unique().tolist()}),
            "recommendations": sorted({str(x) for x in df.get("recommendation", pd.Series(dtype=str)).dropna().unique().tolist()}),
        }

        schemas = payload.get("schemas") or []
        recommendations = payload.get("recommendations") or []
        min_score = payload.get("min_score", None)

        limit = int(payload.get("limit", 200) or 200)
        offset = int(payload.get("offset", 0) or 0)
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)

        sort_by = (payload.get("sort_by") or "score").strip()
        sort_dir = (payload.get("sort_dir") or "desc").strip().lower()
        allowed_sort = {"schema", "table_name", "size_gb", "days_inactive", "score", "recommendation", "risk_level"}
        if sort_by not in allowed_sort:
            sort_by = "score"
        ascending = sort_dir == "asc"

        filtered = _apply_snapshot_filters(df, schemas, recommendations, min_score)
        total_objects = int(len(filtered))
        total_gb = float(filtered.get("size_gb", pd.Series(dtype=float)).fillna(0).sum()) if total_objects else 0.0
        avg_score = float(filtered.get("score", pd.Series(dtype=float)).astype(float).mean()) if total_objects else 0.0
        drop_count = int((filtered.get("recommendation", pd.Series(dtype=str)).astype(str).str.upper() == "DROP").sum()) if total_objects else 0

        if sort_by in filtered.columns:
            filtered = filtered.sort_values(by=sort_by, ascending=ascending, kind="mergesort")

        page = filtered.iloc[offset: offset + limit]
        rows = page.to_dict("records")

        return {
            "snapshot_id": os.path.basename(path),
            "rows": rows,
            "summary": {
                "total_objects": total_objects,
                "total_gb": round(total_gb, 6),
                "avg_score": round(avg_score, 4),
                "drop_count": drop_count,
            },
            "facets": facets,
            "page": {"limit": limit, "offset": offset},
        }

    return _run_with_internal_http_error("query_snapshots", operation)


@app.post("/api/snapshots/export.csv")
async def export_snapshot_csv(payload: Dict = Body(...)):
    """Export CSV del snapshot filtrat."""
    def operation():
        d = _snapshots_dir()
        snapshot_id = (payload.get("snapshot_id") or "").strip()
        files = _list_parquet_files(d)
        path = _resolve_snapshot_path(d, snapshot_id, files)

        df = pd.read_parquet(path)
        filtered = _apply_snapshot_filters(
            df,
            payload.get("schemas") or [],
            payload.get("recommendations") or [],
            payload.get("min_score", None),
        )

        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        filename = f"{os.path.splitext(os.path.basename(path))[0]}_export.csv"
        return _stream_attachment(csv_bytes, "text/csv; charset=utf-8", filename)

    return _run_with_internal_http_error("export_snapshot_csv", operation)


@app.get("/api/obsolets")
async def list_obsolets(
    only_obsolete: bool = True,
    schema_name: Optional[str] = None,
    risk_level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Llista el registre d'obsolets (SQLite meta_objects)."""
    def operation():
        rows, cols = internal_db.list_meta_objects(
            only_obsolete=only_obsolete,
            schema_name=schema_name,
            risk_level=risk_level,
            source=source,
            limit=limit,
            offset=offset,
        )
        return {"items": [dict(zip(cols, r)) for r in rows], "page": {"limit": limit, "offset": offset}}

    return _run_with_internal_http_error("list_obsolets", operation)


@app.post("/api/obsolets")
async def create_obsolet(payload: Dict = Body(...)):
    """Afegeix una entrada al registre d'obsolets."""
    def operation():
        schema_name = (payload.get("schema_name") or "").strip()
        object_name = (payload.get("object_name") or "").strip()
        object_type = (payload.get("object_type") or "").strip()
        reason = (payload.get("reason") or "").strip()
        risk_level = (payload.get("risk_level") or "").strip()
        recommendation = (payload.get("recommendation") or "").strip()
        description = (payload.get("description") or "").strip()
        source = (payload.get("source") or "USER").strip()
        is_obsolete = int(1 if payload.get("is_obsolete", 1) else 0)

        if not (schema_name and object_name and object_type and reason and risk_level):
            raise HTTPException(status_code=400, detail="Falten camps obligatoris")

        obj_id = internal_db.add_meta_object(
            schema_name=schema_name,
            object_name=object_name,
            object_type=object_type,
            reason=reason,
            risk_level=risk_level,
            recommendation=recommendation,
            description=description,
            source=source,
            is_obsolete=is_obsolete,
        )
        return {"status": "success", "id": obj_id}

    return _run_with_internal_http_error("create_obsolet", operation)


@app.patch("/api/obsolets/{obj_id}")
async def update_obsolet(obj_id: int, payload: Dict = Body(...)):
    """Actualitza camps d'una entrada del registre d'obsolets."""
    def operation():
        updated = internal_db.update_meta_object(int(obj_id), **payload)
        if not updated:
            raise HTTPException(status_code=404, detail="No trobat o sense canvis")
        return {"status": "success"}

    return _run_with_internal_http_error("update_obsolet", operation)

# Servir fitxers estÃ tics del frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web-app", "dist"))
logger.debug("Buscant frontend a: %s", frontend_path)

if os.path.exists(frontend_path):
    # Muntem la carpeta d'estÃ tics per a fitxers directes (js, css, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")

    # Qualsevol altra ruta que no sigui API, retorna l'index.html (SPA support)
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str = ""):
        logger.debug("Catch-all SPA: full_path='%s', url='%s'", full_path, request.url)
        if full_path.startswith("api"):
             raise HTTPException(status_code=404, detail=f"API endpoint '{full_path}' not found")
        
        # Servir fitxers individuals si existeixen a la rrel (ex: vite.svg, favicon.ico)
        if full_path:
            potential_file = os.path.join(frontend_path, full_path)
            if os.path.isfile(potential_file):
                return FileResponse(potential_file)

        index_file = os.path.join(frontend_path, "index.html")
        return FileResponse(index_file)
        
    @app.get("/")
    async def serve_root():
        index_file = os.path.join(frontend_path, "index.html")
        return FileResponse(index_file)
else:
    logger.warning("No s'ha trobat la carpeta 'dist'. El frontend no estarà disponible.")
    @app.get("/")
    async def root_info():
        return {"message": "API is running. Frontend build missing.", "expected_path": frontend_path}

if __name__ == "__main__":
    import uvicorn
    # Use string "main:app" for reload to work correctly
    port_env = int(os.environ.get("PORT", 8011))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port_env, reload=True)




