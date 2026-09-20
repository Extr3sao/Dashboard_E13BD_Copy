# Design — certification closure

## Evidence flow

`inventory -> safe cleanup -> clean environment -> frozen candidate -> bound
evidence -> verified framework release -> installed artifact -> VERIFY_ONLY ->
independent project verifier -> certification`.

The product checkout is evidence-only: its application, tests and configuration
are not changed. Reproducible caches and test residue may be removed only after
classification; all other material remains in place. Evidence records are stored
as structured JSON plus concise reports, with hashes binding them to the frozen
candidate.

## Framework boundary

The DEV Agent repair is generic and lives only in its own source checkout. A new
successor release is required because its tree differs from immutable 4.5.1.
The builder's report is not certification authority: a distinct verifier package
must validate the release and artifact fingerprint. The Dashboard can consume
only that exact installed artifact.

## Failure handling

Missing secrets, unknown paths, source-fingerprint drift, invalid evidence,
missing verifier material, nonzero residue deltas, or unavailable required
governance terminate the relevant gate as blocked/fail; none are converted to
PASS by narrative inference.

## Validation mapping

AC-001: inventory, residue and restart observations. AC-002: fresh isolated pip
install and import/test dependency inspection. AC-003: git/hash manifest.
AC-004/005: framework regression plus independent package checks. AC-006:
actual CLI receipt and before/after hashes. AC-007: project verifier matrix.
