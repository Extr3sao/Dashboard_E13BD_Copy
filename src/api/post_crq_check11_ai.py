import json
from typing import Any, Dict, List, Optional, Tuple

from src.core.config_loader import ConfigLoader
from src.core.openrouter_client import OpenRouterClient, OpenRouterSettings


CHECK_11_AI_SYSTEM_PROMPT = """
Eres un auditor experto en Oracle PL/SQL, tuning, procesamiento masivo y detección de malas prácticas N+1.
Analizas resultados heurísticos del CHECK 11.
No inventes contexto ausente.
Sé conservador.
Si la evidencia es insuficiente, clasifica como revision_manual.
Solo usa mala_praxis cuando haya señales claras de procesamiento fila a fila evitable.
Solo usa falso_positivo cuando existan indicios razonables de bajo impacto o falso alarmado heurístico.
Devuelve siempre JSON válido.
No sustituyes al auditor humano: eres apoyo técnico.
""".strip()


def _check11_item_key(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(item.get("esquema") or item.get("ESQUEMA") or "").strip().upper(),
        str(item.get("objecte_plsql") or item.get("OBJECTE_PLSQL") or item.get("objecte") or "").strip().upper(),
        str(item.get("tipus_objecte") or item.get("TIPUS_OBJECTE") or item.get("tipus") or "").strip().upper(),
    )


def build_check11_ai_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = []
    for row in rows:
        items.append(
            {
                "esquema": row.get("ESQUEMA") or row.get("esquema"),
                "objecte_plsql": row.get("OBJECTE_PLSQL") or row.get("objecte_plsql") or row.get("OBJECTE"),
                "tipus_objecte": row.get("TIPUS_OBJECTE") or row.get("tipus_objecte") or row.get("TIPUS"),
                "data_modificacio_objecte": row.get("DATA_MODIFICACIO_OBJECTE") or row.get("data_modificacio_objecte"),
                "linies_sospitoses_en_loop": row.get("LINIES_SOSPITOSES_EN_LOOP") or row.get("linies_sospitoses_en_loop"),
                "total_linies_codi": row.get("TOTAL_LINIES_CODI") or row.get("total_linies_codi"),
                "severitat_sql": row.get("SEVERITAT_SQL") or row.get("severitat_sql") or row.get("SEVERITAT"),
                "observacio": row.get("OBSERVACIO") or row.get("observacio"),
                "linies_detall": row.get("LINIES_DETALL") or row.get("linies_detall"),
            }
        )
    return {
        "instruction": (
            "Analiza los siguientes hallazgos del CHECK 11. Para cada ítem clasifica en una de: "
            "falso_positivo, mala_praxis, revision_manual. "
            "Devuelve JSON válido con el schema solicitado."
        ),
        "check_id": "CHECK_11",
        "items": items,
    }


def validate_check11_ai_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("openrouter_response_not_object")
    if payload.get("check_id") != "CHECK_11":
        raise ValueError("check_id_invalid")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary_missing")
    for key in ("total_findings", "mala_praxis", "falso_positivo", "revision_manual"):
        if not isinstance(summary.get(key), int):
            raise ValueError(f"summary_field_invalid:{key}")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items_missing")
    validated_items = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("item_invalid")
        for key in (
            "esquema",
            "objecte_plsql",
            "tipus_objecte",
            "severitat_sql",
            "classificacio_ia",
            "confianca_ia",
            "explicacio_ia",
            "recomanacio_ia",
        ):
            if key not in item:
                raise ValueError(f"item_field_missing:{key}")
        if item["classificacio_ia"] not in {"mala_praxis", "falso_positivo", "revision_manual"}:
            raise ValueError("classificacio_ia_invalid")
        if not isinstance(item["confianca_ia"], int):
            raise ValueError("confianca_ia_invalid")
        validated_items.append(item)
    return {"check_id": "CHECK_11", "summary": summary, "items": validated_items}


def analyze_check11_results(
    rows: List[Dict[str, Any]],
    client: Optional[OpenRouterClient] = None,
    config: Optional[ConfigLoader] = None,
) -> Dict[str, Any]:
    config = config or ConfigLoader()
    settings = client.settings if client is not None else OpenRouterSettings.from_config(config)
    if not rows:
        return {
            "enabled": settings.enabled,
            "called": False,
            "status": "skipped_no_rows",
            "items": [],
            "summary": None,
        }
    if not settings.enabled or not settings.api_key:
        return {
            "enabled": settings.enabled,
            "called": False,
            "status": "no disponible",
            "error": "openrouter_disabled",
            "items": [],
            "summary": None,
        }

    client = client or OpenRouterClient(settings=settings, config=config)
    
    chunk_size_raw = config.get_env_var("CHECK11_AI_CHUNK_SIZE", "15")
    try:
        chunk_size = int(chunk_size_raw)
    except ValueError:
        chunk_size = 15

    all_validated_items = []
    final_status = "ok"
    final_model = None
    final_selection = {}

    for i in range(0, len(rows), chunk_size):
        chunk_rows = rows[i:i + chunk_size]
        payload = build_check11_ai_payload(chunk_rows)
        response = client.chat_completion(CHECK_11_AI_SYSTEM_PROMPT, payload)
        
        if not response.get("ok"):
            final_status = response.get("status") or "no disponible"
            return {
                "enabled": True,
                "called": True,
                "status": response.get("status") or "no disponible",
                "error": response.get("error") or "openrouter_error",
                "model": response.get("model"),
                "selection": response.get("selection") or {},
                "items": [],
                "summary": None,
            }

        try:
            parsed = json.loads(response["content"])
            validated = validate_check11_ai_response(parsed)
            all_validated_items.extend(validated["items"])
            final_model = response.get("model")
            final_selection = response.get("selection") or {}
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            return {
                "enabled": True,
                "called": True,
                "status": "no disponible",
                "error": str(exc),
                "model": response.get("model"),
                "selection": response.get("selection") or {},
                "items": [],
                "summary": None,
            }

    summary = {
        "total_findings": len(all_validated_items),
        "mala_praxis": sum(1 for item in all_validated_items if item.get("classificacio_ia") == "mala_praxis"),
        "falso_positivo": sum(1 for item in all_validated_items if item.get("classificacio_ia") == "falso_positivo"),
        "revision_manual": sum(1 for item in all_validated_items if item.get("classificacio_ia") == "revision_manual")
    }

    return {
        "enabled": True,
        "called": True,
        "status": final_status,
        "model": final_model,
        "selection": final_selection,
        "items": all_validated_items,
        "summary": summary,
    }


def merge_check11_ai_results(rows: List[Dict[str, Any]], ai_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    merged_rows: List[Dict[str, Any]] = []
    lookup = {
        _check11_item_key(item): item
        for item in (ai_result.get("items") or [])
    }
    status = ai_result.get("status") or "no disponible"

    for row in rows:
        key = _check11_item_key(row)
        ai_item = lookup.get(key)
        enriched = dict(row)
        enriched["ESTAT_ANALISI_IA"] = status
        enriched["CLASSIFICACIO_IA"] = ai_item.get("classificacio_ia") if ai_item else None
        enriched["CONFIANCA_IA"] = ai_item.get("confianca_ia") if ai_item else None
        enriched["EXPLICACIO_IA"] = ai_item.get("explicacio_ia") if ai_item else None
        enriched["RECOMANACIO_IA"] = ai_item.get("recomanacio_ia") if ai_item else None
        merged_rows.append(enriched)

    return merged_rows
