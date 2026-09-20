# DEV Agent successor release approval package

## Proposed release

- **Proposed version:** 4.5.2 (semantic patch successor to immutable 4.5.1;
  no conflicting local successor exists).
- **Source commit:** `6378d2bf586d87e25fa33a5929e4055613797b5b`.
- **Source fingerprint:** `83ac5e38…a500` (independently recomputed repaired
  tree); core fingerprint `551bf201…a886`.
- **Distribution fingerprint:** PENDING. No wheel may be treated as a 4.5.2
  distribution until release engineering performs the governed identity/version
  transition after approval.

## Defect closure

The candidate contains generic fixes for VERIFY_ONLY routing, declared-test
authority, fail-closed E2E authority, independent-verifier binding,
certification guards, terminal receipts, and release/source binding. It has no
E13BD-specific framework logic.

Independent controls already observed: six CLI/behavioral controls passed;
receipt tamper probe detected 11/11 mutations; five human-gate policy tests
passed. Four 4.5.1 identity pin failures are expected and required: the repaired
tree must not impersonate `REL-4.5.1-E6116BDBD69B`.

## Base recovery and provenance

The declared pristine base was recovered locally at
`C:\dev\devagent-fw-baseline`, commit
`ddb00aebfa0479def7444904aa9e7154c6d150cc`, clean tree
`cec421e38939dbe2ad54053e7493c53d0589067c`; `git fsck --full --strict`
passes. Its release identity matches the immutable 4.5.1 fingerprint
`e6116b…d4933`. The claimed OneDrive origin is locally documented but has no
remote-backed provenance proof.

## Regression and risk

The unscoped `pytest -q` is invalid for this monorepo: it collects archived
release/report copies and fails with import-file collisions. The canonical
candidate command is `py -m pytest tests -q`. It completed with **2445 passed,
19 failed, 9 skipped, 10 warnings** in 1097.96 seconds.

Four failures are the expected immutable-identity pins. Fifteen additional
failures concern distribution/resource/CLI/release-binding reproducibility and
dogfood identity flows. No authoritative baseline was available to prove them
pre-existing, so they are release-blocking until diagnosed and either repaired
or baseline-differenced. `FRAMEWORK_RELEASE_READY = NO`.

## Required approval

After technical closure, release engineering must approve or reject the 4.5.2 successor, then regenerate
identity and distribution manifests, build an immutable wheel, bind its hash to
independent verification, and preserve all 4.5.1 records byte-for-byte.

**Rollback:** retain 4.5.1 as immutable historical identity and revert the
installed 4.5.2 artifact to the prior governed release only through the release
procedure. No identity rewrite or in-place reseal is allowed.

**Open risks:** missing remote provenance for the recovered base; 15 unexplained
framework-regression failures; successor distribution verification pending.
