# Tasks

- [x] T1: Freeze evidence and classify framework release boundary. Scope: Git/evidence only. Requirements: FR-004, CON-002. Verify: status and existing verifier report. Dependency: none. Delegate: no.
- [x] T2: Add credential-free Windows CI. Scope: `.github/workflows/ci.yml`. Requirements: FR-003, CON-001. Verify: workflow inspection and local lint run. Dependency: T1. Delegate: no.
- [x] T3: Write the audit/implementation report. Scope: `docs/reports/DEV_AGENT_FULL_AUDIT_AND_IMPLEMENTATION_REPORT.md`. Requirements: FR-001, FR-004. Verify: AC-001 review. Dependency: T1/T2. Delegate: no.
- [x] T4: Write the improvement master plan. Scope: `docs/reports/PROJECT_IMPROVEMENT_MASTER_PLAN.md`. Requirements: FR-002. Verify: AC-002 review. Dependency: T1/T2. Delegate: no.
- [x] T5: Execute and document final verification. Scope: `specs/dashboard-forensic-audit/verification.md`. Requirements: AC-003, AC-004. Verify: command outputs/explicit execution limitation. Dependency: T2-T4. Delegate: no.
- [x] T6: Redact unexpected API/Oracle exception text. Scope: `src/api/main.py`, `tests/test_main_runtime.py`. Requirements: FR-005, AC-005. Verify: focused runtime test. Dependency: T1. Delegate: no.
