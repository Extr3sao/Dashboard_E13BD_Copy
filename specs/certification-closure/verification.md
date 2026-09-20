# Verification — certification closure

This record starts from the authoritative user-supplied baseline: backend
251/251, Oracle 41/41, frontend 79/79, lint/build/mock E2E and npm audit zero.
Those results are not repeated unless a later source fingerprint invalidates
their authority. New records will distinguish direct execution from historical
evidence and will never infer a passing gate.

## Continuation observations

| Gate | Direct observation | Status |
|---|---|---|
| Workspace inventory | Deterministic non-disclosing inventory recorded in `docs/reports/WORKSPACE_CLEANLINESS_REPORT.md`. | PASS (inventory only) |
| Safe cleanup | Executor rejected the removal command before execution; protected artifacts remain. | INCOMPLETE |
| Fresh Python install | Isolated venv created; pip resolution did not conclude within executor window. | INCOMPLETE |
| Framework source authority | Repair source is clean at `6378d2bf`, but immutable 4.5.1 pins intentionally differ and release approval is pending. | BLOCKED pending independent verification/release governance |

| Frozen E13BD backend | `python -m pytest -q` | PASS: 251 tests, 2 warnings, 409.68 s |
| Frozen frontend lint | `npm run lint` | PASS: exit 0, no findings |
| Frozen frontend tests | `npm test -- --no-file-parallelism` | PASS: 26 files, 79 tests, 126.63 s |
| Frozen frontend build | `npm run build` | PASS: 41.03 s; non-blocking chunk-size warning |
| Frozen mocked E2E | `npm run smoke:ui` | PASS: smoke success |
| Frozen npm audit | `npm audit --omit=dev --json` | PASS: 0 vulnerabilities |
| Clean Python install | fresh `dashboard-e13bd-cert-cleanpy2`, `pip install -r requirements.txt`, `pip check`, test collection | PASS: 251 tests collected; pip check exit 0; slow resolver/install with observed progress |

## Framework base and regression continuation

`FRAMEWORK_BASE_RECOVERY = PASS (local content)`: exact commit
`ddb00aebfa0479def7444904aa9e7154c6d150cc` was recovered in the clean local
baseline checkout, with tree `cec421e38939dbe2ad54053e7493c53d0589067c` and
passing `git fsck --full --strict`. Original OneDrive provenance is asserted by
local records only.

The canonical framework suite `py -m pytest tests -q` ran at repair commit
`6378d2bf`: 2445 passed, 19 failed, 9 skipped in 1097.96 s. Four failures are
the expected immutable 4.5.1 identity-pin mismatches. Fifteen further failures
lack a comparable authoritative baseline and block successor release readiness.

## Independent framework-verifier evidence

Verifier source: `C:\dev\devagent-fw`, HEAD
`6378d2bf586d87e25fa33a5929e4055613797b5b`. The verifier independently observed:

| Check | Result |
|---|---|
| Six targeted real CASE/CLI tests (zero/failing tests, no-E2E/trivial false-cert, builder-E2E inadmissibility, VERIFY_ONLY routing) | PASS, 6 in 22.28s |
| Receipt tamper probe | PASS: baseline valid, digest recomputed, 11/11 mutations detected |
| Human-gate policy tests | PASS, 5; release policy reports `APPROVAL_REQUIRED` |
| Four release-pin controls | FAIL as expected/intentional: repaired full/core hashes `83ac5e38…a500`/`551bf201…a886` differ from sealed 4.5.1 `e6116bdb…4933`/`2dc8f989…9f75` |

The verifier did not treat the intentionally failing identity pins as a passing
successor release. It also found that declared base commit `ddb00aeb…` is absent
locally, and that no technical command gate currently binds a successor
re-seal/installation to the human approval record. Full-suite output was not
captured and is therefore unasserted. `FRAMEWORK_INDEPENDENT_VERIFIER = PARTIAL`.
