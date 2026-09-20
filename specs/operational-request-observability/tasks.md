# Tasks

- [x] T-001 — Capture source evidence and baseline availability. Requirements: FR-001..003, NFR-001. Verification: route/log inventory and focused-command record. Dependency: none. Not delegated.
- [x] T-002 — Define bounded health and request-observability contract. Requirements: FR-001..003, NFR-001, CON-001. Verification: requirements and design review. Dependency: T-001. Not delegated.
- [x] T-003 — Implement additive routes and safe request middleware in `src/api/main.py`. Requirements: FR-001..003, NFR-001. Verification: focused runtime tests. Dependency: T-002. Not delegated.
- [x] T-004 — Add regression tests in `tests/test_main_runtime.py`. Requirements: AC-001..004. Verification: `python -m pytest tests/test_main_runtime.py -q` (43 passed). Dependency: T-003. Not delegated.
- [ ] T-005 — Establish reproducible Python and Node installs, then run full regression gates with authoritative receipts. Requirements: AC-001..007, CON-001. Backend evidence complete: `.venv-repro\\Scripts\\python.exe -m pytest -q --durations=10` passed 255 tests. Remaining: two clean Python installs, `pip check`, `npm ci`, audit, lint, Vitest, build, and mocked Playwright. Dependency: T-004. Not delegated.
- [x] T-006 — Expand and execute the observability security matrix. Requirements: FR-003..004, NFR-001..002. Verification: focused tests cover invalid IDs, 4xx/5xx, schema/duration, and secret redaction; full backend regression passed (255 tests). Dependency: T-004. Not delegated.
- [ ] T-007 — Record traceability and freeze only after the applicable backend gates pass. Requirements: AC-001..007. Verification: `verification.md`, clean workspace delta, commit/tree receipts. Dependency: T-005, T-006. Not delegated.
