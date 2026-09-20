# E13BD Next evolution report

**Date:** 2026-09-20. **Baseline:** `39d733e7063a28beae538f649e1eb31b46789464`. **Status:** `IMPLEMENTED`, `TESTED`, `LOCALLY_VERIFIED` (focused slice only). This report does not claim independent verification or certification.

## Audit evidence

The code is a FastAPI + React/Vite application. `src/api/main.py` is a high-coupling API composition module with 97 endpoint decorators. Oracle access is wrapped through `OracleDBManager`; local SQLite persists internal/automation data via `InternalDBManager` and `AutomationStore`; reports use PDF/ZIP builders; `AutomationService` owns in-process scheduling, retries, and distribution. Existing retry queue locking and UTC helpers are present. No P0 product defect was proven by this review.

| ID | Priority / state | Problem and evidence | Affected scope | Impact / risk | Proposed solution, acceptance, tests, rollback | Classification |
|---|---|---|---|---|---|---|
| NEXT-001 | P1 DONE | No liveness/readiness route or uniform request correlation was found in the real API route/middleware inventory. | `src/api/main.py`, runtime tests | Slow incident diagnosis; low change risk. | Add dependency-free health routes and bounded request IDs, completion duration/status log fields; tests assert routes, IDs and redaction. Rollback: remove additive middleware/routes. | PROJECT_ONLY |
| NEXT-002 | P1 PLANNED | `requirements.txt` contains unpinned packages; a clean install attempted during this cycle backtracked on the Google dependency graph and initially left imports unavailable. | Python dependency workflow, CI | Non-reproducible local/CI setup; medium governance risk. | Produce reviewed constraints/lock for supported Python. AC: two clean installs resolve identical versions and full gate passes. Tests: clean install + gates. Rollback: restore prior manifest. | POTENTIALLY_GENERALIZABLE_TO_DEV_AGENT |
| NEXT-003 | P1 BLOCKED | High-impact configuration, distribution, purge and backfill endpoints have no independently established identity/role boundary. | API/security/deployment | Unauthorized mutation risk if exposed outside trusted network; high design risk. | Requires IdP, roles, segregation decision; AC: 401/403 integration tests. Rollback: deployment policy. | PROJECT_ONLY |
| NEXT-004 | P1 BLOCKED | Oracle external validation requires non-production credentials and DBA ownership. | Oracle integration | Live integration confidence gap; high external risk. | Least-privilege profile plus masked fixture protocol; AC: controlled smoke without secret disclosure. | PROJECT_ONLY |
| NEXT-005 | P2 PLANNED | `main.py`, `automation_service.py`, and `post_crq_audit.py` coordinate multiple domains; exception/log styles are inconsistent. | API/domain/reporting/automation | Change cost and diagnostics; medium risk. | Extract typed interfaces only behind contract tests; include redacted structured logging and correlation propagation to jobs. | POTENTIALLY_GENERALIZABLE_TO_DEV_AGENT |
| NEXT-006 | P2 PLANNED | Scheduler is process-local; retry queue has locks but multi-process singleton safety is not proven. | Scheduler/SQLite | Duplicate execution risk in multi-worker deployment. | Lease/ownership contract and restart/concurrency tests; no deployment change without topology decision. | PROJECT_ONLY |
| NEXT-007 | P2 PLANNED | PDF/ZIP work is intentionally expensive; partial artifact recovery is not proven end-to-end. | Reports/distribution | Recovery and observability gap. | Persist manifest, report operation IDs/counts/duration, failure-injection tests. | PROJECT_ONLY |
| NEXT-008 | P3 PLANNED | Frontend async/error UX varies among domains; performance has only test-duration evidence. | React UX/performance | Future usability/performance opportunity. | Shared accessible async states and representative workload benchmark after product data definition. | PROJECT_ONLY |

## This cycle — NEXT-001

`GET /healthz` and `GET /readyz` are local, credential-free endpoints. Every response gets `X-Request-ID`; only safe bounded values are preserved. The completion event records `event`, request ID, method, path, status, and duration. It excludes headers, query strings, bodies, passwords, tokens, and secrets. Local readiness intentionally does not call Oracle, SMTP, or AI.

Focused verification: `python -m pytest tests/test_main_runtime.py -q` → **43 passed**. The full backend command completed after the executor detached its output, so its result is **INDETERMINATE** and is not counted as green. The frontend gates are **BLOCKED locally** because the attempted `npm ci` left an incomplete dependency tree; this is recorded, not waived. No data, Oracle, SMTP, scheduler, or production operation was performed.

## Cross-cutting assessment

- Architecture: clear broad layers exist, but API composition and automation orchestration need future boundaries.
- Security: path traversal and generic internal error protections have tests; authN/authZ remains a deployment/design blocker. CORS is explicit but should be revisited with deployment origins.
- Reliability: retry queue and timestamps use explicit mechanisms; multi-process scheduler and artifact recovery need evidence.
- Observability: request-level correlation is now available. Job/PDF/distribution correlation remains planned.
- UX: no low-risk UI modification was justified during this backend-focused cycle.
- Performance: expensive PDF/distribution tests are legitimate per the prior profile; no speculative optimization was made.

## Traceability and certification boundary

`specs/operational-request-observability/` contains REQ → AC → design → task → test evidence. The permitted status is `LOCALLY_VERIFIED` for the focused slice. `INDEPENDENTLY_VERIFIED` and `CERTIFIED` are not claimed. Future certification requires the approved DEV Agent successor plus complete regression and external Oracle evidence.
