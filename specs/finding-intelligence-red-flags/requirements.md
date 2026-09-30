# E13DB-004/005 — Finding intelligence and Red Flags

## Goal

Turn valid `RuleResult` observations into durable, operator-actionable findings and deduplicated Red Flags. The canonical input is the persisted/returned post-CRQ rule result stream; E13DB-004 must not alter the meaning of existing audit payloads.

## Functional requirements

- FR-001: Persist stable findings, occurrences, lifecycle actions, target context and Red Flags in the existing SQLite operational store through idempotent schema creation.
- FR-002: Fingerprints MUST be SHA-256 of database, rule, object type and normalized owner/object name only.
- FR-003: Reconcile valid PASS/WARN/FAIL observations deterministically into NEW, PERSISTENT, WORSENING, IMPROVING, RESOLVED and REOPENED; ERROR/SKIPPED/unhealthy runs MUST never resolve a finding.
- FR-004: Preserve operator statuses and audit actor/reason/time for acknowledge, accepted risk and false positive.
- FR-005: Produce the specified Red Flag classes, deduplicate them across observations, assign explainable deterministic P1–P4 priority using severity, delta, persistence and target criticality.
- FR-006: Provide USER/CSRF-protected APIs for list/detail/history/actions, red flags, needs-attention and audit summaries.
- FR-007: Provide a UI view that prioritizes attention, shows reason/recommendation/history and allows lifecycle actions with reasons.
- FR-008: Integrate reconciliation after a valid API Post-CRQ audit and return its operational summary additively.

## Constraints and non-goals

- CON-001: No main changes, destructive migrations, silent SQLite fallback, credential leakage, service Bearer token in frontend, or E13DB-006 work.
- CON-002: Existing E13DB-001/002/003 contracts remain compatible.
- NG-001: ML, LLM, probabilistic prioritization, notification delivery and unrelated refactors are excluded.

## Acceptance criteria

- AC-001: Multi-run test proves fingerprint stability and all lifecycle deltas, including false-resolution protection.
- AC-002: Tests prove occurrence history, lifecycle action retention, target context and Red Flag dedupe/priority/explanation.
- AC-003: API tests prove USER/CSRF protection and output redaction.
- AC-004: UI renders a usable Needs Attention/detail workflow and frontend/backend full regression passes.
