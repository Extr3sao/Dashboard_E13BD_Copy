# Verification evidence

| Requirement | Evidence |
|---|---|
| AR-1 | `tests/test_alerting_engine.py` simulates 20 repeated evaluations and verifies one event. |
| AR-2 | Focused tests cover P2/P1 policy transition, maintenance suppression and linked recovery. |
| AR-3 | `tests/test_alerting_router.py` verifies anonymous rejection and CSRF enforcement. |
| AR-4 | Focused tests persist daily/weekly reports with aging data; scheduler-due test proves reuse of existing automation tick. |
| AR-5 | Alert summary and delivery error paths use `redact_secrets`; SMTP channel reads runtime-only config. |
| AR-6 | `npm run lint`, `npm test`, and `npm run build` pass with the lazy AlertingReports view. |

Commands executed: `python -m pytest -q` (288 passed, 2 warnings, 6 subtests), `npm run lint`, `npm test` (27 files, 80 tests), `npm run build`, `git diff --check`.

Residual risk: actual SMTP delivery is intentionally not exercised against a live mail server; it is configuration-dependent and delivery failures are persisted safely.
