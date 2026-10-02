"""Additive adapters between legacy Post-CRQ dictionaries and E13DB rule contracts."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict

from src.api.check_engine import RuleDefinition, RuleResult, RuleStatus, redact_evidence


def definition_from_post_crq(check: Dict[str, Any], *, timeout: float | None = None) -> RuleDefinition:
    sql = str(check.get("sql") or "").strip()
    definition_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest() if sql else hashlib.sha256(str(check.get("check_id") or "").encode()).hexdigest()
    return RuleDefinition(
        rule_id=str(check["check_id"]), name=str(check.get("title") or check["check_id"]),
        description=str(check.get("description") or check.get("criteri") or ""), category="post_crq",
        default_severity=str(check.get("severitat") or "LOW"), supported_engine=("oracle",), timeout=timeout,
        tags=("post-crq",), evidence_sensitivity="internal",
        version=str(check.get("version") or check.get("versio") or f"sha256:{definition_hash[:16]}"),
        definition_hash=definition_hash,
        required_capabilities=tuple(str(value) for value in (check.get("required_capabilities") or ())),
        required_privileges=tuple(str(value) for value in (check.get("required_privileges") or ())),
        license_requirements=tuple(str(value) for value in (check.get("license_requirements") or ())),
    )


def result_from_post_crq(item: Dict[str, Any], database_id: str, definition: RuleDefinition) -> RuleResult:
    duration_ms = max(0, int(item.get("duration_ms") or 0)); finished = time.time(); started = finished - duration_ms / 1000
    legacy_status = str(item.get("status") or "error").lower()
    if legacy_status == "skipped": status = RuleStatus.SKIPPED
    elif legacy_status != "ok": status = RuleStatus.ERROR
    elif int(item.get("row_count") or 0): status = RuleStatus.FAIL
    else: status = RuleStatus.PASS
    rows = item.get("rows") or []
    # Do not copy SQL, bind values or raw configuration into the normalized contract.
    # Durable normalized evidence must not copy query rows/bind values (which
    # can include production or personal data). Object-level Findings are
    # persisted separately as allow-listed finding envelopes.
    evidence = redact_evidence({"row_count": int(item.get("row_count") or 0), "columns": list(item.get("columns") or [])[:100]})
    return RuleResult(
        rule_id=definition.rule_id, database_id=database_id, status=status,
        severity=definition.default_severity, started_at=started, finished_at=finished,
        duration=duration_ms / 1000, summary=str(item.get("criteri") or item.get("title") or ""),
        metrics={"row_count": int(item.get("row_count") or 0), "duration_ms": duration_ms}, evidence=evidence,
        error=redact_evidence(item.get("error")) if status is RuleStatus.ERROR else None,
        recommendation=definition.recommendation,
        rule_version=definition.version, definition_hash=definition.definition_hash,
        coverage_meaning="not_evaluated" if status is RuleStatus.SKIPPED else ("evaluation_error" if status is RuleStatus.ERROR else "evaluated"),
    )
