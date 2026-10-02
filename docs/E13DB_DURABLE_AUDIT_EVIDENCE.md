# Durable Audit Evidence

## AuditRun identity and execution

The manual Post-CRQ endpoint and scheduled Post-CRQ jobs execute the same audit
runner and persist the same normalized evidence before reconciliation. Manual
requests may provide `audit_run_id`; the Post-CRQ UI creates one for each live
execution. Scheduled identity is derived from the job ID and scheduled
reference, so retrying one tick reuses its AuditRun while a later tick gets a
new identity. The `job_runs.audit_run_id` field links scheduler history to the
authoritative record.

`GET /api/audit-runs` lists durable runs. `GET /api/audit-runs/{audit_run_id}`
returns runtime identity, target context, attempt history, rule results,
capability snapshot, evidence references and the reconciliation receipt.
Automation history and the manual Post-CRQ result surface the AuditRun ID.

## State and recovery

An AuditRun moves through `RUNNING` to `SUCCESS` or a classified failure. A
successful execution is persisted before Findings, Red Flags and Alerts are
reconciled; its reconciliation state remains `PENDING` until that projection
commits and the receipt is recorded. Startup recovery marks abandoned running
attempts interrupted and retries completed-but-unreconciled projections.
Finding reconciliation receipts and stable finding/observation identities
prevent duplicate occurrences if the process stops between projection and
receipt publication.

This is at-least-once execution with idempotent reconciliation, not exactly-once
execution. An unavailable capability or incomplete rule evaluation is recorded
as `SKIPPED`, `ERROR`, or degraded coverage; it never counts as a passing rule
or evidence that an existing Finding has cleared. Legacy rows retain
`LEGACY`/`UNKNOWN` provenance instead of receiving fabricated runtime or rule
metadata.

## Capability and licensing policy

Capability discovery uses bounded, allow-listed, read-only dictionary probes.
Rule requirements are gated only when explicitly declared. If privilege
discovery itself is unavailable, the result is recorded as unknown rather than
asserting that the privilege is absent. AWR and ASH views are not queried by
this audit path; their rule gates remain closed unless license and privilege
configuration explicitly permits them.

## SMTP delivery ambiguity

Before an immediate alert email is sent, an `ATTEMPTING` notification-outbox
record is committed. Confirmed delivery becomes `SENT`; local configuration
failure becomes `FAILED`. A timeout or process loss with an unknown SMTP
outcome becomes `AMBIGUOUS`. Ambiguous attempts are exposed in alert delivery
history and notification health and are not automatically resent. This avoids
duplicate emails when the remote SMTP server may already have accepted a
message.

## Verification

The focused regression suite is:

```text
python -m pytest tests/test_audit_evidence.py tests/test_alerting_engine.py tests/test_automation.py
```

Post-CRQ UI checks are in `src/web-app/src/hooks/usePostCrqAudit.test.jsx` and
`src/web-app/src/views/PostCrqAuditView.test.jsx`.
