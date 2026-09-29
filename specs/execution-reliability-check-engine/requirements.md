# E13DB-002/003 requirements

## Context

Post-CRQ checks currently return legacy `ok`/`error` dictionaries. The next finding milestone needs a stable, safe rule-result contract and reliable execution primitives.

## Goals

- FR-001: Runs MUST use explicit `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, or `INTERRUPTED` states and reject invalid transitions.
- FR-002: A run MUST isolate target failures, record each target outcome, honour configurable connection/check/run timeouts, retry only classified transient errors with bounded backoff, and recover abandoned running leases as `INTERRUPTED`.
- FR-003: A `RuleDefinition` MUST expose the requested metadata with safe defaults.
- FR-004: A `RuleResult` MUST normalize `PASS`, `WARN`, `FAIL`, `ERROR`, and `SKIPPED`, retain stable finding fields, and redact secrets from errors/evidence.
- FR-005: The engine MUST skip incompatible engine/version/capability/license rules and isolate executor exceptions/timeouts.
- FR-006: Post-CRQ MUST expose normalized `rule_results` while retaining legacy report fields.

## Non-goals

Finding lifecycle/fingerprints, Red Flag Engine, notification work, and new database adapters are excluded.

## Constraints and assumptions

- CON-001: Preserve existing Post-CRQ payload compatibility.
- CON-002: Existing uncommitted automation changes are out of scope.
- ASS-001: The supplied certified SHA is unavailable in this clone; HEAD is used as the integration base without asserting baseline certification.
- ASS-002: The repository-required `plan-writing` skill is missing; these SDD artifacts provide the equivalent evidence.

## Acceptance criteria

| ID | Observable result |
| --- | --- |
| AC-001 | Invalid run transitions fail; terminal runs cannot become successful. |
| AC-002 | Target failure/timeout/interruption is explicit and does not block other targets. |
| AC-003 | Leases prevent duplicate execution and stale leases recover as interrupted. |
| AC-004 | Transient failures retry only to configured exhaustion with recorded attempts. |
| AC-005 | Rule contracts represent all five statuses and redact secret values. |
| AC-006 | Engine compatibility/license gates return `SKIPPED`; an executor exception/timeout returns `ERROR` without stopping peers. |
| AC-007 | Existing Post-CRQ audit tests retain legacy output and normalized results are included. |
