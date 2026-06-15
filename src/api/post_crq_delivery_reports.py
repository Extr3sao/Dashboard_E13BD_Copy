import io
import json
import re
import zipfile
from typing import Any, Dict, List, Optional

from src.api.post_crq_audit import build_post_crq_pdf_report
from src.api.post_crq_experimental_pdf import filter_post_crq_report_for_lot


def _safe_provider_code(value: Optional[str]) -> str:
    raw = str(value or "SENSE_LOT").strip() or "SENSE_LOT"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)


def list_post_crq_provider_codes(report_data: Dict[str, Any]) -> List[str]:
    report_model = report_data.get("report_model") or {}
    seen = set()
    ordered: List[str] = []

    for item in report_model.get("lot_summary") or []:
        code = str(item.get("lot") or "").strip()
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)

    for item in report_model.get("lot_incident_groups") or []:
        code = str(item.get("lot") or "").strip()
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)

    for check_result in report_data.get("results_by_check") or []:
        for row in check_result.get("rows") or []:
            code = str(row.get("Lot") or row.get("LOT") or "").strip()
            if code and code not in seen:
                seen.add(code)
                ordered.append(code)

    return ordered


def build_post_crq_general_artifact(profile: str, report_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "audience": "tic",
        "provider_code": None,
        "filename": "general.pdf",
        "content": build_post_crq_pdf_report(profile, report_data),
    }


def build_post_crq_provider_artifact(profile: str, report_data: Dict[str, Any], provider_code: str) -> Dict[str, Any]:
    filtered_report = filter_post_crq_report_for_lot(report_data, provider_code)
    safe_code = _safe_provider_code(provider_code)
    return {
        "audience": "provider",
        "provider_code": provider_code,
        "filename": f"provider_{safe_code}.pdf",
        "content": build_post_crq_pdf_report(profile, filtered_report),
    }


def build_post_crq_all_artifacts(profile: str, report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts = [build_post_crq_general_artifact(profile, report_data)]
    for provider_code in list_post_crq_provider_codes(report_data):
        artifacts.append(build_post_crq_provider_artifact(profile, report_data, provider_code))
    return artifacts


def build_post_crq_zip_bundle(
    profile: str,
    report_data: Dict[str, Any],
    *,
    manifest: Optional[Dict[str, Any]] = None,
) -> bytes:
    artifacts = build_post_crq_all_artifacts(profile, report_data)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for artifact in artifacts:
            zf.writestr(artifact["filename"], artifact["content"])
        if manifest is not None:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    buffer.seek(0)
    return buffer.getvalue()
