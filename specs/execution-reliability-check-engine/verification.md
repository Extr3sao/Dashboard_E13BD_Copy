# Verification

## Environment

Python test runner in the repository virtual environment; frontend dependencies are absent in this checkout.

## Executed checks

- `python -m pytest tests/test_execution_reliability.py tests/test_check_engine.py tests/test_post_crq_audit.py tests/test_post_crq_scheduler.py -q` — 34 passed.
- `git diff --check` — passed.
- Frontend `npm run lint`, `npm test`, and `npm run build` could not start because `eslint`, `vitest`, and `vite` are not installed (`node_modules` absent).

## Acceptance evidence

| Acceptance criterion | Evidence |
| --- | --- |
| AC-001–004 | `tests/test_execution_reliability.py` and focused run. |
| AC-005–006 | `tests/test_check_engine.py` and focused run. |
| AC-007 | `tests/test_post_crq_audit.py` passed with additive adapter integration. |

## Deviations and residual risks

The supplied certified SHA is not present locally, so certification provenance cannot be independently verified. The new durable lease is additive and not wired into the pre-existing dirty automation-store path. Legacy query exports remain legacy behavior; normalized evidence is redacted and excludes SQL/binds.
