# Design

`src/api/execution_reliability.py` provides an in-memory, lease-aware coordinator deliberately separated from the existing automation store, avoiding migration of unrelated automation tables. It owns state transitions, target isolation, deadline enforcement, retry classification/backoff, cancellation, and stale-lease recovery. Its lease protocol is duck-typed (`acquire`, `release`, `recover_stale`) so a persistent certified lease provider can be supplied.

`src/api/check_engine.py` provides immutable-ish dataclass contracts and a sequential isolated executor. Rules are evaluated against a target capability set before execution. The executor is run in a bounded worker; its timeout/error becomes a normalized `ERROR`. Redaction recursively removes credential-shaped keys and secrets in strings.

Post-CRQ receives adapters: parsed checks become Oracle `RuleDefinition`s and legacy check dictionaries become `RuleResult`s. The old fields remain unchanged, with `rule_results` added as a stable extension.

Security: raw SQL and credentials are not copied into normalized evidence. Evidence is bounded to row count, columns and sanitized rows supplied by the legacy output.

Validation: focused unit tests cover AC-001 through AC-007; existing Post-CRQ tests are regression evidence.
