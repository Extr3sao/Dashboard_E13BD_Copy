# E13DB-006/007 requirements

## Goal

Give operators a truthful fleet view: what needs action, whether each target has sufficient recent evidence, and how the position changed over time.

## Requirements

- FR-001: Persist an immutable audit execution summary after each finding reconciliation, including result counts, coverage, timing and safe execution outcome.
- FR-002: Derive deterministic target health (`HEALTHY`, `ATTENTION`, `CRITICAL`, `DEGRADED`, `UNREACHABLE`, `UNKNOWN`, `NOT_AUDITED`) with an explanation; zero findings alone MUST never mean healthy.
- FR-003: Expose authenticated APIs for fleet summary, target health/detail, attention queue, trends, audit history/detail and coverage.
- FR-004: Reuse finding occurrences and red flags for changes and trends; support 24h, 7d and 30d windows.
- FR-005: Provide an operational dashboard with fleet health, attention-first ordering, target detail, coverage and useful empty states.
- FR-006: Respect existing USER/CSRF policy and redact persisted execution errors/evidence.

## Constraints

- CON-001: Use additive/idempotent SQLite schema changes and preserve E13DB-004/005 contracts.
- CON-002: Target context defaults conservatively; no target without successful coverage is rendered healthy.
- CON-003: No ML/LLM, no Prometheus dependency, no service credentials in the browser.

## Acceptance criteria

- AC-001: Multi-target test derives healthy, critical, unreachable and degraded targets, and orders attention deterministically.
- AC-002: Trend and audit-history tests cover 24h/7d/30d, coverage regression and target detail.
- AC-003: API security tests prove USER protection/CSRF is maintained and data is redacted.
- AC-004: Dashboard UI visibly presents fleet status, attention, target detail and trends without raw JSON.
