# E13DB consolidated line — requirements

## Context

The historical E13DB commits are unavailable. The canonical line MUST preserve the current functional work at `b56ef64` and consolidate runtime safety, authentication, execution reliability, and the check engine without inventing Git history.

## Goals

- FR-001: Preserve all existing work, including `b56ef64`, without modifying `main`.
- FR-002: Create `feature/e13db-001-003-consolidated` from the current head without changing `main` or deleting existing branches.
- FR-003: Provide opaque server-side USER sessions, login, `/auth/me`, logout, expiry, rotation, CSRF validation, and USER/SERVICE separation.
- FR-004: Secrets MUST remain server-side and be redacted from API responses, logs, and evidence; SQL MUST be read-only.
- FR-005: SQLite MUST use foreign keys, WAL, busy timeout and no silent in-memory fallback; scheduler startup MUST be opt-in with stale lease recovery.
- FR-006: The frontend MUST bootstrap `/auth/me`, use cookies plus CSRF, provide login/logout and safely handle 401 without a service Bearer token.
- FR-007: Preserve and validate execution-reliability and normalized check-engine contracts on the same head.

## Non-goals

- Recovering or fabricating the missing historical commits.
- E13DB-004 or E13DB-005 work.
- Modifying or merging `main`.

## Constraints

- CON-001: No destructive Git operations, branch deletion, clone deletion, force push, or changes to `main`.
- CON-002: Preserve pre-existing local changes and make only scoped corrections.
- CON-003: Publish the completed branch to `origin` without force.

## Acceptance criteria

- AC-001: The target remote and all locally available relevant refs/objects are inventoried and the known commit locations are recorded.
- AC-002: Auth/session/CSRF/policy, read-only SQL, secret redaction, CORS and SQLite/scheduler runtime behaviours have automated evidence.
- AC-003: E13DB-002 reliability and E13DB-003 rule contracts pass their tests.
- AC-004: `npm ci`, frontend lint/tests/build, full backend regression, security checks and `git diff --check` pass; the branch is published.
