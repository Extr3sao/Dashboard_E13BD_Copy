# Dashboard forensic audit and delivery

## Goal

Record an evidence-led current forensic audit, deliver the mandatory reports, and add a non-destructive CI baseline without claiming framework certification.

## Tasks

- [ ] Freeze and recheck source, framework provenance, evidence, and data candidates → Verify: Git status, independent evidence, and filesystem inventory.
- [ ] Define governed scope and acceptance criteria in `specs/dashboard-forensic-audit/` → Verify: requirements/design/tasks map every deliverable to a check.
- [ ] Add a Windows CI baseline for declared backend and frontend checks → Verify: workflow syntax reviewed and the same commands run locally where available.
- [ ] Produce implementation/audit and improvement-roadmap reports → Verify: both requested paths exist and contain evidence, risks, and acceptance criteria.
- [ ] Run focused and full relevant verification, then record evidence → Verify: test/build/smoke outputs and `verification.md`.

## Done When

- [ ] The reports distinguish verified product evidence from blocked framework certification.
- [ ] CI covers lint, unit tests, build, and mocked E2E without credentials.
- [ ] No secrets, business data, framework source, or irreversible data is changed.
