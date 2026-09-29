# Tasks

- [x] T-001 — Inventory refs, worktrees, target remote, objects, and reflogs. Satisfies FR-001, FR-002, AC-001. Verification: Git inspection and fetch.
- [x] T-002 — Test authoritative retrieval of the full E13DB-001 certification commit. Satisfies FR-002, CON-002, AC-002. Verification: direct `git fetch`.
- [x] T-003 — Use the requested new canonical branch from the preserved local head; do not recreate missing history. Satisfies FR-001, FR-002. Verification: branch/HEAD inspection.
- [x] T-004 — Close runtime-safety gaps: USER/CSRF middleware, configurable restrictive CORS, secret handling, strict SQL, and durable SQLite/recovery. Satisfies FR-003–FR-006. Verification: full regression and security tests.
- [ ] T-005 — Execute full backend/frontend regression and publish the canonical branch without force. Satisfies FR-007, AC-002–AC-004. Verification: `verification.md`.
