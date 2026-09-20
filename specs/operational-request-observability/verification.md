# Verification

## Environment

Windows; Python 3.14. The repository did not contain a virtual environment or frontend `node_modules` at baseline.

## Commands and results

| Command | Result |
|---|---|
| `python -m pytest tests/test_main_runtime.py -q` | PASS — 43 passed in 12.92s (two third-party TestClient deprecation warnings). |
| `.venv-repro\\Scripts\\python.exe -m pytest -q --durations=10` | PASS — 255 passed in 173.80s; exit code 0. One third-party Starlette deprecation warning. |
| `npm run lint` | BLOCKED — `node_modules` absent; `eslint` unavailable. |
| `npm test -- --runInBand` | BLOCKED — `node_modules` absent; `vitest` unavailable. |
| `npm run build` | BLOCKED — `node_modules` absent; `vite` unavailable. |

The first focused pytest attempt was blocked because the unpinned Python manifest had not installed dependencies. The resolver backtracked over the Google dependency graph and left a partial environment; the focused test was rerun successfully after the necessary packages became available. This is evidence for IMP-001, not a product regression.

## Acceptance evidence

| Acceptance criterion | Evidence |
|---|---|
| AC-001 | `test_operational_endpoints_and_request_observability_contract` asserts `GET /healthz` is 200 with the exact liveness payload. |
| AC-002 | The same test asserts `GET /readyz` is 200 with the exact local readiness payload. |
| AC-003 | The same test verifies a valid ID is preserved and an invalid one becomes a UUID. |
| AC-004 | `test_request_completion_log_is_redacted_and_correlated` checks the structured log `extra` fields use the request ID and path only, not the query string. |
| AC-005 | `test_operational_endpoints_and_request_observability_contract` rejects an invalid ID and confirms a generated UUID; the unit-level runtime suite also covers the bounded-ID validation path. |
| AC-006 | `test_request_observability_covers_4xx_and_unhandled_5xx_without_leaking_secrets` checks 405 and 500 responses, correlation headers, exactly one completion event per response, and non-negative durations. |
| AC-007 | The redaction and 4xx/5xx tests assert request metadata excludes query secrets; `test_request_observability_wraps_unhandled_5xx_with_correlation` asserts exception text is not logged. |

## Residual risks

The backend full-regression gate is now PASS for the frozen Python environment. Frontend lint/tests/build/mock E2E still require a clean dependency install and have not been used to certify this backend-only slice. Readiness deliberately does not probe Oracle or SMTP because those integrations are optional and credential-gated.
