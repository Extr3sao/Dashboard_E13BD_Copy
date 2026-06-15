import datetime as dt
import hashlib
from typing import Any, Dict, List, Optional

from src.core.automation_store import AutomationStore
from src.core.ownership_resolver import load_ownership_mapping
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now_iso


IGNORED_LOT_CODES = {"", "SENSE LOT", "SIN_MAPEO"}


def _normalize_lot(value: Any) -> str:
    return str(value or "").strip().upper()


def load_schema_lot_catalog(mapping_db_path: Optional[str] = None) -> Dict[str, List[str]]:
    db_path = mapping_db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    ownership_mapping = load_ownership_mapping(db_path)
    catalog: Dict[str, List[str]] = {}
    for schema_name, assignment in ownership_mapping.items():
        schema = str(schema_name or "").strip().upper()
        lot = _normalize_lot((assignment or {}).get("lot"))
        if not schema or lot in IGNORED_LOT_CODES:
            continue
        catalog.setdefault(lot, []).append(schema)
    return {
        lot: sorted({schema for schema in schemas if schema})
        for lot, schemas in sorted(catalog.items())
    }


def _catalog_hash(catalog: Dict[str, List[str]]) -> str:
    serialized = "|".join(
        f"{lot}:{','.join(sorted(schemas))}"
        for lot, schemas in sorted(catalog.items())
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_master_lot_backfill_preview(
    store: AutomationStore,
    *,
    mapping_db_path: Optional[str] = None,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    catalog = load_schema_lot_catalog(mapping_db_path)
    source_hash = _catalog_hash(catalog)
    master_lots = {str(item.get("code") or "").strip().upper(): item for item in store.list_master_lots()}
    lot_routes = {str(item.get("lot_code") or "").strip().upper(): item for item in store.list_lot_routes(audience="provider")}

    items: List[Dict[str, Any]] = []
    create_count = 0
    noop_count = 0
    conflict_count = 0

    for lot_code, schema_names in catalog.items():
        current = master_lots.get(lot_code)
        if not current:
            action = "create"
            conflict_code = None
            selected = True
            notes = "Lot absent al cataleg mestre i candidat a alta."
            create_count += 1
        elif not bool(current.get("enabled", True)):
            action = "conflict"
            conflict_code = "disabled_master_lot"
            selected = False
            notes = "El lot existeix al cataleg mestre pero esta deshabilitat."
            conflict_count += 1
        else:
            action = "noop"
            conflict_code = None
            selected = False
            notes = "El lot ja existeix al cataleg mestre."
            noop_count += 1
        items.append(
            {
                "lot_code": lot_code,
                "proposed_label": lot_code,
                "schema_names": schema_names,
                "action": action,
                "conflict_code": conflict_code,
                "selected": selected,
                "applied": False,
                "notes": notes,
            }
        )

    for lot_code, route in sorted(lot_routes.items()):
        if lot_code in master_lots or lot_code in catalog:
            continue
        items.append(
            {
                "lot_code": lot_code,
                "proposed_label": str(route.get("label") or lot_code).strip() or lot_code,
                "schema_names": [],
                "action": "conflict",
                "conflict_code": "route_without_master",
                "selected": False,
                "applied": False,
                "notes": "Existeix una ruta de destinataris sense lot al cataleg mestre ni a schema_lots.",
            }
        )
        conflict_count += 1

    summary = {
        "source_rows": sum(len(schemas) for schemas in catalog.values()),
        "distinct_lots": len(catalog),
        "to_create": create_count,
        "noop": noop_count,
        "conflicts": conflict_count,
    }
    existing_preview = next(
        (
            item
            for item in store.list_master_lot_backfill_runs(limit=20)
            if item.get("status") == "preview" and item.get("source_hash") == source_hash
        ),
        None,
    )
    if existing_preview:
        return existing_preview
    run = store.create_master_lot_backfill_run(
        source_hash=source_hash,
        summary=summary,
        actor=actor,
        reason=reason,
    )
    store.replace_master_lot_backfill_items(run["id"], items)
    store.record_change_event(
        entity_type="master_lot_backfill",
        entity_key=str(run["id"]),
        action="preview",
        actor=actor,
        reason=reason,
        before=None,
        after={"summary": summary},
        context={"source_hash": source_hash},
    )
    return store.get_master_lot_backfill_run(run["id"]) or run


def apply_master_lot_backfill(
    store: AutomationStore,
    *,
    run_id: int,
    selected_lot_codes: Optional[List[str]] = None,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    run = store.get_master_lot_backfill_run(run_id)
    if not run:
        raise ValueError("Execucio de backfill no trobada")

    selected = {
        _normalize_lot(item)
        for item in (selected_lot_codes or [])
        if _normalize_lot(item)
    }
    items = run.get("items") or []
    candidates = [
        item
        for item in items
        if item.get("action") == "create" and (not selected or _normalize_lot(item.get("lot_code")) in selected)
    ]
    payload = [
        {
            "code": _normalize_lot(item.get("lot_code")),
            "label": str(item.get("proposed_label") or item.get("lot_code") or "").strip() or _normalize_lot(item.get("lot_code")),
            "description": "",
            "enabled": True,
            "metadata": {
                "backfill_source": "schema_lots",
                "backfill_run_id": int(run_id),
                "schema_names": item.get("schema_names") or [],
            },
        }
        for item in candidates
    ]
    created_codes = [item["code"] for item in payload]
    if payload:
        store.upsert_master_lots(
            payload,
            actor=actor,
            reason=reason or "Backfill des de schema_lots",
            context={"source": "backfill", "backfill_run_id": int(run_id)},
        )
        store.mark_master_lot_backfill_items_applied(run_id, created_codes)
    applied_summary = {
        **(run.get("summary") or {}),
        "applied_count": len(created_codes),
        "selected_count": len(selected) if selected else len(candidates),
    }
    updated = store.update_master_lot_backfill_run(
        run_id,
        status="applied",
        summary=applied_summary,
        actor=actor,
        reason=reason,
        applied_at=run.get("applied_at") or utc_now_iso(),
    )
    store.record_change_event(
        entity_type="master_lot_backfill",
        entity_key=str(run_id),
        action="apply",
        actor=actor,
        reason=reason,
        before={"summary": run.get("summary") or {}},
        after={"summary": applied_summary, "created_codes": created_codes},
        context={"selected_lot_codes": sorted(selected) if selected else created_codes},
    )
    return updated or run
