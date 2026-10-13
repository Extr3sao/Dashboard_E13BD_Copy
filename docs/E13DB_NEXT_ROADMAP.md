# E13DB roadmap recommendation after milestones 001–011

## Delivery update (E13DB-013)

- E13DB-012 was delivered from `7be7f228b8404a2e910c01e311ca7c07502bac4a` on `feature/e13db-012-durable-audit-evidence`.
- E13DB-013 implementation is on `feature/e13db-013-oracle-deep-diagnostics`, based on that E13DB-012 SHA. It adds Oracle session/blocking, SQL/plan, workload-related statistics, segment-growth and capacity observations through the durable AuditRun pipeline. Fixture and real-API/browser verification is recorded in `docs/E13DB_013_IMPLEMENTATION_PLAN.md`; live Oracle certification is still pending.
- Diagnostic SQL is read-only and bounded. Fixtures and a real-API/browser SQLite smoke verify product integration; a live Oracle validation remains required before claiming Oracle-server certification.
- E13DB-014 remains the next roadmap milestone: baselines and regression intelligence beyond the current explicit, comparable-snapshot rules.

## Options assessed

| Candidate | User/DBA value | Risk reduction | Architecture leverage | Complexity | Reuse potential | Timing |
|---|---|---|---|---|---|---|
| A. Oracle Deep Diagnostics | VERY HIGH | HIGH | MEDIUM | HIGH | MEDIUM | **E13DB-013 implemented on its feature branch** after the 012 authority foundation; live Oracle verification is pending |
| B. Evidence, Capability & Reproducibility Foundation | HIGH | VERY HIGH | VERY HIGH | MEDIUM | HIGH | **Delivered as E13DB-012**; addresses false-success distinction and scheduled/manual audit divergence |
| C. Architecture Modularization | LOW visible value | MEDIUM | HIGH | HIGH | LOW | Do only extractions required by B, not a standalone rewrite |
| D. Product/UX Consolidation | MEDIUM | LOW/MEDIUM | LOW | LOW/MEDIUM | LOW | Do small walkthrough-driven fixes continuously; no evidence for a large redesign |
| E. Multi-Database Foundation | HIGH eventual value | MEDIUM | HIGH | VERY HIGH | MEDIUM | FUTURE; target and RuleDefinition contracts/capability snapshot are not stable enough |
| F. Scheduled audit/evidence reconciliation and external side-effect receipts | VERY HIGH | VERY HIGH | HIGH | MEDIUM/HIGH | HIGH | The core scope of 012: close the real scheduled-audit Findings gap and ambiguous send boundary before adding more diagnostics |

## Recommended E13DB-012

**E13DB-012 — Durable Audit Evidence, Capability Snapshots & Reconciliation (delivered)**

Why now:

1. Code inspection shows manual `/api/audit/post-crq/run` calls
   `FindingStore.reconcile_post_crq`, while the scheduled `AutomationService`
   path persists `job_runs`/analytics facts but has no FindingStore reconciliation
   call. The 010 browser fixture manually injected that integration, so its
   E2E does not prove production scheduler-to-Finding linkage.
2. Manual Post-CRQ reconciliation generates a random run ID when no ID is passed;
   retries therefore create additional occurrences rather than replaying one
   stable audit identity. Failure audits do not currently use the successful
   reconciliation receipt path.
3. Rule definitions already carry engine/version, privilege, license and
   capability fields, but effective target capabilities and rule version are
   not snapshot-bound to every AuditRun. This makes historical no-Finding
   outcomes ambiguous.
4. Alert SMTP is an external side effect before its durable SENT row commits;
   a process crash can make acceptance ambiguous and a later retry may duplicate
   the email.

012 should deliver one normalized, stable AuditRun/RuleResult contract for both
manual and scheduled audits; persist per-run source/rule/capability snapshots;
reconcile Findings/Red Flags/Investigations idempotently from that contract; add
a durable notification/report-delivery outbox with explicit `UNKNOWN` recovery
for crash-after-accept; and test restart/replay against exact persisted results.
Keep the current two SQLite stores unless the selected ownership boundary proves
they must change; do not begin with a rewrite.

Patterns to transfer: stable operation identity, explicit at-least-once semantics,
evidence-bound reconciliation receipt, versioned capability snapshot, failure
classification, bounded retry/cooldown, and typed operational event correlation.
Do not transfer: agent runtime, distributed worker leases/fencing while
single-worker SQLite remains the deployment model, or the entire DEV Agent
certification pipeline.

## Three-milestone sequence

### E13DB-012 — Durable Audit Evidence, Capability Snapshots & Reconciliation

* Unify manual and scheduled outputs through a versioned `AuditRun` + normalized
  RuleResult persistence contract; explicitly represent unavailable/skipped,
  partial and failed runs.
* Persist the rule-pack/source identity, engine/version and effective
  capability/privilege/license snapshot per audit.
* Reconcile Findings, Red Flags and Investigation triggers idempotently from a
  stable AuditRun identity across retries/restarts.
* Add delivery intent/receipt states and crash-after-side-effect reconciliation
  without claiming SMTP exactly-once.
* Acceptance: same audit input replay gives the same derived state; scheduled
  audit path produces visible Findings; absent Findings are distinguished from
  absent/ineligible evidence; SMTP UNKNOWN is not silently resent.

### E13DB-013 — Oracle Capability Discovery & Deep Diagnostics (implemented; live Oracle certification pending)

* Discover Oracle version and read-only view privileges per connection and bind
  the versioned capability snapshot to each AuditRun; capability-gate session,
  locking, SQL/plan, statistics, segment and storage probes.
* Default AWR/ASH to SKIPPED unless both explicit license acknowledgement and
  privilege are recorded; bounded rows/timeouts; no SQL binds or sensitive SQL
  text persisted.
* Add plan/statistics/blocking evidence and contradictions with deterministic
  Oracle-shaped fixtures; run against a non-production Oracle target before
  claiming live-server certification.

### E13DB-014 — Portable Target Adapters & Multi-Engine Readiness

* If product demand is established, define `DatabaseTarget` and adapter contracts
  against the stable capability/evidence model; first add one non-Oracle engine
  only with CI service, migrations, rule parity and investigation semantics.
* Keep Oracle as one adapter; do not add vendor-neutral abstractions for
  unimplemented capability.

If user evidence instead prioritizes UX, small improvements continue during each
milestone, but they do not displace 012’s scheduled audit/evidence correctness.
