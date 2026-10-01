# DEV Agent → E13DB transfer map

## Source authority and evidence boundary

**Latest certified source inspected:** DEV Agent 4.7.1,
`release/4.6.8-canonical-entrypoint` lineage; certified release
`REL-4.7.1-4478A6813F8D`; canonical source Git SHA
`ae7d5dfff9e5e8beb9386ec305663aa515b6f569`; governed release-flip commit
`1a06aaa92f87a0cee7152d1ac58c912de6192f46`. Its source fingerprint is
`4478a6813f8da8369f933b2fe5784331677a9e4cc0a68a9a68fe5f7d388d5c72`.
Evidence read in `C:\dev\devagent-fw-468-entrypoint\reports\v4.7.1`:
`RELEASE_IDENTITY_4_7_1.json`, `DEV_AGENT_4_7_1_REPORT.json`,
`FULL_REGRESSION.json`, `ADVERSARIAL_VERIFICATION_471.json`,
`TRACEABILITY_471.json`, `FRESH_CLONE.json`, `CI_SHA_BINDING.json`, provider
E2E and threat-model receipts. Reported suite: 2,914 passed / 0 failed / 11
skipped; five required CI jobs were SHA-bound. The release is operationally
certified with inherited governance exception GOV-EX-2026-001.

**Newest candidate inspected, not certified:** DEV Agent 4.7.2 at
`release/4.6.8-canonical-entrypoint`, current worktree head
`ee8a9a3749253ecb4835b6efd235987627ff1124` (including commits `eb25237` and
`ee8a9a3`). Its identity artifact binds canonical source SHA
`eb25237a8e77592574f56a1705f10a94c3c9d70d`, fingerprint
`9b758f933a5f1ea52e0f7f7108d8ae2607b7d0b0d5c0be47680635205ec61d89`, and says
`SEALED_NOT_CERTIFIED`; no certifying receipt was issued. Its available
`FULL_REGRESSION_472.json` is explicitly a 4.7.1 mandate on head `6bbd927...`,
not a full regression of the 4.7.2 sealed identity. The 4.7.2 certification-
pipeline code/contracts were inspected as candidate patterns only. No claim
here treats that candidate as certified or depends on its PASS claims. The
checkout was dirty and advancing during review; it was not modified.

No DEV Agent package, import, runtime, database, scheduler or state was added to
E13DB. The observed root checkout `C:\dev\devagent-fw` is a different, dirty
`feat/semantic-decision-layer` workspace and was not treated as the latest
certified release source.

## Pattern decision matrix

| Latest DEV Agent pattern | E13DB equivalent / gap | Decision | E13DB adaptation, evidence and limit |
|---|---|---|---|
| Persistent Run State | `job_runs`, `audit_runs`, Finding occurrence records; split between two SQLite files | ADAPT | Use one stable AuditRun ID across both stores and retain the complete run state/RuleResult lineage; not a generic runtime FSM |
| At-least-once execution | Scheduler retries and restart recovery exist | TRANSFER | State guarantee explicitly; every retried audit/reconciliation must use stable operation identity |
| Idempotent side effects | Finding fingerprint/occurrence uniqueness; report `(type,period)` uniqueness; alert key dedupe | ADAPT | Extend to delivery outbox and side-effect receipt; current external SMTP boundary remains ambiguous |
| Durable receipts | Finding reconciliation receipts and report calendar key; delivery attempts are separate | ADAPT | Generalize a small receipt contract only for audit reconciliation and external delivery, not every function call |
| Crash-after-side-effect reconciliation | SMTP accepted before delivery commit can lead to duplicate/unknown send | TRANSFER | Persist `PREPARED/SENDING/SENT/UNKNOWN` attempt identity and require reconciliation of uncertain sends; exactly-once still not claimed |
| Checkpoints | Audit/retention jobs can be long; E13DB restarts entire bounded job | FUTURE | First instrument duration/restart cost; checkpoint only large jobs with safe idempotent segments |
| Durable WAIT/SIGNAL | Maintenance windows are time intervals; no blocking workflow waits for operator | REJECT | No current workflow needs durable pausing; HTTP/browser should remain nonblocking |
| Durable claims | One SQLite scheduler lease/heartbeat; documented single worker, local DB | FUTURE | Current single-owner lease is proportionate. Revisit for multi-host/worker deployment |
| Fencing tokens | E13DB lease is owner/expiry based, no monotonic generation | FUTURE | Existing single-worker local SQLite architecture is the stated constraint; do not add distributed fencing until deployment changes |
| Failure classification | `RuleStatus.ERROR/SKIPPED`, `RunState`, delivery error classes; some rule failures collapse to ERROR | ADAPT | Normalize timeout/unreachable/auth/privilege/license/query/storage/cancel classes at adapters and preserve retryability |
| Bounded recovery | Retry count/backoff on checks and delivery; stale scheduler recovery | TRANSFER | Reuse finite per-target/per-channel attempts, record exhaustion and avoid retry storms |
| Circuit breaker | Alert dedupe/cooldown exists; no global SMTP channel breaker | ADAPT | Add per-channel bounded open/cooldown/probe once volume evidence warrants; isolate SMTP from Oracle auditing |
| Evidence authority | Findings evidence is redacted and linked to FindingOccurrence | ADAPT | Add source identity, producer/version and rule/capability snapshot; do not import DEV’s agent claim taxonomy wholesale |
| Evidence lineage | AuditRun→Finding occurrence→Red Flag→Alert/Investigation is partial | ADAPT | Bind all relationships to stable AuditRun/RuleResult identifiers; scheduled/manual path divergence is current gap |
| Precise invalidation | No re-derivation/invalidation graph for changed rule packs/capabilities | FUTURE | First persist rule and capability identity; then invalidate affected derived correlations only |
| Capability Registry | `RuleDefinition` has required capabilities; no discovery registry/snapshot per target | ADAPT | Add a small Oracle-target capability snapshot after audit, with explicit unknown/privilege/license outcomes |
| Capability snapshot | No per-AuditRun engine/version/privilege/license snapshot | TRANSFER | Snapshot these facts per run so “no Finding” can be distinguished from “rule not evaluated” |
| Canonical identity | Finding identity hash is normalized; rule/runtime identity not version-bound | ADAPT | Canonicalize target/rule-version inputs only where they define identity; preserve current Finding lifecycle identity |
| Reproducibility | Run/Occurrence history exists, effective rule/config snapshot is incomplete | ADAPT | Add an audit manifest with source SHA, rule-pack version, engine/version and safe config fingerprint |
| Artifact integrity | Backups use checksums and SQLite integrity; reports lack a common producer manifest/checksum | TRANSFER | Reuse content hash/version metadata for reports/exports where operators exchange artifacts |
| Replay | Findings can be viewed but not fully replayed because all RuleResults are not retained | ADAPT | Persist canonical normalized results then add dry-run derivation comparison; never requery Oracle for replay |
| Independent verification | Restore/integrity checks exist; no separate verifier for derived Finding projections | FUTURE | First preserve inputs/versions and make derivation deterministic; then independently compare a replay |
| IMPLEMENTED/VERIFIED/CERTIFIED distinction | Milestones have reports/tests, but runtime feature status is not a per-SHA evidence artifact | ADAPT | Use lightweight exact-SHA validation receipt; do not copy the full DEV lifecycle FSM into E13DB runtime |
| Requirement traceability | Tests/docs exist by milestone, not machine-linked to runtime audit findings | ADAPT | Keep lightweight Requirement→Implementation→Test→Execution evidence for critical controls only |
| Certification receipt | No committed product release validation receipt for each exact E13DB SHA | ADAPT | Consider a machine-readable CI/build/security/E2E receipt as release tooling, separate from audit truth |
| Exact-SHA binding | Git branch/commit is available; Operations does not report source SHA | TRANSFER | Expose git/build version in secret-free runtime manifest and bind test receipt to SHA |
| Typed durable events | Operations timeline events and business event tables exist | ADAPT | Standardize important audit/Finding/alert/backup event IDs with correlation/run IDs; do not event-source all state |

## Explicitly not transferring

* Multi-agent orchestration, specialized PLANNER/IMPLEMENTER/TESTER/VERIFIER
  agents, agent debate or provider routing: E13DB’s detection/investigation
  conclusions must remain deterministic and evidence-based.
* External Codex/provider adapters: no problem in E13DB requires generated
  production SQL or autonomous code edits; SQL execution remains allow-listed.
* DEV Agent’s planning DAG/convergence engine as a runtime dependency: this would
  duplicate E13DB’s scheduler and expand failure surface.
* Its distributed file claim/lease implementation: SQLite plus one worker is the
  current supported deployment; test the existing lease first.
* A full certification state machine inside the application. Release validation
  should be a separate CI/review receipt, not self-certified runtime state.

The 4.7.2 candidate’s DAG, candidate binding, exact invalidation and hash-chained
campaign recovery are promising for **release-validation tooling**, but remain
candidate patterns because 4.7.2 is explicitly SEALED_NOT_CERTIFIED and its
available full-regression receipt is bound to an older 4.7.1 head. Any future
adaptation requires execution of the candidate’s own verifier/regression on its
exact SHA first.
