"""Additive adapters between legacy Post-CRQ dictionaries and E13DB rule contracts."""
from __future__ import annotations

import time
from typing import Any, Dict

from src.api.check_engine import RuleDefinition, RuleResult, RuleStatus, redact_evidence


def definition_from_post_crq(check: Dict[str, Any], *, timeout: float | None = None) -> RuleDefinition:
    return RuleDefinition(
        rule_id=str(check["check_id"]), name=str(check.get("title") or check["check_id"]),
        description=str(check.get("description") or check.get("criteri") or ""), category="post_crq",
        default_severity=str(check.get("severitat") or "LOW"), supported_engine=("oracle",), timeout=timeout,
        tags=("post-crq",), evidence_sensitivity="internal",
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
    evidence = redact_evidence({"row_count": int(item.get("row_count") or 0), "columns": list(item.get("columns") or []), "rows": rows[:100]})
    return RuleResult(
        rule_id=definition.rule_id, database_id=database_id, status=status,
        severity=definition.default_severity, started_at=started, finished_at=finished,
        duration=duration_ms / 1000, summary=str(item.get("criteri") or item.get("title") or ""),
        metrics={"row_count": int(item.get("row_count") or 0), "duration_ms": duration_ms}, evidence=evidence,
        error=redact_evidence(item.get("error")) if status is RuleStatus.ERROR else None,
        recommendation=definition.recommendation,
    )
