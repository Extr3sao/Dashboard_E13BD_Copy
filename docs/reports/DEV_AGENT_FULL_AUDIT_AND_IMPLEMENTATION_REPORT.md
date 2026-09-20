# DEV Agent full audit and implementation report

## Executive summary

This report closes all work safely possible from the 2026-09-18 forensic request. Dashboard E13BD is a FastAPI + React/Vite internal Oracle-audit application. It has strong existing product evidence, but is **not certified**: the separately verified DEV Agent 4.5.1 candidate has an open false-success path and its source authority is neither clean nor release-approved. No false PASS is claimed.

This delivery adds a credential-free Windows CI baseline and the requested strategic roadmap. It intentionally does not modify business data, credentials, framework source, or prior `.devagent` evidence.

## Initial state

- Project: `dashboard-e13bd-2695770f`; source HEAD: `756a00442255524b09c26727f5f06f200c0732ab` (`main`), clean before this delivery.
- Framework authority: `C:\Users\GVLLFR0035\OneDrive - Generalitat de Catalunya\Vault Job\30 - RECURSOS\30.09.- DEV Agentic Portable`.
- Declared framework candidate: DEV Agent 4.5.1, `REL-4.5.1-E6116BDBD69B`; immutable parent is 4.5.0. `VERSION` remains legacy `3.4.0`.
- Framework authority state at inspection: HEAD `ef80ade9591b2b22d3b70eb3206295838b6b4256`, with modified core, CLI, packaging, tests, release controls, reports, and untracked material. Release approval `APPROVE_RELEASE_4_5_1=PENDING`.

## DEV Agent framework verification

Identity and source layout were confirmed: `devagent.py`, `devagent_cli.py`, `core/`, `devagent_project/`, `scripts/`, `tests/`, policies, workflows, and release metadata exist. The four forensic requirements cannot be honestly marked repaired from this authority:

| Area | Independent evidence | Status |
|---|---|---|
| VERIFY_ONLY routing | CLI terminalizes `VERIFY_ONLY` as `AUDITED`, not verification | BLOCKED |
| Test runner | framework discovers root `unittest`, while this project declares `pytest` under `tests/` | BLOCKED |
| E2E | CLI injects a successful stub E2E callback | BLOCKED |
| Certification guard | orchestrator transitions through independent verification/certification without invoking a verifier | BLOCKED |

The previous independent control matrix correctly shows zero tests and failed tests block, but also shows a trivial test plus the stub E2E can end `CERTIFIED`. This is an open false-success vector; therefore `FALSE_SUCCESS=1` for framework certification and `FRAMEWORK_CERTIFICATION=NOT_CERTIFIED`.

Release-binding requires a clean implementation commit, controlled successor version, clean reconstruction, two reproducible wheels, isolated install, a true process/tool-isolated verifier, and human release approval. The observed dirty source and pending approval are real governance gates. Historical `REL-4.5.1-E6116BDBD69B` is left immutable. No framework release, tag, pipx installation, or successor identity was fabricated.

## Project baseline and architecture AS-IS

The React SPA in `src/web-app/` communicates with FastAPI at `src/api/main.py`. It supports Oracle obsolescence analysis, post-CRQ SQL checks, reports, automation scheduling and distribution. Oracle is external; SQLite stores internal checks, obsolets, automation jobs, retries, recipients, and templates through `src/core/internal_db.py`, `automation_store.py`, and `sqlite_paths.py`. Optional OpenRouter/AI and SMTP integration remain configuration/credential gated.

The source inventory has 207 files under `src`, `tests`, and `scripts`; 97 FastAPI endpoint decorators were found. Active domains include audit, post-CRQ, automation, checks administration, reports, profiles, and user help. Generated/dependency trees are excluded from source analysis.

## Audit methodology

The audit applied reproduce → isolate → understand → verify, then checked source control, prior independent verifier evidence, runtime/test commands, repository metadata, data-bearing paths, secrets policy, dependency declarations, and static code signals. Evidence is not promoted to certification when its authority is blocked.

## Findings and risks

- P0: none found in the product evidence.
- P1: DEV Agent verification/certification defects described above; unpinned Python dependencies; no prior CI workflow.
- P2: host-coupled legacy maintenance scripts (`fix_mojibake.py`, import helpers, PDF refinement test); large `post_crq_audit.py` and `automation_service.py`; broad exception handling needs domain-by-domain review; real Oracle E2E is unavailable without credentials.
- P3: test/reporting coverage expansion, structured observability, and UI workflow refinements.

## Obsolete data analysis and cleanup

Data-bearing locations were classified as follows: `data/snapshots/*.parquet` is authoritative/derived audit history (preserved); configuration and connection files are secret-bearing/unknown (preserved); `.devagent` is historical evidence (preserved); virtual environments, `node_modules`, `dist`, caches, and SQLite journals are regenerated artefacts when present.

No data was automatically removed in this run. The inspection found no local `*.db`, `-journal`, `-wal`, or `-shm` files. Previously reported 0-byte local databases and duplicate secret backup material are absent from this workspace but, if present elsewhere, require human review because provenance/sole-copy status cannot be proven. `DATA_AUTO_CLEANED=0`; `DATA_QUARANTINED=0`; `DATA_REQUIRING_HUMAN_APPROVAL=0` in this workspace.

## Code and implementation changes

| Change | Files | Why | Validation |
|---|---|---|---|
| Credential-free CI baseline | `.github/workflows/ci.yml` | Makes backend tests, lint, Vitest, build, and mocked Playwright smoke repeatable on Windows | Workflow review; equivalent local commands recorded in verification |
| Audit report | this file | Preserves the certification boundary and forensic evidence | Content/traceability review |
| Roadmap | `PROJECT_IMPROVEMENT_MASTER_PLAN.md` | Turns audit findings into bounded, testable next work | Content/acceptance review |

No backend, frontend, data model, API contract, or architecture change was made. No data cleanup was performed.

## Security, testing, observability, and documentation

The repository ignores `.env`, `config/.env`, connection profiles, and backup shapes; no secret values were read or emitted. The CI design consumes no secrets and deliberately excludes Oracle/SMTP/AI paths. Existing evidence records 250 backend passes, 79 frontend passes in 26 files, a Vite build, and mocked browser E2E; Oracle smoke remains `OPTIONAL_EXTERNAL_VALIDATION` because it requires a real profile, schema, and credentials.

CI is the observability improvement in this delivery: failures now become visible on pushes and pull requests. The next lightweight runtime observability priority is correlated request/job logging, documented in the roadmap.

## Before / after metrics

| Metric | Before | After |
|---|---:|---:|
| Versioned CI workflows | 0 | 1 |
| Product runtime changes | 0 | 0 |
| Automatic data deletions | 0 | 0 |
| Framework certification coverage | 0% | 0% (honestly blocked) |
| Product evidence coverage (prior verifier) | 100% | retained; current recheck recorded separately |

## Tests, E2E, clean workspace, and independent verification

Current command outcomes and any environment limits are recorded in `specs/dashboard-forensic-audit/verification.md`. The prior independently generated report at `docs/operations/devagent-evidence/VERIFICATION_REPORT.json` remains the authoritative historical evidence for the frozen candidate. It passes product checks but fails framework false-success controls, so it reports `NOT_CERTIFIED`.

## Certification, limitations, and rollback

`PROJECT_CERTIFICATION=NOT_CERTIFIED`. This is required by the framework’s open certification defect, not a product failure. Remaining human gates are: (1) framework source cleanup and governed successor release approval; (2) Oracle credential-backed E2E; (3) any secret rotation or deletion of possible sole-copy backups.

Rollback is additive and simple: remove `.github/workflows/ci.yml` and the three documentation/specification additions in a normal reviewed commit. No mutable data requires restoration.

## Final status

The requested audit and roadmap are delivered; a safe CI improvement is implemented. The product is evidence-backed but not framework-certified. Framework remediation must happen in the DEV Agent authority under a new governed successor release before this Dashboard can receive a trustworthy framework certificate.

## Continuation checkpoint — 2026-09-19

### Independent framework closure and release binding

The historical framework identity is preserved: annotated tag `v4.5.0-distribution` points to `ef80ade9591b2b22d3b70eb3206295838b6b4256` and declares `REL-4.5.0-778BAE502045`. The proposed `REL-4.5.1-E6116BDBD69B` is only a dirty, unapproved candidate (38 modified and 162 untracked entries, no 4.5.1 tag, `APPROVE_RELEASE_4_5_1=PENDING`) and is not a release. This resolves binding without rewriting history: 4.5.0 remains immutable; 4.5.1 is not bound; any repaired framework must become a newly named successor from a clean tree after process-isolated verification and human approval.

The independent verifier reconfirmed three blocking defects: `VERIFY_ONLY` is routed to `AUDIT_ONLY` and terminalizes `AUDITED`; the CLI supplies a successful E2E stub; and the orchestrator can transition to independent verification/certification without calling a real independent verifier. Historical A6 zero-test and failing-suite controls remain intact, but the false-success control remains open. Therefore `FRAMEWORK_CERTIFICATION=NOT_CERTIFIED`.

### Current Dashboard audit and safe implementation

Multi-role reviews found no proven P0 product issue. P1 decisions requiring humans are identity/authorization for high-impact endpoints, a retention policy for destructive purge, and non-production Oracle credentials. No data was deleted. Three ignored zero-byte SQLite files and historical logs are demonstrably regenerated residues; snapshots, configuration, DEV Agent evidence and uncertain files are preserved pending the clean-workspace classification.

One reversible low-risk hardening was implemented: `src/api/main.py` now logs unexpected server/Oracle connection errors while returning generic client-safe messages. `tests/test_main_runtime.py` adds a secret-shaped exception regression test. It changes neither successful API results nor stored data.

### Certification rule

Certification is withheld unless every current backend/frontend/build/mocked-E2E/clean-workspace gate passes and the framework has a clean, approved successor that rejects the three false-success vectors. Oracle/SMTP/AI E2E, identity design and destructive retention actions remain real human gates.
