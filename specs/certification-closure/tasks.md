# Tasks — certification closure

- [x] T1 Inventory and classify workspace; record safe cleanup. FR-001, AC-001.
  Verify: deterministic manifest and cleanup receipt. Dependency: none.
- [ ] T2 Measure residue and clean-workspace/restart gates. FR-002, AC-001.
  Verify: before/after counts and representative workflow. Dependency: T1.
- [ ] T3 Validate secrets, security and clean Python dependency installation.
  FR-003/004, AC-002. Verify: non-disclosing audit plus fresh environment. Dependency: T1.
- [ ] T4 Freeze candidate and reconstruct provenance-bound evidence. FR-005/006,
  AC-003. Verify: source manifest and evidence records. Dependency: T1-T3.
- [ ] T5 Reproduce, test and independently verify DEV Agent successor. FR-007,
  AC-004/005. Verify: regression, release and verifier package. Dependency: T4.
- [ ] T6 Install verified framework and execute E13BD VERIFY_ONLY. FR-008/009,
  AC-006. Verify: artifact fingerprint and terminal receipt. Dependency: T5.
- [ ] T7 Independently verify project, traceability and false-success controls.
  FR-010, AC-007. Verify: zero failed checks or explicit genuine human gate. Dependency: T6.
