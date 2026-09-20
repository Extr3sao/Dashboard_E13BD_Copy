# DEV Agent framework feedback — E13BD external evidence

| ID | Classification | Evidence | Proposed generic contract | Priority |
|---|---|---|---|---|
| DAF-001 | DEVAGENT_ENHANCEMENT | Backend source on NTFS still stalled when the interpreter/site-packages lived in OneDrive; a fully NTFS venv produced 251/251 in 244.13s. | `VERIFICATION_ENVIRONMENT_PROVENANCE` records source filesystem, tool executable, site-packages, TEMP/TMP and cloud-path detection; a policy can require local paths. | P1 |
| DAF-002 | DEVAGENT_ENHANCEMENT | PDF/ZIP distribution tests take 6–15s but complete with progress; global short timeouts would be false hangs. | `ADAPTIVE_TEST_WATCHDOG`: baseline-aware slow/expensive/stalled/hung states, heartbeat and per-test isolation before fail-closed timeout. | P1 |
| DAF-003 | DEVAGENT_ENHANCEMENT | E13BD generates SQLite/PDF/ZIP artifacts during tests. | `ARTIFACT_RESIDUE_DIFF` stores before/after classified snapshots and rejects unexplained residue. | P1 |
| DAF-004 | DEVAGENT_ENHANCEMENT | Python, ESLint, Vitest, build, Playwright and npm audit must be bound as one mixed-stack gate. | `MULTI_STACK_QUALITY_GATE` emits per-tool receipts tied to one source fingerprint. | P1 |

No E13BD-specific code belongs in DEV Agent. Acceptance fixtures should be abstract mixed-stack projects with a cloud-path fixture, a controlled slow artifact fixture, and negative residue/fingerprint controls.
# Certification-closure continuation — 2026-09-20

## P0 — certification correctness

`DEF-DEVAGENT-E13BD-CERT-001` is the E13BD traceability alias for the existing
generic set `DEF-VERIFY-ROUTING-001`, `DEF-TEST-RUNNER-001`,
`DEF-E2E-STUB-001`, and `DEF-CERT-GUARD-001`; it is not a newly invented product
defect. The generic repair is present in `C:\dev\devagent-fw` at
`6378d2bf` (repair range `eacdbb8..0a3683b`). Its release-binding pins honestly
fail because the repaired tree differs from immutable 4.5.1. The installed CLI
is older/unrepaired. Treat a successor re-seal, independent verification, and
exact-artifact installation as P0 prerequisites for project certification.

Independent verifier continuation: behavioral controls passed (six CLI/case
checks and 11/11 receipt mutations) and human-gate policy tests passed (five).
The verifier correctly refused successor authority: four release pins detect the
new repaired hashes, the declared pristine base commit is unavailable locally,
and a re-seal/install is not technically bound to human approval. Strengthen that
binding before any successor claim; do not bypass it by changing immutable 4.5.1.

## P1 — evidence provenance and residue diff

E13BD's previous green runs bind to earlier source; the current dirty tree must
not reuse them. Persist structured evidence with source/product/test/config
fingerprints and before/after SQLite/PDF/ZIP counts. `resources/test_automation_reports`
contains real report artifacts with unproven retention and must be preserved by
automatic cleanup.

## P2/P3 roadmap

Keep `VERIFICATION_ENVIRONMENT_PROVENANCE`, `ADAPTIVE_TEST_WATCHDOG`,
`ARTIFACT_RESIDUE_DIFF`, and `MULTI_STACK_QUALITY_GATE` as P1 candidates.
Keep `MODEL_ORCHESTRATION_DECOUPLING`, DecisionGateway, ModelGateway and Jev as
P2 experimental/shadow-only work. Jev has no certification authority and is not
activated by this certification closure.
# Next evolution feedback — 2026-09-20

## Dependency resolution must be a verifiable release gate

- **Problem:** A project can have a valid-looking unpinned `requirements.txt` while a clean install backtracks for an extended period and initially leaves required imports unavailable.
- **E13BD evidence:** The 2026-09-20 focused runtime gate initially could not import FastAPI/xhtml2pdf; `pip install -r requirements.txt` resolved the broad Google dependency graph slowly without a reproducible lock outcome.
- **Generalization:** DEV Agent should distinguish a manifest syntax check from a completed clean, isolated dependency resolution and report partial environments as a failed/incomplete gate.
- **Proposed DEV Agent capability:** Isolated-install evidence adapter that records interpreter, hashes/locked versions, resolver exit state, and import smoke results before allowing test evidence.
- **Acceptance test:** A fixture with unpinned conflicting/transitive dependencies must not be reported as reproducibly installed until an isolated environment completes and imports declared runtime roots.
