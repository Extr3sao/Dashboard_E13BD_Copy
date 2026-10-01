# Design

`FindingStore` gains an additive `audit_runs` ledger. Reconciliation records the summarized outcome after each run while findings retain their existing object-level occurrence history. Fleet health is derived server-side from the latest audit, coverage, red flags, active findings and target context; it is not a persisted competing truth.

The dashboard API is a small router mounted under `/api/operations`. It returns pre-aggregated fleet and target payloads to prevent client-side N+1 requests. `FleetDashboardView` makes a single fleet request, then requests a target detail only when selected.

Health order: execution failure/unreachable, stale or no successful audit, inadequate coverage, P1/P2/critical finding, attention-level findings/flags, then healthy. A target can only be healthy when its latest successful audit has full coverage and no active warning signals.

Trend buckets are calculated from `audit_runs` and existing occurrences over a requested time window. Errors use the existing redaction helper before persistence.
