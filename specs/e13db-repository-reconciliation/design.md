# Design

## Current-state evidence

- `analisis_bd` resolves to `https://github.com/Extr3sao/analisis_bd.git`.
- After `git fetch --all --tags --prune`, its advertised E13DB-001 branch and `main` both resolve to baseline `dcf3543`.
- `b56ef64` descends from `7eb7805` and the unrelated `Dashboard_E13BD_Copy` history, not from `dcf3543`.
- The expected E13DB-001 and frontend-auth object IDs are absent from all inspected worktrees/clones; a direct fetch of `980f54b86417677ad1593103cfc4d28eeb888a9e` from `analisis_bd` returned `not our ref`.

## Consolidation strategy

1. Preserve existing refs and the supplied local `b56ef64` head unchanged.
2. Do not recover, recreate, or refer to the unavailable historical objects.
3. Use `feature/e13db-001-003-consolidated` from the preserved local head as the new canonical line, adding only missing, tested functionality.
4. Keep E13DB-004 (findings, fingerprints, lifecycle and Red Flags) explicitly out of scope.

## Dependency recovery

The frontend's `node_modules` and two dated incomplete directories are regenerable partial installation artifacts. Verify cache, remove only those exact directories, then run `npm ci` from `src/web-app`.

## Validation strategy

AC-001: Git refs and the preserved current head are recorded without attempts to recreate missing history.
AC-002: HTTP auth/CSRF/CORS, secret redaction, strict SQL and SQLite runtime behaviour have automated tests.
AC-003: E13DB-002 durable recovery/retry and E13DB-003 isolated normalized rules pass their tests.
AC-004: backend full suite; frontend `npm ci`, lint, tests and build; security source checks; `git diff --check`; non-force publication.
