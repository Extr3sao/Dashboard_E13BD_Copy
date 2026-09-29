# Tasks

- [x] T1 — Add shared time/status and retry-policy presentation helpers. `FR-002..003`; focused frontend test passed. Dependency: none. Not delegated.
- [ ] T2 — Enforce safe manual retry eligibility at enqueue and processing, plus an atomic durable claim and compact durable-attempt matrix. `FR-004..007`, `NFR-003`, `AC-004`, `AC-006..007`; backend regression remains pending. Dependency: T1 policy definition. Not delegated.
- [x] T3 — Load run-scoped delivery attempts and display retry context in run detail. `FR-002..003`, `NFR-001`; focused frontend test passed. Dependency: T1.
- [x] T4 — Add operational overview to home with bounded existing data. `FR-001`; static lint command launched without diagnostics. Dependency: T1.
- [ ] T5 — Run focused checks, automation regression, full regression, and record evidence. `AC-005`; dependency: T1-T4. Not delegated.
