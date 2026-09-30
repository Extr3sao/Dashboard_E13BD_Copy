# Design

`FindingStore` is an additive SQLite façade in `src/api/finding_engine.py`; it owns schema setup, reconciliation, lifecycle actions and Red Flag calculations. A finding is identified only by a deterministic fingerprint. One `finding_occurrences` record is written per evaluated candidate; `findings` is its current projection.

Only `PASS`, `WARN` and `FAIL` are coverage-valid. A matching candidate keeps/updates an open finding. A valid successful scope resolves open findings for the same database/rule only when it produced no candidate. `ERROR`, `SKIPPED`, failed/interrupted runs and omitted scope do not resolve anything.

Numeric evolution is explicit metadata: candidate `comparison_direction` is `higher_is_worse` or `lower_is_worse`; otherwise persistent is used. Existing Post-CRQ results yield candidates for `FAIL` and `WARN`, with row count as a comparable higher-is-worse metric.

The API router is under `/api/findings`; existing API security middleware requires USER and CSRF for mutations. The React view is a new top-level operational tab, consuming only cookie-authenticated axios calls.

Priority is deterministic: critical production new/worsening/reopened findings are P1; critical/high or persistent critical are P2; medium/new or unhealthy coverage is P3; otherwise P4. Every flag stores a redacted explanation and deduplication key.
