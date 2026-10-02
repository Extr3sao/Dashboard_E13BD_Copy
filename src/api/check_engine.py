"""Normalized rule contracts and isolated execution engine (E13DB-003)."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional, Sequence


class RuleStatus(str, Enum):
    PASS = "PASS"; WARN = "WARN"; FAIL = "FAIL"; ERROR = "ERROR"; SKIPPED = "SKIPPED"


@dataclass
class RuleDefinition:
    rule_id: str
    name: str
    description: str = ""
    category: str = "general"
    default_severity: str = "LOW"
    supported_engine: Sequence[str] = field(default_factory=tuple)
    supported_versions: Sequence[str] = field(default_factory=tuple)
    required_privileges: Sequence[str] = field(default_factory=tuple)
    license_requirements: Sequence[str] = field(default_factory=tuple)
    required_capabilities: Sequence[str] = field(default_factory=tuple)
    timeout: Optional[float] = None
    tags: Sequence[str] = field(default_factory=tuple)
    evidence_sensitivity: str = "internal"
    recommendation: str = ""
    # Stable identity metadata. Version is declarative when available; the
    # definition hash is derived from executable rule content by adapters.
    version: str = "UNKNOWN"
    definition_hash: str = ""


@dataclass
class RuleResult:
    rule_id: str
    database_id: str
    status: RuleStatus
    severity: str
    started_at: float
    finished_at: float
    duration: float
    summary: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    evidence: Any = field(default_factory=dict)
    error: Optional[str] = None
    object_type: Optional[str] = None
    owner: Optional[str] = None
    object_name: Optional[str] = None
    recommendation: str = ""
    rule_version: str = "UNKNOWN"
    definition_hash: str = ""
    coverage_meaning: str = "evaluated"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self); payload["status"] = self.status.value
        return payload


_SECRET_KEY = re.compile(r"(password|passwd|secret|token|credential|authorization|api[_-]?key|webhook)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(password|passwd|token|secret|credential|authorization|api[_-]?key|webhook)\s*[:=]\s*[^\s,;]+")

def redact_evidence(value: Any) -> Any:
    if isinstance(value, dict): return {str(k): ("[REDACTED]" if _SECRET_KEY.search(str(k)) else redact_evidence(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [redact_evidence(item) for item in value]
    if isinstance(value, str): return _SECRET_VALUE.sub(r"\1=[REDACTED]", value)
    return value


class RuleEngine:
    def __init__(self, enabled_licenses: Iterable[str] = (), capabilities: Optional[Dict[str, Any]] = None):
        self.enabled_licenses = set(enabled_licenses); self.capabilities = capabilities or {}

    def execute(self, rules: Iterable[RuleDefinition], database_id: str, executor: Callable[[RuleDefinition], Any], *, engine: str, version: str, privileges: Iterable[str] = ()) -> list[RuleResult]:
        granted = set(privileges); results = []
        for rule in rules:
            started = time.time(); reason = self._skip_reason(rule, engine, version, granted)
            if reason:
                results.append(self._result(rule, database_id, RuleStatus.SKIPPED, started, summary=reason)); continue
            try:
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(executor, rule)
                try:
                    outcome = future.result(timeout=rule.timeout)
                finally:
                    # Never wait for an uncooperative timed-out rule: its result is
                    # isolated and subsequent rules must continue.
                    pool.shutdown(wait=False, cancel_futures=True)
                results.append(self._coerce(rule, database_id, started, outcome))
            except TimeoutError:
                results.append(self._result(rule, database_id, RuleStatus.ERROR, started, error="rule_timeout"))
            except BaseException as exc:
                results.append(self._result(rule, database_id, RuleStatus.ERROR, started, error=str(exc)))
        return results

    def _skip_reason(self, rule: RuleDefinition, engine: str, version: str, privileges: set[str]) -> Optional[str]:
        if rule.supported_engine and engine not in rule.supported_engine: return "incompatible_engine"
        if rule.supported_versions and version not in rule.supported_versions: return "incompatible_version"
        if set(rule.required_privileges) - privileges: return "missing_privilege"
        if set(rule.license_requirements) - self.enabled_licenses: return "license_not_enabled"
        if set(rule.required_capabilities) - set(self.capabilities.get("enabled", ())): return "missing_capability"
        return None

    def _coerce(self, rule: RuleDefinition, database_id: str, started: float, outcome: Any) -> RuleResult:
        if isinstance(outcome, RuleResult):
            outcome.evidence = redact_evidence(outcome.evidence); outcome.error = redact_evidence(outcome.error)
            outcome.rule_version = outcome.rule_version if outcome.rule_version != "UNKNOWN" else rule.version
            outcome.definition_hash = outcome.definition_hash or rule.definition_hash
            if outcome.status is RuleStatus.SKIPPED and outcome.coverage_meaning == "evaluated": outcome.coverage_meaning = "not_evaluated"
            elif outcome.status is RuleStatus.ERROR and outcome.coverage_meaning == "evaluated": outcome.coverage_meaning = "evaluation_error"
            elif not outcome.coverage_meaning: outcome.coverage_meaning = "evaluated"
            return outcome
        data = dict(outcome or {}); raw = str(data.pop("status", "PASS")).upper()
        status = RuleStatus(raw if raw in RuleStatus.__members__ else "ERROR")
        return self._result(rule, database_id, status, started, summary=str(data.pop("summary", "")), metrics=data.pop("metrics", {}), evidence=data.pop("evidence", data), error=data.pop("error", None))

    def _result(self, rule: RuleDefinition, database_id: str, status: RuleStatus, started: float, **values: Any) -> RuleResult:
        ended = time.time()
        return RuleResult(rule.rule_id, database_id, status, rule.default_severity, started, ended, ended - started, recommendation=rule.recommendation, evidence=redact_evidence(values.pop("evidence", {})), error=redact_evidence(values.pop("error", None)), rule_version=rule.version, definition_hash=rule.definition_hash, coverage_meaning="not_evaluated" if status is RuleStatus.SKIPPED else ("evaluation_error" if status is RuleStatus.ERROR else "evaluated"), **values)
