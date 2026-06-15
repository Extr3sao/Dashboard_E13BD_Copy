from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.ownership_resolver import load_ownership_mapping
from src.core.sqlite_paths import resolve_sqlite_path


LOT_STATUS_WITH_FINDINGS = "CON_HALLAZGOS"
LOT_STATUS_WITHOUT_FINDINGS = "SIN_HALLAZGOS"
LOT_STATUS_NOT_APPLICABLE = "NO_APLICA"
LOT_STATUS_QUERY_ERROR = "ERROR_CONSULTA"
LOT_STATUS_UNMAPPED = "SIN_MAPEO"
UNMAPPED_LOT_CODE = LOT_STATUS_UNMAPPED
_UNMAPPED_MARKERS = {"", "SENSE LOT", UNMAPPED_LOT_CODE}


def default_distribution_job_config() -> Dict[str, Any]:
    return {
        "lot_scope": {
            "mode": "all",
            "selected_lots": [],
        },
        "send_policy": {
            "send_only_with_findings": True,
            "send_without_findings": False,
            "record_without_findings": True,
        },
        "email_template": {
            "subject": "[Oracle Audit] {job_name} - {lot}",
            "body": (
                "Bon dia,\n\n"
                "S'ha executat correctament l'auditoria automàtica del lot {lot}.\n\n"
                "Resum de l'execució\n"
                "- Perfil: {profile}\n"
                "- Lot: {lot}\n"
                "- Estat: {status}\n"
                "- Nombre de troballes: {findings}\n"
                "- Identificador d'execució: {execution_id}\n\n"
                "Observacions\n"
                "{observations}\n\n"
                "Llegenda tècnica\n"
                "{technical_legend}\n\n"
                "Trobaràs el detall complet a l'informe adjunt.\n\n"
                "Salutacions,\n"
                "Sistema d'auditoria BBDD"
            ),
        },
        "report_options": {
            "include_summary": True,
            "include_lot_reports": True,
        },
        "delivery": {
            "targets": ["lots", "tic"],
            "test_mode": False,
            "override_recipients": [],
        },
    }


def normalize_distribution_job_config(raw_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    defaults = default_distribution_job_config()
    source = raw_config or {}

    scope = source.get("lot_scope") or {}
    mode = str(scope.get("mode") or defaults["lot_scope"]["mode"]).strip().lower()
    if mode not in {"all", "selected"}:
        mode = "all"
    selected_lots: List[Dict[str, Any]] = []
    for value in scope.get("selected_lots") or []:
        if isinstance(value, dict):
            lot_code = str(value.get("code") or "").strip().upper()
            if not lot_code:
                continue
            
            emails: List[Dict[str, Any]] = []
            for e in (value.get("emails") or []):
                if isinstance(e, dict):
                    email_str = str(e.get("email") or "").strip()
                    if email_str:
                        emails.append({
                            "email": email_str,
                            "enabled": bool(e.get("enabled", True))
                        })
                else:
                    email_str = str(e or "").strip()
                    if email_str:
                        emails.append({"email": email_str, "enabled": True})
            
            selected_lots.append({
                "code": lot_code,
                "emails": emails
            })
        else:
            # Compatibilitat amb format antic (llista de strings)
            lot = str(value or "").strip().upper()
            if lot:
                selected_lots.append({
                    "code": lot,
                    "emails": []
                })

    send_policy = source.get("send_policy") or {}
    email_template = source.get("email_template") or {}
    report_options = source.get("report_options") or {}
    delivery = source.get("delivery") or {}

    raw_targets = delivery.get("targets")
    targets: List[str] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            normalized_target = str(item or "").strip().lower()
            if normalized_target in {"lots", "tic"} and normalized_target not in targets:
                targets.append(normalized_target)
    else:
        if source.get("send_to_lots", True) is not False:
            targets.append("lots")
        if source.get("send_to_tic", True) is not False:
            targets.append("tic")

    override_recipients: List[str] = []
    for item in delivery.get("override_recipients") or []:
        email = str(item or "").strip()
        if email and email not in override_recipients:
            override_recipients.append(email)
    test_mode = bool(delivery.get("test_mode", False))

    return {
        "lot_scope": {
            "mode": mode,
            "selected_lots": selected_lots,
        },
        "send_policy": {
            "send_only_with_findings": True if send_policy.get("send_only_with_findings", True) is not False else False,
            "send_without_findings": True if send_policy.get("send_without_findings", False) is True else False,
            "record_without_findings": True if send_policy.get("record_without_findings", True) is not False else False,
        },
        "email_template": {
            "subject": str(email_template.get("subject") or defaults["email_template"]["subject"]).strip() or defaults["email_template"]["subject"],
            "body": str(email_template.get("body") or defaults["email_template"]["body"]).strip() or defaults["email_template"]["body"],
        },
        "report_options": {
            "include_summary": bool(report_options.get("include_summary", True)),
            "include_lot_reports": bool(report_options.get("include_lot_reports", True)),
        },
        "delivery": {
            "targets": targets,
            "test_mode": test_mode,
            "override_recipients": override_recipients,
        },
    }


def _normalized_lot(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_unmapped_lot(value: Any) -> bool:
    return _normalized_lot(value) in _UNMAPPED_MARKERS


def _append_unique(values: List[str], candidate: Any) -> None:
    normalized = _normalized_lot(candidate)
    if normalized and normalized not in values:
        values.append(normalized)


def _collect_detected_lots(report_data: Dict[str, Any]) -> List[str]:
    detected: List[str] = []
    report_model = report_data.get("report_model") or {}
    for item in report_model.get("lot_summary") or []:
        lot = item.get("lot")
        if not _is_unmapped_lot(lot):
            _append_unique(detected, lot)
    for item in report_model.get("lot_incident_groups") or []:
        lot = item.get("lot")
        if not _is_unmapped_lot(lot):
            _append_unique(detected, lot)
    for finding in report_data.get("finding_envelopes") or []:
        lot_assignment = finding.get("lot_assignment") or {}
        lot = lot_assignment.get("lot")
        if not _is_unmapped_lot(lot):
            _append_unique(detected, lot)
    return detected


def _catalog_from_mapping(
    ownership_mapping: Dict[str, Dict[str, Any]],
    selected_schemas: List[str],
) -> Dict[str, List[str]]:
    catalog: Dict[str, List[str]] = {}
    for schema_name, assignment in ownership_mapping.items():
        schema = str(schema_name or "").strip().upper()
        lot = _normalized_lot((assignment or {}).get("lot"))
        if not schema or _is_unmapped_lot(lot):
            continue
        if selected_schemas and schema not in selected_schemas:
            continue
        catalog.setdefault(lot, []).append(schema)
    for lot, schemas in catalog.items():
        catalog[lot] = sorted({schema for schema in schemas if schema})
    return catalog


def build_post_crq_lot_execution_matrix(
    report_data: Dict[str, Any],
    *,
    job_config: Optional[Dict[str, Any]] = None,
    delivery_routes: Optional[Dict[str, Any]] = None,
    master_lots: Optional[List[Dict[str, Any]]] = None,
    mapping_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_job_config = normalize_distribution_job_config(job_config)
    scope = normalized_job_config["lot_scope"]
    selected_lots = list(scope.get("selected_lots") or [])
    selected_schemas = [
        str(schema or "").strip().upper()
        for schema in ((report_data.get("context") or {}).get("schemas") or [])
        if str(schema or "").strip()
    ]
    routes_lookup = {
        _normalized_lot(item.get("provider_code")): item
        for item in (delivery_routes or {}).get("providers") or []
        if _normalized_lot(item.get("provider_code"))
    }
    master_lot_lookup = {
        _normalized_lot(item.get("code")): item
        for item in (master_lots or [])
        if _normalized_lot(item.get("code")) and bool(item.get("enabled", True))
    }
    ownership_path = mapping_db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    ownership_mapping = load_ownership_mapping(ownership_path)
    mapping_catalog = _catalog_from_mapping(ownership_mapping, selected_schemas)
    detected_lots = _collect_detected_lots(report_data)

    target_lots: List[str] = []
    if scope.get("mode") == "selected":
        for item in selected_lots:
            _append_unique(target_lots, item.get("code"))
    else:
        for lot in master_lot_lookup.keys():
            _append_unique(target_lots, lot)
        for lot in mapping_catalog.keys():
            _append_unique(target_lots, lot)
        for lot in routes_lookup.keys():
            _append_unique(target_lots, lot)
        for lot in detected_lots:
            _append_unique(target_lots, lot)

    findings_by_lot: Dict[str, int] = {}
    unmapped_findings = 0
    findings_without_schema = 0
    finding_envelopes = report_data.get("finding_envelopes") or []
    for finding in finding_envelopes:
        if str(finding.get("runtime_status") or "").strip().lower() != "ok":
            continue
        schema = str(finding.get("schema") or "").strip().upper()
        lot = _normalized_lot(((finding.get("lot_assignment") or {}).get("lot")))
        if not schema:
            findings_without_schema += 1
        if _is_unmapped_lot(lot):
            unmapped_findings += 1
            continue
        findings_by_lot[lot] = findings_by_lot.get(lot, 0) + 1
        _append_unique(target_lots, lot)

    if not findings_by_lot and not finding_envelopes:
        for check_result in report_data.get("results_by_check") or []:
            if str(check_result.get("status") or "ok").strip().lower() != "ok":
                continue
            for row in check_result.get("rows") or []:
                lot = _normalized_lot(row.get("Lot") or row.get("LOT"))
                schema = str(row.get("ESQUEMA") or row.get("SCHEMA") or "").strip().upper()
                if not schema:
                    findings_without_schema += 1
                if _is_unmapped_lot(lot):
                    unmapped_findings += 1
                    continue
                findings_by_lot[lot] = findings_by_lot.get(lot, 0) + 1
                _append_unique(target_lots, lot)

    failed_checks = [
        {
            "check_id": item.get("check_id"),
            "title": item.get("title"),
            "error": item.get("error") or "query_execution_failed",
        }
        for item in (report_data.get("results_by_check") or [])
        if str(item.get("status") or "").strip().lower() != "ok"
    ]

    rows: List[Dict[str, Any]] = []
    for lot in target_lots:
        mapped_schemas = sorted(mapping_catalog.get(lot) or [])
        route = routes_lookup.get(lot) or {}
        master_lot = master_lot_lookup.get(lot) or {}
        findings = int(findings_by_lot.get(lot) or 0)
        
        job_lot_config = next((item for item in selected_lots if item.get("code") == lot), None)
        explicitly_selected = job_lot_config is not None
        covered_by_mapping = bool(mapped_schemas)
        has_detected_data = findings > 0 or lot in detected_lots

        if findings > 0:
            detection_status = LOT_STATUS_WITH_FINDINGS
            num_findings: Optional[int] = findings
            skip_reason = None
            observations = f"S'han detectat {findings} troballes per al lot {lot}."
        elif failed_checks and (covered_by_mapping or explicitly_selected):
            detection_status = LOT_STATUS_QUERY_ERROR
            num_findings = None
            skip_reason = "Revisio manual requerida per errors de consulta."
            observations = f"Hi ha {len(failed_checks)} checks amb error i no es pot assegurar l'absencia de troballes."
        elif covered_by_mapping or has_detected_data:
            detection_status = LOT_STATUS_WITHOUT_FINDINGS
            num_findings = 0
            skip_reason = "Sense troballes."
            observations = "Lot avaluat correctament i sense troballes."
        else:
            detection_status = LOT_STATUS_NOT_APPLICABLE
            num_findings = None
            skip_reason = "Lot fora d'abast o sense mapping amb els esquemes auditats."
            observations = "El lot no aplica a l'execucio actual o no te cobertura de mapping."

        # Resolució de correus: prioritzem els del job si mode es 'selected' i el lot hi és
        final_emails = []
        if explicitly_selected and job_lot_config and job_lot_config.get("emails"):
            final_emails = [e["email"] for e in job_lot_config["emails"] if e.get("enabled", True)]
            is_route_enabled = len(final_emails) > 0
        else:
            final_emails = list(route.get("emails") or [])
            is_route_enabled = bool(route.get("enabled", True)) if route else False

        rows.append(
            {
                "lot": lot,
                "detection_status": detection_status,
                "num_findings": num_findings,
                "report_generated": False,
                "email_sent": False,
                "motivo_sin_envio": None if detection_status == LOT_STATUS_WITH_FINDINGS else skip_reason,
                "observaciones": observations,
                "mapped_schemas": mapped_schemas,
                "route_label": str(route.get("label") or master_lot.get("label") or lot).strip() or lot,
                "route_emails": final_emails,
                "route_enabled": is_route_enabled,
                "master_lot_label": str(master_lot.get("label") or lot).strip() or lot,
                "needs_manual_review": detection_status in {LOT_STATUS_QUERY_ERROR, LOT_STATUS_UNMAPPED},
                "delivery_candidate": detection_status == LOT_STATUS_WITH_FINDINGS,
                "is_from_job_config": explicitly_selected and bool(job_lot_config and job_lot_config.get("emails")),
            }
        )

    if unmapped_findings or findings_without_schema:
        observations = f"Hi ha {unmapped_findings} troballes sense lot fiable i {findings_without_schema} sense esquema identificable."
        rows.append(
            {
                "lot": UNMAPPED_LOT_CODE,
                "detection_status": LOT_STATUS_UNMAPPED,
                "num_findings": unmapped_findings or findings_without_schema or None,
                "report_generated": False,
                "email_sent": False,
                "motivo_sin_envio": "Revisio manual requerida per troballes sense lot fiable.",
                "observaciones": observations,
                "mapped_schemas": [],
                "route_label": UNMAPPED_LOT_CODE,
                "route_emails": [],
                "route_enabled": False,
                "needs_manual_review": True,
                "delivery_candidate": False,
            }
        )

    status_counts: Dict[str, int] = {}
    for row in rows:
        key = row["detection_status"]
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "job_config": normalized_job_config,
        "items": rows,
        "failed_checks": failed_checks,
        "target_lots": target_lots,
        "summary": {
            "total_lots": len(rows),
            "with_findings": status_counts.get(LOT_STATUS_WITH_FINDINGS, 0),
            "without_findings": status_counts.get(LOT_STATUS_WITHOUT_FINDINGS, 0),
            "not_applicable": status_counts.get(LOT_STATUS_NOT_APPLICABLE, 0),
            "query_errors": status_counts.get(LOT_STATUS_QUERY_ERROR, 0),
            "unmapped": status_counts.get(LOT_STATUS_UNMAPPED, 0),
            "failed_checks": len(failed_checks),
        },
    }
