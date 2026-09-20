# Dashboard forensic audit

## Context

Dashboard E13BD is a FastAPI/React application. Its prior independent verification found a framework false-success defect, so the product must not be certified through that framework until the defect is repaired and independently verified.

## Goals

- Produce the two requested reports from current, reproducible evidence.
- Improve continuous verification without requiring Oracle credentials.
- Preserve all product data, secrets, and existing DEV Agent history.

## Non-goals

- Repair, release, tag, publish, or install the dirty DEV Agent 4.5.1 authority.
- Validate live Oracle, SMTP, or AI-provider integrations.
- Delete unknown, user, business, secret, or historical evidence data.

## Functional requirements

- FR-001: The repository MUST include the requested audit/implementation report.
- FR-002: The repository MUST include a prioritized future-improvement roadmap with testable recommendations.
- FR-003: CI MUST run backend tests, frontend lint/tests/build, and the mocked browser smoke on Windows without credentials.
- FR-004: Reports MUST separate observed evidence from certification claims and record framework blockers.
- FR-005: Unexpected server and Oracle connection errors MUST NOT return raw exception text to API clients.

## Constraints

- CON-001: No production, credential, or irreversible data action is permitted.
- CON-002: Framework verification may not claim certification while its release authority is dirty, unapproved, and demonstrably false-success prone.
- CON-003: Existing `.devagent` history is immutable for this task.

## Acceptance criteria

- AC-001: `docs/reports/DEV_AGENT_FULL_AUDIT_AND_IMPLEMENTATION_REPORT.md` exists with all requested audit sections and exact status qualifiers.
- AC-002: `docs/reports/PROJECT_IMPROVEMENT_MASTER_PLAN.md` exists and every recommendation includes ID, priority, problem, proposal, value, effort, risk, dependencies, and acceptance criteria.
- AC-003: `.github/workflows/ci.yml` runs the declared no-credential backend and frontend commands on Windows.
- AC-004: Verification records the command results or an explicit environmental limitation; no PASS is inferred.
- AC-005: A focused runtime test proves a secret-shaped exception is logged server-side but not returned in a 500 response or connection-test result.

## Assumptions and decisions

- The existing independent report is historical evidence, not a replacement for current verification.
- Mocked browser smoke is the only credential-free mandatory E2E. Oracle smoke remains a human/credential gate.
