# Project improvement master plan

## Vision

Make Dashboard E13BD a reproducible, secure and operable internal control platform: reliable locally, independently verifiable in CI, auditable around Oracle actions, and clear for operational users.

## What works well

FastAPI/React separation, SQLite path isolation, a substantial backend/frontend suite, mocked browser smoke, data bootstrap, and explicit real-Oracle opt-in are solid foundations.

## Prioritized roadmap

Every recommendation below includes priority, problem, proposal, value, effort, risk, dependencies, and an observable acceptance criterion.

### Quick wins (0–2 weeks)

| ID | Priority | Problem / proposal | Value | Effort / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|
| IMP-001 | P1 | Python dependencies are unpinned. Generate a reviewed lock/constraints file for the supported Python version. | Reproducible installs | M / M | Clean CI baseline | Two clean installs resolve identical versions; test/build pass. |
| IMP-002 | P1 | CI was absent. Keep and tune the new Windows CI workflow. | Regression visibility | S / L | GitHub Actions availability | Every PR runs backend, lint, Vitest, build and mocked smoke. |
| IMP-003 | P1 | Framework false-success permits untrustworthy certificates. Repair DEV Agent routing, test adapter, E2E contract, verifier binding, and successor release outside this repo. | Restores governance | L / H | Framework clean freeze + approval | Negative matrix and isolated verifier reject every fake path; successor is independently certified. |
| IMP-004 | P2 | Host-specific scripts reduce portability. Parameterize paths or archive/remove only after reference and runtime checks. | Portable maintenance | M / M | Legacy owner confirmation | No `C:\\Users\\...` source dependency remains; focused tests pass. |
| IMP-005 | P2 | Broad exception handlers obscure operational failures. Replace highest-risk cases with typed errors and structured context. | Diagnostics | M / M | API error-model decision | Failure-injection tests assert stable HTTP/error behaviour without secret leakage. |

### Short term (2–6 weeks)

| ID | Priority | Problem / proposal | Value | Effort / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|
| IMP-006 | P1 | Oracle E2E is manually credential-gated. Create a non-production, least-privilege Oracle test profile and masked fixture protocol. | Real integration confidence | L / H | DBA approval, credentials | Controlled Oracle smoke passes without exposing values. |
| IMP-007 | P2 | Large orchestration modules increase change risk. Extract post-CRQ report/normalization and automation scheduling services behind tested interfaces. | Maintainability | L / M | Contract tests | Existing API tests pass; new services have focused unit tests. |
| IMP-008 | P2 | Job and request troubleshooting lacks a uniform correlation model. Add request/job IDs and structured durations/failures. | Operations | M / L | Logging schema | One API request and one automation job emit correlatable, redacted records. |
| IMP-009 | P2 | SQLite concurrency and scheduler singleton behavior need explicit guarantees. Add lock/lease policy and restart/concurrency tests. | Reliability | M / M | Deployment topology | Concurrent scheduler starts yield exactly one active executor. |
| IMP-010 | P2 | Error/loading UX varies by domain. Define shared async-state components and accessible error recovery. | UX/accessibility | M / L | Frontend design review | Keyboard and screen-reader tests cover loading/error/retry states. |

### Medium term (1–3 months)

| ID | Priority | Problem / proposal | Value | Effort / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|
| IMP-011 | P2 | SQL checks require stronger governance. Version catalog changes with review metadata, validation and rollback. | Auditability | L / M | Data migration plan | Every check has version, author, validation result, and rollback path. |
| IMP-012 | P2 | AuthN/AuthZ scope is not independently proven. Model roles and protect configuration, checks, automation and reports. | Security | L / H | Identity provider decision | Unauthorized users receive no data/action access in integration tests. |
| IMP-013 | P2 | Reports need durability guarantees. Persist generation manifests and add partial-failure recovery. | Reliable reporting | M / M | Storage retention policy | Interrupted report generation is resumable/idempotent and documented. |
| IMP-014 | P3 | Performance is unmeasured. Establish representative audit workload benchmarks and query timeout budgets. | Predictability | M / M | Safe test dataset | CI/perf job records baseline; budget breaches are visible. |
| IMP-015 | P3 | Operational docs can drift. Generate endpoint/config/test inventory checks in CI. | Developer experience | M / L | Documentation format | CI detects unreferenced or undocumented operational commands. |

### Long term (3+ months)

| ID | Priority | Problem / proposal | Value | Effort / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|
| IMP-016 | P2 | Deployment contracts are implicit. Package a supported deployment topology with migrations, health/readiness checks, backup/restore runbook, and rollback. | Operability | L / H | Platform/operations approval | A clean target environment deploys, verifies health, and rolls back successfully. |
| IMP-017 | P3 | Data quality trends are hard to compare. Add governed historical trend views with retention and ownership rules. | Product insight | L / M | Data governance | Trend totals reconcile to authoritative snapshots. |
| IMP-018 | P3 | AI is optional and provider-dependent. Add human-reviewed, redacted AI assistance only for explanations—not autonomous control decisions. | Productivity | L / H | Security/privacy review | Evaluated prompts never send secrets; all suggestions require human confirmation. |

## Strategic themes

The recommended execution order is IMP-003 and IMP-001/002 first, then Oracle validation, typed failures and observability, then scheduler/SQLite and modularization, finally identity, deployment, data trends and AI. This order protects governance before feature velocity.

## Things not worth doing now

Do not redesign the UI wholesale, migrate databases, add AI control automation, delete historical data, or replace the framework merely to obtain a certificate. None is justified by current evidence without a product/architecture decision.

## Risks and preconditions

Oracle, SMTP, real report distribution, identity integration, secret rotation, production deployment, and destructive data cleanup require their respective owners. Each recommendation must retain the existing no-false-success rule: implementation is not verification, and verification is not certification.

## Multi-role continuation priorities

Independent framework, technical, and functional reviews agree: no P0 is proven; governance of effects comes before feature expansion. The secret-safe error response portion of IMP-005 is now implemented and regression-tested. The next proposals remain unimplemented until their stated gates are met.

| ID | Priority | Problem / proposal | Value | Effort / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|
| IMP-019 | P1 | Purge/retry/job/backfill actions need preview, reason, strong confirmation, and a manifest before effect. | Prevents accidental loss/actions | M / M | Retention owner; actor identity | Cancel sends no API request; confirmation records scope/reason/actor/parameter hash; purge manifest lists candidates and exclusions. |
| IMP-020 | P1 | High-impact configuration, credential, check, automation and report endpoints lack proven authorization. Add corporate identity, roles and endpoint permissions. | Protects sensitive operations | L / H | Human IdP, role and segregation decision | Integration tests prove unauthorized calls receive 401/403 and cannot read/mutate protected data. |
| IMP-021 | P1 | Automatic purge defaults do not prove data is obsolete. Make retention opt-in after preview, quarantine period and policy approval. | Protects evidence/data | M / M | Retention policy and owner | No automatic permanent deletion; policy-approved purge emits a reviewed manifest and honors holds. |
| IMP-022 | P2 | Request, job, retry and delivery cannot be correlated consistently. Add redacted correlation IDs and structured timing/outcome logs. | Faster incident resolution | M / L | Logging schema | One test proves a request-to-delivery chain shares a redacted correlation ID. |
| IMP-023 | P2 | Operations lack durable closure context and partial Post-CRQ recovery. Add evidence-linked task lifecycle and retry-only-failed checks. | Better operational throughput | M / M | Actor model, API contract | Resolved task requires result/reason; retry preserves base execution and only runs failed checks. |
| IMP-024 | P2 | Shared links and accessibility recovery are incomplete. Persist non-secret audit context in URL; replace alerts with focus-managed aria-live errors/retry. | Reproducible, accessible UX | M / L | Frontend design review | A copied URL restores profile/subview/filter safely; keyboard/error/retry tests pass. |
