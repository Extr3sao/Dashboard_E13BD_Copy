# E13BD certification closure

## Context

The Dashboard E13BD product has current successful regression evidence but is not
certified. The governing DEV Agent repair must be independently released and
installed before an authoritative, immutable `VERIFY_ONLY` project run can be
accepted.

## Goals

- Establish reproducible workspace, dependency, secret, residue, security and
  evidence controls without changing Dashboard product behaviour.
- Use the actual, independently verified DEV Agent release for an immutable
  project verification run.
- Certify only when every mandatory gate has direct authoritative evidence.

## Non-goals

- Add Dashboard features or E13BD-specific DEV Agent logic.
- Delete business data, secrets, unknown files, or historical evidence.
- Re-run already authoritative green product gates unless the frozen source
  fingerprint changes.

## Requirements

- FR-001: The workspace MUST have a deterministic inventory and a safe cleanup
  record that preserves non-reproducible or unknown material.
- FR-002: SQLite, journal, WAL, SHM, PDF and ZIP residue MUST be measured before
  and after the relevant workflow; unexpected deltas MUST be zero.
- FR-003: A fresh Python environment MUST install only declared dependencies;
  undeclared runtime and test dependencies MUST be zero.
- FR-004: Secret hygiene and security review MUST avoid emitting secret values
  and record whether any rotation requires human action.
- FR-005: The product candidate MUST be frozen with unambiguous source,
  product, test and configuration fingerprints before authority is reconstructed.
- FR-006: Each mandatory result MUST be bound to a run id, command, exit code,
  source fingerprint, environment, tool identity and artifact reference.
- FR-007: The existing generic DEV Agent certification defect MUST be reproduced
  and the successor release independently verified before installation.
- FR-008: The installed release MUST exactly match the independently verified
  distribution before it runs E13BD `VERIFY_ONLY`.
- FR-009: `VERIFY_ONLY` MUST terminalize and leave product fingerprints unchanged.
- FR-010: Mandatory requirements MUST be traceable to execution, evidence,
  verifier and certification, with no invalid orphans.

## Constraints

- CON-001: Preserve the user-owned dirty product tree and pre-existing evidence.
- CON-002: Do not alter Dashboard production/test/config code as part of this closure.
- CON-003: Do not reuse DEV Agent 4.5.0/4.5.1 release identity.
- CON-004: Human approval is required only where release governance or real
  credential-backed integration requires it.

## Acceptance criteria

- AC-001: Inventory, cleanup, secret, residue and clean-restart records are
  direct observations and classify every retained item.
- AC-002: Fresh Python install passes from declared manifests with zero
  undeclared dependencies.
- AC-003: A frozen candidate has complete fingerprints and unambiguous changes.
- AC-004: DEV Agent has a documented pre-fix failing regression and post-fix
  passing generic regression, independently verified in a successor release.
- AC-005: A controlled installed artifact passes the required framework checks
  and matches its independently verified fingerprint.
- AC-006: E13BD `VERIFY_ONLY` produces a terminal receipt without product changes.
- AC-007: Independent project verification has zero failed checks and complete
  requirement traceability, or certification remains explicitly blocked.
