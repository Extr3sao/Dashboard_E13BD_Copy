from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from src.api.post_crq_lot_status import build_post_crq_lot_execution_matrix
from src.core.ownership_resolver import load_ownership_mapping
from src.core.sqlite_paths import resolve_sqlite_path


def _normalized(value: Any) -> str:
    return str(value or "").strip().upper()


def _schema_from_row(row: Dict[str, Any]) -> str:
    for key in ("ESQUEMA", "SCHEMA", "SCHEMA_NAME", "OWNER", "USERNAME"):
        if row.get(key):
            return _normalized(row.get(key))
    return ""


def _lot_from_row(row: Dict[str, Any]) -> str:
    for key in ("Lot", "LOT", "lot", "LOT_NAME"):
        if row.get(key):
            return _normalized(row.get(key))
    return ""


def _check_id_from_finding(finding: Dict[str, Any]) -> str:
    return _normalized(finding.get("source_check") or finding.get("check_id"))


def build_post_crq_analytics_payload(
    report_data: Dict[str, Any],
    *,
    run_id: int,
    job_id: int,
    execution_id: str,
    executed_at: str,
    audit_type: str,
    profile: str,
    lot_execution: Optional[Dict[str, Any]] = None,
    mapping_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    context = report_data.get("context") or {}
    summary = report_data.get("summary") or {}
    mapping_path = mapping_db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    ownership_mapping = load_ownership_mapping(mapping_path)
    current_lot_execution = lot_execution or build_post_crq_lot_execution_matrix(
        report_data,
        job_config={},
        delivery_routes={},
        master_lots=[],
        mapping_db_path=mapping_path,
    )

    report_model = report_data.get("report_model") or {}
    lot_checks: Dict[str, Set[str]] = defaultdict(set)
    report_model_schema_lots: Dict[str, str] = {}
    for item in report_model.get("lot_summary") or []:
        lot = _normalized(item.get("lot"))
        if not lot:
            continue
        for schema_name in item.get("schemas") or []:
            schema = _normalized(schema_name)
            if schema:
                report_model_schema_lots[schema] = lot
        for check_id in item.get("checks") or []:
            if _normalized(check_id):
                lot_checks[lot].add(_normalized(check_id))
    for item in report_model.get("lot_incident_groups") or []:
        lot = _normalized(item.get("lot"))
        check_id = _normalized(item.get("check") or item.get("check_id"))
        if lot and check_id:
            lot_checks[lot].add(check_id)
        for schema_group in item.get("schemas") or []:
            schema = _normalized(schema_group.get("nom") or schema_group.get("schema") or schema_group.get("schema_name"))
            if schema and lot:
                report_model_schema_lots[schema] = lot

    schema_counts: Dict[str, int] = defaultdict(int)
    schema_checks: Dict[str, Set[str]] = defaultdict(set)
    schema_lots: Dict[str, str] = {}
    check_counts: Dict[str, int] = defaultdict(int)
    check_lots: Dict[str, Set[str]] = defaultdict(set)
    check_schemas: Dict[str, Set[str]] = defaultdict(set)
    check_meta: Dict[str, Dict[str, Any]] = {}

    finding_envelopes = report_data.get("finding_envelopes") or []
    if finding_envelopes:
        for finding in finding_envelopes:
            if str(finding.get("runtime_status") or "").strip().lower() != "ok":
                continue
            schema = _normalized(finding.get("schema"))
            lot = _normalized(((finding.get("lot_assignment") or {}).get("lot")))
            check_id = _check_id_from_finding(finding)
            if schema:
                schema_counts[schema] += 1
                if check_id:
                    schema_checks[schema].add(check_id)
                if lot:
                    schema_lots[schema] = lot
            if check_id:
                check_counts[check_id] += 1
                if lot:
                    check_lots[check_id].add(lot)
                if schema:
                    check_schemas[check_id].add(schema)
    else:
        for result in report_data.get("results_by_check") or []:
            check_id = _normalized(result.get("check_id"))
            rows = result.get("rows") or []
            for row in rows:
                schema = _schema_from_row(row)
                lot = _lot_from_row(row) or report_model_schema_lots.get(schema) or _normalized((ownership_mapping.get(schema) or {}).get("lot"))
                if schema:
                    schema_counts[schema] += 1
                    if check_id:
                        schema_checks[schema].add(check_id)
                    if lot:
                        schema_lots[schema] = lot
                if check_id:
                    check_counts[check_id] += 1
                    if lot:
                        check_lots[check_id].add(lot)
                    if schema:
                        check_schemas[check_id].add(schema)

    selected_schemas = [_normalized(item) for item in (context.get("schemas") or []) if _normalized(item)]
    for schema in selected_schemas:
        schema_lots.setdefault(schema, report_model_schema_lots.get(schema) or _normalized((ownership_mapping.get(schema) or {}).get("lot")))

    check_rows: List[Dict[str, Any]] = []
    for result in report_data.get("results_by_check") or []:
        check_id = _normalized(result.get("check_id"))
        if not check_id:
            continue
        rows = result.get("rows") or []
        row_count = int(result.get("row_count") or len(rows))
        check_meta[check_id] = {
            "title": result.get("title") or check_id,
            "severity": result.get("severitat") or result.get("criticality") or "-",
            "status": str(result.get("status") or "ok").strip().lower() or "ok",
        }
        check_rows.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "execution_id": execution_id,
                "executed_at": executed_at,
                "check_id": check_id,
                "title": check_meta[check_id]["title"],
                "severity": check_meta[check_id]["severity"],
                "status": check_meta[check_id]["status"],
                "row_count": row_count,
                "finding_count": int(check_counts.get(check_id, row_count if row_count > 0 else 0)),
                "affected_lots": len(check_lots.get(check_id, set())),
                "affected_schemas": len(check_schemas.get(check_id, set())),
                "payload": {
                    "title": check_meta[check_id]["title"],
                    "status": check_meta[check_id]["status"],
                    "row_count": row_count,
                },
            }
        )

    lot_rows: List[Dict[str, Any]] = []
    for item in current_lot_execution.get("items") or []:
        lot = _normalized(item.get("lot"))
        if not lot:
            continue
        lot_rows.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "execution_id": execution_id,
                "executed_at": executed_at,
                "lot": lot,
                "detection_status": item.get("detection_status"),
                "finding_count": int(item.get("num_findings") or 0),
                "schema_count": len(item.get("mapped_schemas") or []),
                "check_count": len(lot_checks.get(lot, set())),
                "payload": item,
            }
        )

    schema_rows: List[Dict[str, Any]] = []
    schema_source = sorted(set(selected_schemas) | set(schema_counts.keys()))
    for schema in schema_source:
        lot = schema_lots.get(schema) or report_model_schema_lots.get(schema) or _normalized((ownership_mapping.get(schema) or {}).get("lot"))
        schema_rows.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "execution_id": execution_id,
                "executed_at": executed_at,
                "schema_name": schema,
                "lot": lot or "SENSE LOT",
                "finding_count": int(schema_counts.get(schema, 0)),
                "check_count": len(schema_checks.get(schema, set())),
                "payload": {
                    "schema": schema,
                    "lot": lot or "SENSE LOT",
                },
            }
        )

    lots_with_findings = sum(1 for item in lot_rows if int(item.get("finding_count") or 0) > 0)
    execution_row = {
        "run_id": run_id,
        "job_id": job_id,
        "execution_id": execution_id,
        "executed_at": executed_at,
        "audit_type": audit_type,
        "profile": profile,
        "total_findings": int(summary.get("total_findings") or sum(item["finding_count"] for item in lot_rows if item.get("lot") != "SIN_MAPEO")),
        "checks_with_findings": int(summary.get("checks_with_findings") or sum(1 for item in check_rows if int(item.get("finding_count") or 0) > 0)),
        "checks_with_errors": int(summary.get("checks_with_errors") or sum(1 for item in check_rows if item.get("status") != "ok")),
        "lots_with_findings": lots_with_findings,
        "schemas_in_scope": len(selected_schemas),
        "payload": {
            "context": context,
            "summary": summary,
        },
    }

    return {
        "execution": execution_row,
        "lots": lot_rows,
        "schemas": schema_rows,
        "checks": check_rows,
    }
