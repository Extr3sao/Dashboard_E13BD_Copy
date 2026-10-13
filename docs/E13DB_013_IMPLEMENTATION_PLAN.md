# E13DB-013 implementation and verification record

## Baseline

- Branch: `feature/e13db-013-oracle-deep-diagnostics`
- Required starting SHA: `7be7f228b8404a2e910c01e311ca7c07502bac4a`
- E13DB-012 working tree was clean at that SHA.
- Reproduced before changes: the focused E13DB-012 evidence, scheduler, alert and RuleResult tests passed (`68 passed`). This included scheduled `execute_job` reconciliation/replay and SMTP ambiguity tests; these use deterministic SQLite/Oracle fixtures, not a real Oracle server.
- The local `plan-writing` and `systematic-debugging` skill files were not present. This plan and the reproduce/isolate/verify sequence are the documented fallback.

## Existing coverage inventory

| Area | Coverage at baseline | Limitation | E13DB-013 change |
|---|---|---|---|
| Sessions | Post-CRQ does not inspect live sessions; `V$SESSION` only appeared in E13DB-012 capability probes. | No bounded status, wait, SQL_ID, transaction or history observations. | `ORACLE_SESSIONS` records bounded current-instance/cluster rows, transaction markers when visible, and explicitly avoids declaring an unblocked long call stalled from one sample. |
| Blocking | No lock-chain diagnostic rules. Capability probe tests `V$LOCK`. | No root, affected-session, depth or sample-history correlation. | `V$SESSION`/`GV$SESSION` edges are confirmed against `V$LOCK`/`GV$LOCK`; composite instance/container/SID/SERIAL identity and stable root Finding. |
| SQL | Post-CRQ is a recent-DDL quality catalogue (12 checks), not runtime SQL monitoring. | No cumulative counters, rates or comparable deltas. | Bounded `V$SQLSTATS`/`GV$SQLSTATS` (fallback to SQL views only when capability allows), per-execution metrics and reset/no-new-execution checks. No SQL text. |
| Plans | Investigations could correlate plan hashes only when a Finding already carried them. | No direct historical plan observation or bounded plan-step evidence. | Per-SQL_ID plan-hash history, bounded `V$SQL_PLAN`/`GV$SQL_PLAN` shape details without predicates, and non-causal wording. |
| Statistics | Existing Post-CRQ checks report statistics in recent object-change context. | No join to SQL workload or historical diagnostic samples. | Bounded stale-stat observations only for table objects referenced by sampled SQL plans. |
| Tablespaces | Deep Scan includes segments/owner size; no per-audit operational usage lifecycle. | No free/allocated/autoextend capacity baseline or warning/critical thresholds. | Bounded permanent/undo and temporary-space rules, datafile/tempfile limits, configured thresholds and lifecycle Findings. |
| Segments | Deep Scan includes size summaries and segments. | No comparable top-segment growth snapshots tied to the durable diagnostic pipeline. | Bounded top-200 segment samples only for workload-related objects, persistent snapshots, and findings only after comparable growth thresholds. |
| RAC/CDB | E13DB-012 probes `GV$INSTANCE` and `V$CONTAINERS`, but does not preserve/query diagnostic scope. | Cluster or PDB visibility could be mistaken for whole-target visibility. | Capability snapshot records RAC instance count, active CON_ID and CDB mode; GV$ views are required for multi-instance scope and diagnostics bind the active CON_ID. Unknown CDB scope is skipped/degraded. |

## Implemented flow

`AutomationService.execute_job` and the manual diagnostics endpoint call the same diagnostic runner and E13DB-012 `AuditEvidenceService`. RuleResults, allow-listed finding envelopes, diagnostic observations and capability state are committed before the common Finding/Red Flag/Alert reconciliation. Replays use stable scheduled or caller-provided AuditRun IDs.

Observations are appended in `oracle_diagnostic_observations`, bounded to 500 rows per AuditRun and allow-listed fields. They contain numeric counters, identity, timestamps and redacted metadata, never SQL text/predicates/binds. Findings remain the incident/lifecycle engine; the observation table supplies historical comparison inputs and does not create a second issue engine.

## Fixture-backed scenarios

`tests/test_oracle_diagnostics.py` has deterministic Oracle-shaped fixtures covering session/lock chains across instances and containers, comparable SQL counters, plan-hash changes, related stale statistics, segment growth, capacity lifecycle, capability loss, read-only/query limits, AWR/ASH non-query behavior, AuditRun replay, Investigation facts and the real `AutomationService.execute_job` path.

The scheduler acceptance calls the actual `AutomationService.tick()` entry point (not the manual endpoint), waits for the scheduled worker's durable AuditRun/Findings, then replays the same scheduled reference to verify the run does not duplicate occurrences.

The Playwright real-backend smoke seeds a clearly identified fixture AuditRun in isolated SQLite files and follows it through the actual API/browser to Finding and Investigation views. It verifies product navigation and persistence; it is not an Oracle connection test or a scheduled SQL execution test.

## Certification boundary

No safe test Oracle endpoint or credentials were supplied/discovered for this implementation. Oracle syntax, actual grants, licensed feature use and RAC/CDB server behavior remain `REAL_ORACLE_NOT_VERIFIED`; fixture results do not certify a live Oracle server.

## Final verification (current candidate)

- Backend: `367 passed, 0 failed` (includes existing E13DB-001–012 regressions).
- Frontend: `96 passed, 0 failed`; `npm run lint`: PASS; `npm run build`: PASS (Vite emits the existing >500 kB chunk warning).
- Browser: `npm run smoke:ui:real` PASS against the real served SPA/Uvicorn/API and isolated SQLite stores. It navigates Diagnostics → Finding → Investigation from an explicitly seeded fixture AuditRun. No Oracle query is executed by this browser smoke.
- Query shape/volume: fixture runner enforces SELECT-only statements; at most 8 diagnostic data queries/run and 500 allow-listed persisted observations. Capability probes are separately counted and timed on the AuditRun.
- Synthetic single-target timing sample (fixture only): runner 0.018 s, 24 capability probes, 7/8 data queries, reconciliation 0.630 s, Fleet projection 0.010 s and Needs Attention 0.002 s. Oracle fixture replies are immediate, so query latency is not representative; these are not production or Oracle SLOs.
- `npm audit --audit-level=low`: FAIL, 9 transitive advisories (2 low, 2 moderate, 5 high). Non-forced `npm audit fix` was applied; remaining automated fixes require major Tailwind 4 / Mermaid 10 changes and were not forced into this diagnostics milestone.
- Read-only SQL/security fixtures, privilege-loss false-resolution prevention, AWR/ASH gate, scheduler replay, crash recovery and referenced-evidence retention: PASS.

Implementation is fixture-complete. Overall release certification remains **PARTIAL** until a safe non-production Oracle target is exercised and dependency advisories are remediated or accepted through the repository's dependency-upgrade process.
