"""
checks_admin_router.py
======================
Router FastAPI per a la gestió CRUD dels checks i les seves consultes SQL.
Exposat sota el prefix /api/checks.

Endpoints:
  GET    /api/checks                → llista de tots els checks amb estat
  GET    /api/checks/{check_id}     → detall del check amb versió vigent
  POST   /api/checks                → crear nou check
  PUT    /api/checks/{check_id}     → editar check (crea nova versió)
  DELETE /api/checks/{check_id}     → eliminar check (soft delete)
  GET    /api/checks/{check_id}/history    → historial de versions
  POST   /api/checks/{check_id}/regenerate → forçar regeneració IA
  GET    /api/checks/{check_id}/sync-status → estat de sincronització

Codificació: UTF-8 (garantia lingüística català)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import unicodedata
from datetime import timedelta
from typing import Any, Dict, List, Optional

import re
import shutil
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field, constr
import requests

from src.core.config_loader import ConfigLoader
from src.core.ai_assistant import AIAssistant
from src.core.db_manager import OracleDBManager
from src.core.dba_query_explainer import DBAExplainRequest, DBAQueryExplainer
from src.core.query_sync_service import QuerySyncService
from src.core.sql_result_comparator import compare_query_results, default_comparison_options
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now, utc_now_iso
from src.api.post_crq_audit import _days_back_from_filter, _run_single_post_crq_check, parse_post_crq_checks
from src.core.sql_codex_transformer import transform_for_codex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checks", tags=["Gestió de Checks"])
config_loader = ConfigLoader()

SEVERITATS_VALIDES = {"Crític", "Mitjà", "Baix"}

# ─── Models Pydantic ──────────────────────────────────────────────────────────

class CheckCreate(BaseModel):
    check_id: str = Field(..., examples=["CHECK_14"])
    titol: str = Field(..., examples=["TAULES SENSE COMENTARI"])
    severitat_base: str = Field(..., examples=["Mitjà"])
    sql_text: str = Field(..., examples=["SELECT * FROM dba_tables WHERE ..."])
    parametres: Optional[str] = Field(None, examples=["days_back"])
    tipus: str = Field("SQL", examples=["SQL"])
    ordre: int = Field(0, examples=[14])
    context_check: Optional[str] = None
    ai_enabled: int = Field(0, examples=[0, 1])


class CheckUpdate(BaseModel):
    titol: Optional[str] = None
    severitat_base: Optional[str] = None
    sql_text: Optional[str] = None
    parametres: Optional[str] = None
    context_check: Optional[str] = None
    ai_enabled: Optional[int] = None


class CheckResponse(BaseModel):
    check_id: str
    titol: str
    severitat_base: str
    parametres: Optional[str]
    tipus: str
    ordre: int
    actiu: int
    context_check: Optional[str]
    ai_enabled: int = 0
    creat_en: str
    actualitzat_en: str
    versio_vigent: Optional[int] = None
    sql_vigent: Optional[str] = None
    estat_explicacio: Optional[str] = None
    estat_sync_md: Optional[str] = None
    estat_sync_txt: Optional[str] = None


class CheckValidationRequest(BaseModel):
    check_id: str = Field(..., examples=["CHECK_01"])
    titol: str = Field(..., examples=["TAULES RECENTS SENSE PRIMARY KEY"])
    severitat_base: str = Field(..., examples=["Mitjà"])
    sql_text: str = Field(..., examples=["SELECT * FROM dba_tables WHERE ..."])
    parametres: Optional[str] = Field(None, examples=["days_back"])
    tipus: str = Field("SQL", examples=["SQL"])
    context_check: Optional[str] = None
    profile: Optional[str] = Field(None, examples=["E13DB"])
    validation_start_at: Optional[str] = Field(None, examples=["2026-04-10T09:00"])
    validation_end_at: Optional[str] = Field(None, examples=["2026-04-11T09:00"])


class SQLTransformRequest(BaseModel):
    sql_text: str
    debug: bool = False


class CodexEngineComparisonOptions(BaseModel):
    trim_whitespace: bool = True
    null_equals_empty: bool = False
    ignore_case: bool = False
    ignore_row_order: bool = False
    normalize_dates: bool = True
    normalize_numbers: bool = True
    compare_by_column_name: bool = True
    normalize_column_aliases: bool = True
    sample_limit: int = Field(25, ge=1, le=100)
    preview_limit: int = Field(100, ge=10, le=500)
    comparison_key: List[str] = Field(default_factory=list)


class CodexEngineExecuteRequest(BaseModel):
    sql_text: str
    profile: Optional[str] = Field(None, examples=["E13DB"])
    side: str = Field("right", examples=["left", "right"])
    variables: Dict[str, str] = Field(default_factory=dict)
    preview_limit: int = Field(100, ge=10, le=500)


class CodexEngineExecuteBothRequest(BaseModel):
    left_sql: str
    right_sql: str
    profile: Optional[str] = Field(None, examples=["E13DB"])
    variables: Dict[str, str] = Field(default_factory=dict)
    preview_limit: int = Field(100, ge=10, le=500)


class CodexEngineCompareRequest(BaseModel):
    left_sql: str
    right_sql: str
    profile: Optional[str] = Field(None, examples=["E13DB"])
    variables: Dict[str, str] = Field(default_factory=dict)
    options: CodexEngineComparisonOptions = Field(default_factory=CodexEngineComparisonOptions)


class CodexEngineAnalyzeRequest(BaseModel):
    left_sql: str
    right_sql: str
    left: Dict[str, Any]
    right: Dict[str, Any]
    comparison: Dict[str, Any]


# ─── Helpers de BBDD ──────────────────────────────────────────────────────────

def _get_db() -> str:
    return resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _ensure_checks_schema(conn: sqlite3.Connection) -> None:
    columns = _get_table_columns(conn, "audit_checks")
    if "ai_enabled" not in columns:
        conn.execute("ALTER TABLE audit_checks ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    if _table_exists(conn, "consulta_versions"):
        version_columns = _get_table_columns(conn, "consulta_versions")
        if "checksum" not in version_columns:
            conn.execute("ALTER TABLE consulta_versions ADD COLUMN checksum TEXT")
        if "creat_per" not in version_columns:
            conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_per TEXT")
        if "creat_en" not in version_columns:
            conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_en TEXT")
        conn.commit()


def _get_check_or_404(conn: sqlite3.Connection, check_id: str) -> dict:
    _ensure_checks_schema(conn)
    row = conn.execute(
        "SELECT * FROM audit_checks WHERE check_id = ? AND actiu = 1",
        (check_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Check '{check_id}' no trobat.")
    cols = [d[0] for d in conn.execute("SELECT * FROM audit_checks LIMIT 0").description or
            [("check_id",), ("titol",), ("severitat_base",), ("parametres",),
             ("tipus",), ("ordre",), ("actiu",), ("context_check",),
             ("creat_en",), ("actualitzat_en",)]]
    # Requery amb col names
    cur = conn.execute("SELECT * FROM audit_checks WHERE check_id = ?", (check_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_sql_for_versioning(sql_text: Optional[str]) -> str:
    text = str(sql_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    header_pattern = re.compile(
        r"^\s*-- =+\s*\n"
        r"-- CHECK[ _]\d+:.*\n"
        r"(?:--.*\n)*?"
        r"-- =+\s*\n?",
        re.IGNORECASE,
    )
    stripped = header_pattern.sub("", text, count=1).strip()
    return stripped or text


def _sql_version_checksum(sql_text: Optional[str]) -> str:
    return _sha256(_normalize_sql_for_versioning(sql_text))


def _next_versio(conn: sqlite3.Connection, check_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(versio) FROM consulta_versions WHERE check_id = ?", (check_id,)
    ).fetchone()
    return (row[0] or 0) + 1


def _detect_md_tipus(sql_text: Optional[str]) -> str:
    sql_upper = (sql_text or "").upper()
    indicadors_plsql = ("BEGIN", "DECLARE", "PROCEDURE", "FUNCTION", "PACKAGE", "DBMS_", "EXECUTE", "LOOP", "CURSOR")
    return "PLSQL" if any(token in sql_upper for token in indicadors_plsql) else "SQL"


def _normalize_markdown_severity(raw_value: Optional[str], current_value: Optional[str] = None) -> str:
    if current_value in SEVERITATS_VALIDES and raw_value not in (None, ""):
        candidate_current = str(current_value).strip()
    else:
        candidate_current = None

    text = str(raw_value or "").strip()
    normalized = unicodedata.normalize("NFD", text.upper()).encode("ascii", "ignore").decode("ascii")

    if normalized in {"CRITIC", "CRITIC ", "STOPPER", "ALT"}:
        return "Crític"
    if normalized in {"MITJA", "MITJA ", "MITJA/BAIX"} or "MITJ" in normalized:
        return "Mitjà"
    if "BAIX" in normalized:
        return "Baix"
    if candidate_current in SEVERITATS_VALIDES:
        return candidate_current
    return "Mitjà"


def _sync_markdown_sql_version(
    conn: sqlite3.Connection,
    *,
    check_id: str,
    sql_text: str,
    created_at: str,
) -> bool:
    actual = conn.execute(
        "SELECT id, sql_text, versio FROM consulta_versions WHERE check_id = ? AND es_vigent = 1 ORDER BY versio DESC LIMIT 1",
        (check_id,),
    ).fetchone()
    normalized_sql = (sql_text or "").strip()
    if actual and _sql_version_checksum(actual["sql_text"]) == _sql_version_checksum(normalized_sql):
        return False

    if actual:
        conn.execute(
            "UPDATE consulta_versions SET es_vigent = 0 WHERE check_id = ? AND es_vigent = 1",
            (check_id,),
        )

    conn.execute(
        """INSERT INTO consulta_versions (check_id, versio, sql_text, checksum, creat_per, creat_en, es_vigent)
           VALUES (?, ?, ?, ?, 'markdown_sync', ?, 1)""",
        (check_id, _next_versio(conn, check_id), normalized_sql, _sql_version_checksum(normalized_sql), created_at),
    )
    conn.execute(
        "UPDATE explicacions SET estat = 'OBSOLETA' WHERE check_id = ? AND estat = 'VIGENT'",
        (check_id,),
    )
    return True


def _has_unsynced_user_sql_override(
    conn: sqlite3.Connection,
    *,
    check_id: str,
    markdown_sql: str,
) -> bool:
    latest_version = conn.execute(
        """SELECT sql_text, creat_per
           FROM consulta_versions
           WHERE check_id = ?
           ORDER BY versio DESC
           LIMIT 1""",
        (check_id,),
    ).fetchone()
    if not latest_version:
        return False

    creator = str(latest_version["creat_per"] or "").strip().lower()
    if creator != "usuari":
        return False

    sync_rows = conn.execute(
        "SELECT estat FROM sincronitzacio_fitxers WHERE check_id = ?",
        (check_id,),
    ).fetchall()
    if not sync_rows:
        return False

    statuses = {str(row["estat"] or "").strip().upper() for row in sync_rows}
    if statuses == {"OK"}:
        return False

    latest_sql = (latest_version["sql_text"] or "").strip()
    return _sql_version_checksum(latest_sql) != _sql_version_checksum((markdown_sql or "").strip())


def _sync_checks_catalog_from_markdown(conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Alinea el catàleg actiu de SQLite amb `auditoria_post_crq.md`.
    El Markdown es considera la font canònica del set de checks i de la SQL vigent.
    """
    _ensure_checks_schema(conn)
    markdown_checks = parse_post_crq_checks()
    now = utc_now_iso()
    stats = {"created": 0, "updated": 0, "sql_updated": 0, "deactivated": 0}

    existing_rows = conn.execute("SELECT * FROM audit_checks").fetchall()
    existing_by_id = {row["check_id"]: row for row in existing_rows}
    markdown_ids = set()

    for markdown_check in markdown_checks:
        check_id = str(markdown_check.get("check_id") or "").upper().strip()
        if not check_id:
            continue

        markdown_ids.add(check_id)
        current = existing_by_id.get(check_id)
        titol = (
            markdown_check.get("title")
            or (current["titol"] if current else check_id)
        ).strip()
        severitat = _normalize_markdown_severity(
            markdown_check.get("severitat_base") or markdown_check.get("severitat"),
            current["severitat_base"] if current else None,
        )
        context_check = (markdown_check.get("criteri") or markdown_check.get("description") or (current["context_check"] if current else "") or "").strip()
        sql_text = (markdown_check.get("sql") or "").strip()
        ordre = int(markdown_check.get("check_number") or (current["ordre"] if current else 0) or 0)
        tipus = _detect_md_tipus(sql_text)
        parametres = current["parametres"] if current else "days_back"
        ai_enabled = int(current["ai_enabled"]) if current else 0

        if current is None:
            conn.execute(
                """INSERT INTO audit_checks
                   (check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, ai_enabled, creat_en, actualitzat_en)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (check_id, titol, severitat, parametres, tipus, ordre, context_check, ai_enabled, now, now),
            )
            stats["created"] += 1
        else:
            if _has_unsynced_user_sql_override(conn, check_id=check_id, markdown_sql=sql_text):
                continue

            changed_fields = (
                current["titol"] != titol
                or current["severitat_base"] != severitat
                or (current["context_check"] or "") != context_check
                or current["tipus"] != tipus
                or int(current["ordre"] or 0) != ordre
                or int(current["actiu"] or 0) != 1
            )
            if changed_fields:
                conn.execute(
                    """UPDATE audit_checks
                       SET titol = ?, severitat_base = ?, tipus = ?, ordre = ?, actiu = 1,
                           context_check = ?, actualitzat_en = ?
                       WHERE check_id = ?""",
                    (titol, severitat, tipus, ordre, context_check, now, check_id),
                )
                stats["updated"] += 1
            elif int(current["actiu"] or 0) != 1:
                conn.execute(
                    "UPDATE audit_checks SET actiu = 1, actualitzat_en = ? WHERE check_id = ?",
                    (now, check_id),
                )
                stats["updated"] += 1

        if _sync_markdown_sql_version(conn, check_id=check_id, sql_text=sql_text, created_at=now):
            stats["sql_updated"] += 1

    for existing_id, row in existing_by_id.items():
        if existing_id not in markdown_ids and int(row["actiu"] or 0) == 1:
            conn.execute(
                "UPDATE audit_checks SET actiu = 0, actualitzat_en = ? WHERE check_id = ?",
                (now, existing_id),
            )
            stats["deactivated"] += 1

    return stats


def _persist_explanation_row(
    conn: sqlite3.Connection,
    *,
    check_id: str,
    version_id: int,
    estat: str,
    created_at: str,
    payload: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    columns = _get_table_columns(conn, "explicacions")
    existing_row = None
    if "consulta_version_id" in columns:
        existing_row = conn.execute(
            "SELECT id FROM explicacions WHERE check_id = ? AND consulta_version_id = ? ORDER BY id DESC LIMIT 1",
            (check_id, version_id),
        ).fetchone()

    values: Dict[str, Any] = {}
    if "check_id" in columns:
        values["check_id"] = check_id
    if "consulta_version_id" in columns:
        values["consulta_version_id"] = version_id
    if "estat" in columns:
        values["estat"] = estat
    if "creat_en" in columns:
        values["creat_en"] = created_at
    if "error_missatge" in columns:
        values["error_missatge"] = error_message

    if payload:
        payload_mapping = {
            "resum_executiu": payload.get("resum_executiu"),
            "explicacio_funcional": payload.get("explicacio_funcional"),
            "explicacio_tecnica": payload.get("explicacio_tecnica"),
            "impacte": payload.get("impacte"),
            "riscos": payload.get("riscos"),
            "canvis_respecte_anterior": payload.get("canvis_respecte_anterior"),
            "recomanacio_revisio": payload.get("recomanacio_revisio"),
            "nivell_confianca": payload.get("nivell_confianca"),
            "advertiments": payload.get("advertiments"),
            "model_utilitzat": payload.get("model_utilitzat"),
        }
        for column, value in payload_mapping.items():
            if column in columns:
                values[column] = value

    if existing_row:
        assignments = ", ".join(f"{column} = ?" for column in values)
        conn.execute(
            f"UPDATE explicacions SET {assignments} WHERE id = ?",
            (*values.values(), int(existing_row[0])),
        )
        return

    insert_columns = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO explicacions ({insert_columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _record_regeneration_error(db_path: str, *, check_id: str, version_id: int, error_message: str) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            _persist_explanation_row(
                conn,
                check_id=check_id,
                version_id=version_id,
                estat="ERROR",
                created_at=utc_now_iso(),
                error_message=error_message,
            )
            conn.commit()
        QuerySyncService(_get_projecte_root(), db_path).mark_error(check_id, error_message)
    except sqlite3.Error as exc:
        logger.warning(
            "No s'ha pogut persistir l'error de regeneraci? per %s/%s",
            check_id,
            version_id,
            exc_info=exc,
        )
    except (OSError, ValueError) as exc:
        logger.warning(
            "No s'ha pogut marcar l'error de sincronitzacio per %s/%s",
            check_id,
            version_id,
            exc_info=exc,
        )


def _load_regeneration_context(
    db_path: str, check_id: str, version_id: int
) -> tuple[sqlite3.Row, sqlite3.Row, Optional[sqlite3.Row]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        check = conn.execute(
            "SELECT * FROM audit_checks WHERE check_id = ?", (check_id,)
        ).fetchone()
        ver_nova = conn.execute(
            "SELECT * FROM consulta_versions WHERE id = ?", (version_id,)
        ).fetchone()
        ver_ant = conn.execute(
            """SELECT sql_text FROM consulta_versions
               WHERE check_id = ? AND es_vigent = 0
               ORDER BY versio DESC LIMIT 1""",
            (check_id,),
        ).fetchone()

    if not check or not ver_nova:
        raise LookupError(f"No s'ha trobat check o versi?: {check_id} / {version_id}")

    return check, ver_nova, ver_ant


def _persist_regenerated_explanation(
    db_path: str,
    *,
    check_id: str,
    version_id: int,
    response: Any,
) -> None:
    ara = utc_now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE explicacions SET estat = 'OBSOLETA' WHERE check_id = ? AND estat = 'VIGENT'",
            (check_id,),
        )
        _persist_explanation_row(
            conn,
            check_id=check_id,
            version_id=version_id,
            estat="VIGENT",
            created_at=ara,
            payload={
                "resum_executiu": response.resum_executiu,
                "explicacio_funcional": response.explicacio_funcional,
                "explicacio_tecnica": response.explicacio_tecnica,
                "impacte": response.impacte,
                "riscos": response.riscos,
                "canvis_respecte_anterior": response.canvis_respecte_anterior,
                "recomanacio_revisio": response.recomanacio_revisio,
                "nivell_confianca": response.nivell_confianca,
                "advertiments": response.advertiments,
                "model_utilitzat": response.model_utilitzat,
            },
        )
        conn.commit()


def _resolve_oracle_profile(profile_name: Optional[str]) -> tuple[str, Dict[str, Any]]:
    profiles = config_loader.load_connections()
    selected_profile = config_loader.resolve_profile_name(profile_name, profiles)
    if not selected_profile:
        raise HTTPException(status_code=404, detail="Perfil Oracle no trobat.")

    params = dict(profiles[selected_profile] or {})
    params["PROFILE_NAME"] = selected_profile
    oracle_client_lib_dir = config_loader.get_env_var("ORACLE_CLIENT_LIB_DIR")
    if oracle_client_lib_dir:
        params["ORACLE_CLIENT_LIB_DIR"] = oracle_client_lib_dir
    return selected_profile, params


def _default_validation_time_filter() -> Dict[str, str]:
    reference_dt = utc_now()
    start_dt = reference_dt - timedelta(days=1)
    return {
        "mode": "range",
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": reference_dt.strftime("%Y-%m-%d"),
        "range_start_at": start_dt.strftime("%Y-%m-%dT%H:%M"),
        "range_end_at": reference_dt.strftime("%Y-%m-%dT%H:%M"),
    }


def _resolve_current_explanation_status(
    conn: sqlite3.Connection,
    *,
    check_id: str,
    current_version_id: Optional[int],
) -> Optional[str]:
    if current_version_id is not None:
        current = conn.execute(
            "SELECT estat FROM explicacions WHERE check_id = ? AND consulta_version_id = ? ORDER BY id DESC LIMIT 1",
            (check_id, current_version_id),
        ).fetchone()
        if current:
            return current["estat"] if isinstance(current, sqlite3.Row) else current[0]
        return "PENDENT"

    legacy = conn.execute(
        "SELECT estat FROM explicacions WHERE check_id = ? ORDER BY id DESC LIMIT 1",
        (check_id,),
    ).fetchone()
    if legacy:
        return legacy["estat"] if isinstance(legacy, sqlite3.Row) else legacy[0]
    return None


def _preview_ai_explanation(
    *,
    conn: sqlite3.Connection,
    check_id: str,
    titol: str,
    severitat_base: str,
    sql_text: str,
    parametres: Optional[str],
    context_check: Optional[str],
    tipus: str,
) -> Dict[str, Any]:
    current_version = conn.execute(
        "SELECT versio, sql_text FROM consulta_versions WHERE check_id = ? AND es_vigent = 1",
        (check_id,),
    ).fetchone()
    versio_nova = int(current_version["versio"] if current_version else 0) + 1
    sql_anterior = current_version["sql_text"] if current_version else None
    request = DBAExplainRequest(
        check_id=check_id,
        titol=titol,
        severitat=severitat_base,
        sql_nou=sql_text,
        versio_nova=versio_nova,
        parametres=[p.strip() for p in (parametres or "").split(",") if p.strip()],
        sql_anterior=sql_anterior,
        context_check=context_check or "",
        tipus=tipus or "SQL",
    )
    response = DBAQueryExplainer(db_path=_get_db()).explain(request)
    return {
        "status": "ok",
        "model_utilitzat": response.model_utilitzat,
        "resum_executiu": response.resum_executiu,
        "explicacio_funcional": response.explicacio_funcional,
        "explicacio_tecnica": response.explicacio_tecnica,
        "impacte": response.impacte,
        "riscos": response.riscos,
        "canvis_respecte_anterior": response.canvis_respecte_anterior,
        "recomanacio_revisio": response.recomanacio_revisio,
        "nivell_confianca": response.nivell_confianca,
        "advertiments": response.advertiments,
        "bloc_auditoria_md": response.bloc_auditoria_md,
        "linia_consultes_txt": response.linia_consultes_txt,
        "explicacio_check_text": response.explicacio_check_text,
        "explicacio_preview_text": getattr(response, "explicacio_preview_text", response.explicacio_check_text),
    }


def _get_projecte_root() -> str:
    """Localitza la carpeta arrel del projecte (on hi ha auditoria_post_crq.md)."""
    import os
    from pathlib import Path
    # Estratègia: pujar fins trobar el fitxer
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "auditoria_post_crq.md").exists():
            return str(parent)
    # Fallback: directori de treball
    return str(Path.cwd())


_DEFINE_ASSIGNMENT_RE = re.compile(
    r"^\s*DEFINE\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_AMPERSAND_VAR_RE = re.compile(r"&([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _default_codex_engine_variables() -> Dict[str, str]:
    end_dt = utc_now()
    start_dt = end_dt - timedelta(days=1)
    return {
        "START_AT": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "END_AT": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "START_DATE": start_dt.strftime("%Y-%m-%d"),
        "END_DATE": end_dt.strftime("%Y-%m-%d"),
    }


def _extract_define_assignments(sql_text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for name, raw_value in _DEFINE_ASSIGNMENT_RE.findall(sql_text or ""):
        normalized = str(raw_value or "").strip()
        if normalized.startswith("'") and normalized.endswith("'") and len(normalized) >= 2:
            normalized = normalized[1:-1]
        values[str(name).upper()] = normalized
    return values


def _extract_ampersand_variables(sql_text: str) -> List[str]:
    seen: List[str] = []
    for name in _AMPERSAND_VAR_RE.findall(sql_text or ""):
        upper_name = str(name).upper()
        if upper_name not in seen:
            seen.append(upper_name)
    return seen


def _ensure_select_query(sql_text: str) -> None:
    stripped = re.sub(r"/\*.*?\*/", " ", sql_text or "", flags=re.DOTALL)
    stripped = re.sub(r"--.*?$", " ", stripped, flags=re.MULTILINE).strip()
    first_match = re.match(r"([A-Za-z]+)", stripped or "")
    first_token = first_match.group(1).upper() if first_match else ""
    if first_token not in {"SELECT", "WITH"}:
        raise HTTPException(
            status_code=400,
            detail="Només es permeten consultes SELECT/WITH al motor de comparació.",
        )


def _unique_column_names(columns: List[str]) -> List[str]:
    unique: List[str] = []
    counters: Dict[str, int] = {}
    for raw_name in columns:
        base_name = str(raw_name or "COLUMN").strip() or "COLUMN"
        current_count = counters.get(base_name, 0) + 1
        counters[base_name] = current_count
        unique.append(base_name if current_count == 1 else f"{base_name}__{current_count}")
    return unique


def _serialize_oracle_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            if hasattr(value, "hour"):
                return value.isoformat(sep=" ", timespec="seconds")
            return value.isoformat()
        except TypeError:
            return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _prepare_sql_for_codex_engine(sql_text: str, *, side: str) -> Dict[str, Any]:
    raw_sql = str(sql_text or "")
    if not raw_sql.strip():
        raise HTTPException(status_code=400, detail="La consulta SQL no pot estar buida.")

    transform_result = transform_for_codex(raw_sql, debug=True)
    prepared_sql = transform_result.sql if side == "left" else raw_sql.strip().rstrip(";")
    define_values = _extract_define_assignments(raw_sql)
    variables_detected = _extract_ampersand_variables(prepared_sql)
    _ensure_select_query(prepared_sql)
    return {
        "raw_sql": raw_sql,
        "prepared_sql": prepared_sql,
        "transform_logs": transform_result.changes if side == "left" else [],
        "define_values": define_values,
        "variables_detected": variables_detected,
    }


def _sql_ampersands_to_binds(sql_text: str) -> str:
    return _AMPERSAND_VAR_RE.sub(lambda match: f":{match.group(1)}", sql_text or "")


def _resolve_execution_variables(
    prepared: Dict[str, Any],
    variables: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    resolved = {k.upper(): v for k, v in _default_codex_engine_variables().items()}
    for key, value in (prepared.get("define_values") or {}).items():
        resolved[str(key).upper()] = str(value)
    for key, value in (variables or {}).items():
        if value is None:
            continue
        resolved[str(key).upper()] = str(value)
    missing = [name for name in prepared.get("variables_detected") or [] if str(resolved.get(name, "")).strip() == ""]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Falten valors per a les variables: {', '.join(missing)}",
        )
    return {name: resolved[name] for name in prepared.get("variables_detected") or []}


def _execute_codex_engine_side(
    *,
    sql_text: str,
    side: str,
    profile_name: Optional[str],
    variables: Optional[Dict[str, str]] = None,
    preview_limit: int = 100,
) -> Dict[str, Any]:
    prepared = _prepare_sql_for_codex_engine(sql_text, side=side)
    binds = _resolve_execution_variables(prepared, variables)
    executable_sql = _sql_ampersands_to_binds(prepared["prepared_sql"])

    selected_profile, profile_params = _resolve_oracle_profile(profile_name)
    dbm = OracleDBManager(profile_params)
    start_time = time.perf_counter()
    try:
        rows, columns = dbm.execute_query(executable_sql, binds)
        execution_ms = int((time.perf_counter() - start_time) * 1000)
        if rows is None or columns is None:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_ms": execution_ms,
                "error": dbm.last_error or "Error executant la consulta.",
                "profile": selected_profile,
                "prepared_sql": prepared["prepared_sql"],
                "executed_sql": executable_sql,
                "variables_detected": prepared["variables_detected"],
                "variables_used": binds,
                "transform_logs": prepared["transform_logs"],
                "preview_limited": False,
            }

        unique_columns = _unique_column_names(list(columns))
        serialized_rows = [
            {column_name: _serialize_oracle_value(row[idx]) for idx, column_name in enumerate(unique_columns)}
            for row in rows
        ]
        return {
            "success": True,
            "columns": unique_columns,
            "rows": serialized_rows[:preview_limit],
            "full_rows": serialized_rows,
            "row_count": len(serialized_rows),
            "execution_ms": execution_ms,
            "error": None,
            "profile": selected_profile,
            "prepared_sql": prepared["prepared_sql"],
            "executed_sql": executable_sql,
            "variables_detected": prepared["variables_detected"],
            "variables_used": binds,
            "transform_logs": prepared["transform_logs"],
            "preview_limited": len(serialized_rows) > preview_limit,
        }
    finally:
        dbm.close()


def _strip_full_rows(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("full_rows", None)
    return cleaned


def _normalize_codex_engine_options(options: CodexEngineComparisonOptions) -> Dict[str, Any]:
    options_payload = options.model_dump() if hasattr(options, "model_dump") else options.dict()
    return {
        **default_comparison_options(),
        **options_payload,
    }


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _analyze_codex_engine_differences_with_ai(
    *,
    left_sql: str,
    right_sql: str,
    left: Dict[str, Any],
    right: Dict[str, Any],
    comparison: Dict[str, Any],
) -> Dict[str, Any]:
    assistant = AIAssistant()
    assistant.master_prompt = (
        "Eres un ingeniero senior de Oracle SQL y validación de equivalencia entre consultas. "
        "Debes basarte solo en los hechos proporcionados. "
        "Si no hay evidencia suficiente para una causa, dilo explícitamente. "
        "Responde solo con JSON válido en español con las claves: summary, possible_causes, recommendation."
    )
    prompt = json.dumps(
        {
            "left_sql": left_sql,
            "right_sql": right_sql,
            "left_result": {
                "success": left.get("success"),
                "row_count": left.get("row_count"),
                "columns": left.get("columns"),
                "execution_ms": left.get("execution_ms"),
                "error": left.get("error"),
                "rows_sample": left.get("rows")[:5] if isinstance(left.get("rows"), list) else [],
            },
            "right_result": {
                "success": right.get("success"),
                "row_count": right.get("row_count"),
                "columns": right.get("columns"),
                "execution_ms": right.get("execution_ms"),
                "error": right.get("error"),
                "rows_sample": right.get("rows")[:5] if isinstance(right.get("rows"), list) else [],
            },
            "comparison": {
                "status": comparison.get("status"),
                "match": comparison.get("match"),
                "structure_match": comparison.get("structure_match"),
                "row_count_match": comparison.get("row_count_match"),
                "content_match": comparison.get("content_match"),
                "order_match": comparison.get("order_match"),
                "summary": comparison.get("summary"),
                "left_only_columns": comparison.get("left_only_columns"),
                "right_only_columns": comparison.get("right_only_columns"),
                "only_in_left": (comparison.get("only_in_left") or [])[:5],
                "only_in_right": (comparison.get("only_in_right") or [])[:5],
                "value_differences": (comparison.get("value_differences") or [])[:5],
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    raw_response = assistant.generate_response(
        "Analiza estas diferencias SQL y explica solo lo que esté respaldado por la evidencia.\n\n" + prompt,
        timeout=45,
    )
    if raw_response.startswith("⚠️"):
        return {
            "status": "unavailable",
            "summary": "",
            "possible_causes": [],
            "recommendation": "",
            "error": raw_response,
        }
    if raw_response.startswith("❌"):
        return {
            "status": "error",
            "summary": "",
            "possible_causes": [],
            "recommendation": "",
            "error": raw_response,
        }

    parsed = _extract_json_object(raw_response)
    if not parsed:
        return {
            "status": "error",
            "summary": "",
            "possible_causes": [],
            "recommendation": "",
            "error": "La IA no ha retornat un JSON vàlid.",
            "raw_response": raw_response,
        }
    return {
        "status": "ok",
        "summary": str(parsed.get("summary") or "").strip(),
        "possible_causes": list(parsed.get("possible_causes") or []),
        "recommendation": str(parsed.get("recommendation") or "").strip(),
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[CheckResponse])
def list_checks() -> List[Dict[str, Any]]:
    """Retorna tots els checks actius amb el seu estat de versió i sincronització."""
    db = _get_db()
    with sqlite3.connect(db) as conn:
        _ensure_checks_schema(conn)
        conn.row_factory = sqlite3.Row
        try:
            _sync_checks_catalog_from_markdown(conn)
            conn.commit()
        except Exception as exc:
            logger.warning("No s'ha pogut sincronitzar el catàleg de checks des del Markdown", exc_info=exc)
        checks = conn.execute(
            "SELECT * FROM audit_checks WHERE actiu = 1 ORDER BY ordre ASC"
        ).fetchall()
        result = []
        for c in checks:
            check_dict = dict(c)
            check_dict.setdefault("ai_enabled", 0)
            # Versió vigent
            ver = conn.execute(
                "SELECT id, versio, sql_text FROM consulta_versions WHERE check_id = ? AND es_vigent = 1",
                (c["check_id"],),
            ).fetchone()
            check_dict["versio_vigent"] = ver["versio"] if ver else None
            check_dict["sql_vigent"]    = ver["sql_text"] if ver else None

            # Estat explicació
            check_dict["estat_explicacio"] = _resolve_current_explanation_status(
                conn,
                check_id=c["check_id"],
                current_version_id=(ver["id"] if ver else None),
            )

            # Estat sync
            for fitxer, clau in [("auditoria_post_crq.md", "estat_sync_md"),
                                  ("consultes_post_crq.txt", "estat_sync_txt")]:
                sf = conn.execute(
                    "SELECT estat FROM sincronitzacio_fitxers WHERE check_id = ? AND fitxer = ?",
                    (c["check_id"], fitxer),
                ).fetchone()
                check_dict[clau] = sf["estat"] if sf else None

            result.append(check_dict)
    return result


@router.post("/validate-preview")
def validate_check_preview(data: CheckValidationRequest) -> Dict[str, Any]:
    """Executa una prevalidació Oracle del check i genera una previsualització IA sense persistir canvis."""
    if not str(data.sql_text or "").strip():
        raise HTTPException(status_code=400, detail="La consulta SQL no pot estar buida.")
    if str(data.tipus or "SQL").strip().upper() != "SQL":
        raise HTTPException(status_code=400, detail="La prevalidació només està disponible per a checks SQL.")

    selected_profile, profile_params = _resolve_oracle_profile(data.profile)
    try:
        if str(data.validation_start_at or "").strip() and str(data.validation_end_at or "").strip():
            days_back, normalized_filter = _days_back_from_filter(
                {
                    "mode": "range",
                    "start_date": str(data.validation_start_at).strip(),
                    "end_date": str(data.validation_end_at).strip(),
                },
                reference_dt=utc_now(),
            )
        else:
            days_back = 1
            normalized_filter = _default_validation_time_filter()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    check_payload = {
        "check_id": data.check_id,
        "title": data.titol,
        "severitat": data.severitat_base,
        "criteri": data.context_check or data.titol,
        "sql": data.sql_text,
    }

    dbm = OracleDBManager(profile_params)
    try:
        validation = _run_single_post_crq_check(
            check_payload,
            db_manager=dbm,
            normalized_filter=normalized_filter,
            cleaned_schemas=[],
            days_back=days_back,
            source_file="checks_admin_preview",
        )
    finally:
        dbm.close()

    full_rows = list(validation.get("rows") or [])
    preview_limit = 25
    validation["preview_row_count"] = min(len(full_rows), preview_limit)
    validation["preview_limited"] = len(full_rows) > preview_limit
    validation["rows"] = full_rows[:preview_limit]

    if validation.get("status") != "ok":
        return {
            "status": "error",
            "profile": selected_profile,
            "time_filter": normalized_filter,
            "validation": validation,
            "ai_preview": {"status": "skipped", "reason": "validation_failed"},
        }

    with sqlite3.connect(_get_db()) as conn:
        conn.row_factory = sqlite3.Row
        try:
            ai_preview = _preview_ai_explanation(
                conn=conn,
                check_id=data.check_id,
                titol=data.titol,
                severitat_base=data.severitat_base,
                sql_text=data.sql_text,
                parametres=data.parametres,
                context_check=data.context_check,
                tipus=data.tipus,
            )
        except (sqlite3.Error, RuntimeError, ValueError, TypeError, AttributeError, requests.RequestException) as exc:
            return {
                "status": "error",
                "profile": selected_profile,
                "time_filter": normalized_filter,
                "validation": validation,
                "ai_preview": {"status": "error", "error": str(exc)},
            }

    return {
        "status": "ok",
        "profile": selected_profile,
        "time_filter": normalized_filter,
        "validation": validation,
        "ai_preview": ai_preview,
    }


@router.post("/transform-sql")
def transform_sql_endpoint(data: SQLTransformRequest) -> Dict[str, Any]:
    """Transforma una consulta SQL d'Oracle per a Codex."""
    try:
        if not data.sql_text.strip():
            return {"status": "ok", "transformed_sql": "", "logs": []}
            
        res = transform_for_codex(data.sql_text, debug=data.debug)
        if data.debug:
            return {
                "status": "ok",
                "transformed_sql": res.sql,
                "logs": res.changes
            }
        else:
            return {
                "status": "ok",
                "transformed_sql": res,
                "logs": []
            }
    except Exception as e:
        logger.error(f"Error transformant SQL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/codex-engine/execute")
def codex_engine_execute(data: CodexEngineExecuteRequest) -> Dict[str, Any]:
    side = str(data.side or "right").strip().lower()
    if side not in {"left", "right"}:
        raise HTTPException(status_code=400, detail="El costat d'execució ha de ser 'left' o 'right'.")
    result = _execute_codex_engine_side(
        sql_text=data.sql_text,
        side=side,
        profile_name=data.profile,
        variables=data.variables,
        preview_limit=data.preview_limit,
    )
    return {"side": side, "result": _strip_full_rows(result)}


@router.post("/codex-engine/execute-both")
def codex_engine_execute_both(data: CodexEngineExecuteBothRequest) -> Dict[str, Any]:
    left = _execute_codex_engine_side(
        sql_text=data.left_sql,
        side="left",
        profile_name=data.profile,
        variables=data.variables,
        preview_limit=data.preview_limit,
    )
    right = _execute_codex_engine_side(
        sql_text=data.right_sql,
        side="right",
        profile_name=data.profile,
        variables=data.variables,
        preview_limit=data.preview_limit,
    )
    return {"left": _strip_full_rows(left), "right": _strip_full_rows(right)}


@router.post("/codex-engine/compare")
def codex_engine_compare(data: CodexEngineCompareRequest) -> Dict[str, Any]:
    options = _normalize_codex_engine_options(data.options)
    left = _execute_codex_engine_side(
        sql_text=data.left_sql,
        side="left",
        profile_name=data.profile,
        variables=data.variables,
        preview_limit=options["preview_limit"],
    )
    right = _execute_codex_engine_side(
        sql_text=data.right_sql,
        side="right",
        profile_name=data.profile,
        variables=data.variables,
        preview_limit=options["preview_limit"],
    )
    comparison = compare_query_results(
        {**left, "rows": left.get("full_rows") or []},
        {**right, "rows": right.get("full_rows") or []},
        options,
    )
    return {
        "left": _strip_full_rows(left),
        "right": _strip_full_rows(right),
        "comparison": comparison,
    }


@router.post("/codex-engine/analyze")
def codex_engine_analyze(data: CodexEngineAnalyzeRequest) -> Dict[str, Any]:
    return {
        "ai_analysis": _analyze_codex_engine_differences_with_ai(
            left_sql=data.left_sql,
            right_sql=data.right_sql,
            left=data.left,
            right=data.right,
            comparison=data.comparison,
        )
    }


@router.get("/{check_id}", response_model=CheckResponse)
def get_check(check_id: str) -> Dict[str, Any]:
    """Retorna el detall d'un check amb la versió SQL vigent."""
    db = _get_db()
    with sqlite3.connect(db) as conn:
        _ensure_checks_schema(conn)
        conn.row_factory = sqlite3.Row
        try:
            _sync_checks_catalog_from_markdown(conn)
            conn.commit()
        except Exception as exc:
            logger.warning("No s'ha pogut sincronitzar el check %s des del Markdown", check_id, exc_info=exc)
        check = _get_check_or_404(conn, check_id)
        check.setdefault("ai_enabled", 0)
        ver = conn.execute(
            "SELECT id, versio, sql_text FROM consulta_versions WHERE check_id = ? AND es_vigent = 1",
            (check_id,),
        ).fetchone()
        check["versio_vigent"] = ver["versio"] if ver else None
        check["sql_vigent"]    = ver["sql_text"] if ver else None
        check["estat_explicacio"] = _resolve_current_explanation_status(
            conn,
            check_id=check_id,
            current_version_id=(ver["id"] if ver else None),
        )
        return dict(check)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_check(data: CheckCreate, bg: BackgroundTasks) -> Dict[str, Any]:
    """Crea un nou check i desencadena la generació d'explicació IA en segon pla."""
    if data.severitat_base not in SEVERITATS_VALIDES:
        raise HTTPException(400, f"Severitat invàlida. Valors acceptats: {SEVERITATS_VALIDES}")

    db = _get_db()
    ara = utc_now_iso()
    with sqlite3.connect(db) as conn:
        _ensure_checks_schema(conn)
        # Comprovar que no existeix
        existing = conn.execute(
            "SELECT check_id FROM audit_checks WHERE check_id = ?", (data.check_id,)
        ).fetchone()
        if existing:
            raise HTTPException(409, f"El check '{data.check_id}' ja existeix.")

        conn.execute(
            """INSERT INTO audit_checks
               (check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, ai_enabled, creat_en, actualitzat_en)
               VALUES (?,?,?,?,?,?,1,?,?,?,?)""",
            (data.check_id, data.titol, data.severitat_base, data.parametres,
             data.tipus, data.ordre, data.context_check, data.ai_enabled, ara, ara),
        )
        versio = _next_versio(conn, data.check_id)
        conn.execute(
            """INSERT INTO consulta_versions (check_id, versio, sql_text, checksum, creat_per, es_vigent)
               VALUES (?,?,?,?,'usuari',1)""",
            (data.check_id, versio, data.sql_text, _sql_version_checksum(data.sql_text)),
        )
        version_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

    # Marcar sync com PENDENT
    svc = QuerySyncService(_get_projecte_root(), db)
    svc.mark_pending(data.check_id)

    # Generar explicació IA en segon pla
    bg.add_task(_regenerate_explanation, data.check_id, version_id)

    return {"check_id": data.check_id, "versio": versio, "estat": "creat"}


@router.put("/{check_id}")
def update_check(check_id: str, data: CheckUpdate, bg: BackgroundTasks) -> Dict[str, Any]:
    """
    Actualitza un check. Si el SQL canvia, crea una nova versió i
    desencadena regeneració de l'explicació IA.
    """
    db = _get_db()
    ara = utc_now_iso()
    with sqlite3.connect(db) as conn:
        _ensure_checks_schema(conn)
        conn.row_factory = sqlite3.Row
        check = _get_check_or_404(conn, check_id)
        nova_versio_id = None

        # Actualitzar camps del check
        updates: dict = {}
        if data.titol is not None:
            updates["titol"] = data.titol
        if data.severitat_base is not None:
            if data.severitat_base not in SEVERITATS_VALIDES:
                raise HTTPException(400, "Severitat invàlida.")
            updates["severitat_base"] = data.severitat_base
        if data.parametres is not None:
            updates["parametres"] = data.parametres
        if data.context_check is not None:
            updates["context_check"] = data.context_check
        if data.ai_enabled is not None:
            updates["ai_enabled"] = data.ai_enabled
        updates["actualitzat_en"] = ara

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE audit_checks SET {set_clause} WHERE check_id = ?",
                (*updates.values(), check_id),
            )

        # Si ha canviat el SQL → nova versió
        if data.sql_text is not None:
            nou_checksum = _sql_version_checksum(data.sql_text)
            ver_actual = conn.execute(
                "SELECT id, sql_text, versio FROM consulta_versions WHERE check_id = ? AND es_vigent = 1",
                (check_id,),
            ).fetchone()

            if ver_actual and ver_actual["checksum" if "checksum" in ver_actual.keys() else 0]:
                pass  # comprovem per sha
            if ver_actual and _sql_version_checksum(ver_actual["sql_text"]) != nou_checksum:
                # Desactivar versió actual
                conn.execute(
                    "UPDATE consulta_versions SET es_vigent = 0 WHERE check_id = ? AND es_vigent = 1",
                    (check_id,),
                )
                versio = _next_versio(conn, check_id)
                conn.execute(
                    """INSERT INTO consulta_versions (check_id, versio, sql_text, checksum, creat_per, es_vigent)
                       VALUES (?,?,?,?,'usuari',1)""",
                    (check_id, versio, data.sql_text, nou_checksum),
                )
                nova_versio_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Marcar explicació anterior com OBSOLETA
                conn.execute(
                    "UPDATE explicacions SET estat = 'OBSOLETA' WHERE check_id = ? AND estat = 'VIGENT'",
                    (check_id,),
                )

        conn.commit()

    if nova_versio_id:
        svc = QuerySyncService(_get_projecte_root(), db)
        svc.mark_pending(check_id)
        bg.add_task(_regenerate_explanation, check_id, nova_versio_id)
        return {"check_id": check_id, "estat": "actualitzat", "nova_versio": True}

    return {"check_id": check_id, "estat": "actualitzat", "nova_versio": False}


@router.delete("/{check_id}", status_code=status.HTTP_200_OK)
def delete_check(check_id: str) -> Dict[str, Any]:
    """Elimina completament un check (HARD DELETE) i reordena els fitxers .txt / .md."""
    check_id = check_id.upper()
    db = _get_db()
    
    # 1. Obtenir directori principal (arrel)
    root = _get_projecte_root()
    if not root:
        root = os.getcwd() # en el pitjor dels casos

    project_root = Path(root)
    md_file = project_root / 'auditoria_post_crq.md'
    txt_file = project_root / 'consultes_post_crq.txt'
    backup_dir = project_root / 'backup_audits'

    mapping: dict[str, str] = {}
    backup_md = None
    backup_txt = None
    md_tmp = None
    txt_tmp = None
    original_md = md_file.read_text(encoding='utf-8') if md_file.exists() else None
    original_txt = txt_file.read_text(encoding='utf-8') if txt_file.exists() else None

    with sqlite3.connect(db) as conn:
        _ensure_checks_schema(conn)
        conn.row_factory = sqlite3.Row
        _get_check_or_404(conn, check_id)

        auxiliary_tables = [
            "consulta_versions",
            "explicacions",
            "sincronitzacio_fitxers",
            "regeneracio_log",
        ]
        existing_aux_tables = [table for table in auxiliary_tables if _table_exists(conn, table)]

        def remap_check_ids(table_name: str, old_to_new: dict[str, str]) -> None:
            for old_id, new_id in old_to_new.items():
                if old_id != new_id:
                    conn.execute(
                        f"UPDATE {table_name} SET check_id = ? WHERE check_id = ?",
                        (f"{new_id}_TMP", old_id),
                    )
            for old_id, new_id in old_to_new.items():
                if old_id != new_id:
                    conn.execute(
                        f"UPDATE {table_name} SET check_id = ? WHERE check_id = ?",
                        (new_id, f"{new_id}_TMP"),
                    )

        try:
            conn.execute("DELETE FROM audit_checks WHERE check_id = ?", (check_id,))
            for table in existing_aux_tables:
                conn.execute(f"DELETE FROM {table} WHERE check_id = ?", (check_id,))

            active_checks = [
                r["check_id"]
                for r in conn.execute("SELECT check_id FROM audit_checks ORDER BY check_id ASC").fetchall()
            ]
            mapping = {old_id: f"CHECK_{idx:02d}" for idx, old_id in enumerate(active_checks, start=1)}

            for table in ["audit_checks", *existing_aux_tables]:
                remap_check_ids(table, mapping)

            if original_md is not None and original_txt is not None:
                backup_dir.mkdir(exist_ok=True)
                t = utc_now().strftime('%Y%m%d_%H%M%S')
                backup_md = backup_dir / f'auditoria_{t}.md'
                backup_txt = backup_dir / f'consultes_{t}.txt'
                shutil.copy2(md_file, backup_md)
                shutil.copy2(txt_file, backup_txt)

                blocks = re.split(r'(?=###\s+CHECK_\d+)', original_md, flags=re.IGNORECASE)
                filtered_md_blocks = []
                for block in blocks:
                    match = re.search(r'###\s+(CHECK_\d+)', block, re.IGNORECASE)
                    if match and match.group(1).upper() == check_id:
                        continue
                    filtered_md_blocks.append(block)
                clean_md_content = ''.join(filtered_md_blocks)

                txt_blocks = re.split(r'(?m)^(?=CHECK_\d+\s*\|)', original_txt)
                filtered_txt_blocks = []
                for block in txt_blocks:
                    match = re.search(r'^(CHECK_\d+)\s*\|', block, re.IGNORECASE)
                    if match and match.group(1).upper() == check_id:
                        continue
                    filtered_txt_blocks.append(block)
                clean_txt_content = ''.join(filtered_txt_blocks)

                for old_check, new_check in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
                    if old_check != new_check:
                        clean_md_content = re.sub(rf'\b{old_check}\b', new_check, clean_md_content)
                        clean_txt_content = re.sub(rf'\b{old_check}\b', new_check, clean_txt_content)

                md_tmp = md_file.with_suffix(md_file.suffix + ".tmp")
                txt_tmp = txt_file.with_suffix(txt_file.suffix + ".tmp")
                md_tmp.write_text(clean_md_content, encoding='utf-8')
                txt_tmp.write_text(clean_txt_content.strip() + '\n', encoding='utf-8')
                os.replace(md_tmp, md_file)
                os.replace(txt_tmp, txt_file)

            conn.commit()
        except (sqlite3.Error, OSError, shutil.Error, ValueError) as exc:
            logger.error("Error eliminant el check %s; s'aplica rollback", check_id, exc_info=exc)
            conn.rollback()
            if md_tmp and md_tmp.exists():
                md_tmp.unlink(missing_ok=True)
            if txt_tmp and txt_tmp.exists():
                txt_tmp.unlink(missing_ok=True)
            if backup_md and backup_md.exists():
                shutil.copy2(backup_md, md_file)
            if backup_txt and backup_txt.exists():
                shutil.copy2(backup_txt, txt_file)
            raise

    return {"check_id": check_id, "estat": "eliminat, backup i seqüeles de reordenació realitzades amb èxit."}


@router.get("/{check_id}/history")
def get_history(check_id: str) -> List[Dict[str, Any]]:
    """Retorna l'historial de versions de la consulta d'un check."""
    db = _get_db()
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT v.id, v.versio, v.checksum, v.creat_per, v.creat_en, v.es_vigent,
                      e.estat AS estat_explicacio, e.model_utilitzat, e.nivell_confianca
               FROM consulta_versions v
               LEFT JOIN explicacions e ON e.consulta_version_id = v.id AND e.estat = 'VIGENT'
               WHERE v.check_id = ?
               ORDER BY v.versio DESC""",
            (check_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{check_id}/regenerate")
def regenerate_explanation(check_id: str, bg: BackgroundTasks) -> Dict[str, Any]:
    """Força la regeneració de l'explicació IA per a un check existent."""
    db = _get_db()
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        _get_check_or_404(conn, check_id)
        ver = conn.execute(
            "SELECT id FROM consulta_versions WHERE check_id = ? AND es_vigent = 1",
            (check_id,),
        ).fetchone()
        if not ver:
            raise HTTPException(400, "No hi ha cap versió vigent per regenerar.")
        version_id = ver["id"]

    bg.add_task(_regenerate_explanation, check_id, version_id)
    return {"check_id": check_id, "estat": "regeneracio_encuada"}


@router.get("/{check_id}/sync-status")
def get_sync_status(check_id: str) -> List[Dict[str, Any]]:
    """Retorna l'estat de sincronització dels fitxers derivats d'un check."""
    db = _get_db()
    svc = QuerySyncService(_get_projecte_root(), db)
    return svc.get_sync_status(check_id)


# ─── Tasca de fons: regeneració IA ───────────────────────────────────────────

def _regenerate_explanation(check_id: str, version_id: int) -> None:
    """
    Tasca asíncrona que invoca el DBAQueryExplainer i sincronitza
    el resultat als fitxers derivats.
    """
    db = _get_db()
    try:
        check, ver_nova, ver_ant = _load_regeneration_context(db, check_id, version_id)
    except LookupError as exc:
        error_message = str(exc)
        logger.error("[Regeneraci?][load] %s", error_message)
        _record_regeneration_error(
            db,
            check_id=check_id,
            version_id=version_id,
            error_message=error_message,
        )
        return
    except sqlite3.Error as exc:
        logger.error("[Regeneraci?][load] Error carregant context per %s", check_id, exc_info=exc)
        _record_regeneration_error(
            db,
            check_id=check_id,
            version_id=version_id,
            error_message=str(exc),
        )
        return

    try:
        params = [p.strip() for p in (check["parametres"] or "").split(",") if p.strip()]
        req = DBAExplainRequest(
            check_id=check_id,
            titol=check["titol"],
            severitat=check["severitat_base"],
            sql_nou=ver_nova["sql_text"],
            versio_nova=ver_nova["versio"],
            parametres=params,
            sql_anterior=ver_ant["sql_text"] if ver_ant else None,
            context_check=check["context_check"] or "",
            tipus=check["tipus"],
        )

        explainer = DBAQueryExplainer(db_path=db)
        resp = explainer.explain(req)
    except (AttributeError, TypeError, ValueError, RuntimeError, requests.RequestException) as exc:
        logger.error("[Regeneraci?][explain] Error per check %s: %s", check_id, exc, exc_info=True)
        _record_regeneration_error(
            db,
            check_id=check_id,
            version_id=version_id,
            error_message=str(exc),
        )
        return

    try:
        _persist_regenerated_explanation(
            db,
            check_id=check_id,
            version_id=version_id,
            response=resp,
        )
    except sqlite3.Error as exc:
        logger.error("[Regeneraci?][persist] Error persistint explicaci? per %s", check_id, exc_info=exc)
        _record_regeneration_error(
            db,
            check_id=check_id,
            version_id=version_id,
            error_message=str(exc),
        )
        return

    try:
        svc = QuerySyncService(_get_projecte_root(), db)
        sync_result = svc.sync_check(
            check_id,
            resp.bloc_auditoria_md,
            resp.linia_consultes_txt,
            getattr(resp, "explicacio_check_text", None),
        )
        if sync_result.get("errors"):
            raise RuntimeError(" | ".join(sync_result["errors"]))
    except (sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
        logger.error("[Regeneraci?][sync] Error sincronitzant check %s", check_id, exc_info=exc)
        _record_regeneration_error(
            db,
            check_id=check_id,
            version_id=version_id,
            error_message=str(exc),
        )
        return

    logger.info("[Regeneració] Check %s regenerat OK amb model %s (confiança: %.2f)",
                check_id, resp.model_utilitzat, resp.nivell_confianca)
