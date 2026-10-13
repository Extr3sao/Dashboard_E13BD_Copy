# E13DB Oracle deep diagnostics

E13DB-013 adds an Oracle-first, read-only diagnostic job and Database Audit workspace. Manual execution and `oracle_diagnostics` scheduled jobs share E13DB-012 `AuditRun`/`RuleResult`, capability snapshot, diagnostic-observation persistence and Finding reconciliation.

## Operator workflow

1. Open **Database Audit → Diagnòstics Oracle**, select the Oracle profile and run a diagnostic, or configure an `oracle_diagnostics` automation job.
2. Review the effective AuditRun coverage and per-view capability state before interpreting an empty result.
3. Inspect timestamped session/lock, SQL, plan, statistics, segment and capacity observations. SQL text, predicates and bind values are not shown or stored.
4. Follow a diagnostic Finding to **Problemes** and open its Investigation to see Facts, correlations, hypotheses and recommended DBA checks.

The UI displays the latest diagnostic history plus the selected run's capability and RuleResult details. If there are no diagnostic observations, it still displays the latest run's skipped/error rules and capabilities when an AuditRun exists.

## Diagnostic coverage and query budget

Each Oracle call has a bounded `CALL_TIMEOUT_MS` (default 3 seconds for diagnostic data queries, lower than an existing connection timeout); capability probes are read-only and individually limited to 2 seconds. A diagnostic run has a hard bound of 80 session rows, 80 lock edges/50 roots, 60 SQL aggregates, 100 plan steps, 50 SQL_ID/object bind identities per secondary probe, 50 workload segments, 100 permanent/undo tablespaces, 50 temporary tablespaces, 500 persisted diagnostic observations per AuditRun, and at most 8 data queries. The optional plan-step query runs only when a plan-hash change candidate exists and plan visibility is available. The AuditRun reports capability-probe count/duration separately from its diagnostic data-query budget.

The current query families are:

| Diagnostic | Oracle views | Observed information |
|---|---|---|
| Sessions | `V$SESSION` / `GV$SESSION`, optionally `V$TRANSACTION` / `GV$TRANSACTION` | User session status, active-call versus inactive-idle age, SQL_ID, wait class/event, module, blocker identifiers and visible open-transaction markers. Repeated SQL_ID/call-age observations describe change without asserting that a call is progressing. |
| Blocking | `V$LOCK` / `GV$LOCK` joined to bounded session edges | Root blocker, explicit lock-confirmed edges, instance/container/SID/SERIAL identities, chain depth, affected sessions and wait time. Findings arise only from observed lock/session relationships. |
| SQL workload | `V$SQLSTATS` / `GV$SQLSTATS`, fallback `V$SQL` / `GV$SQL` when the corresponding capability probe allows it | SQL_ID, executions, elapsed/CPU counters, buffer gets, disk reads, rows, parse calls, latest activity and plan hash. SQL aggregates are ordered by elapsed consumption and windowed to recent activity. |
| Plan changes/details | `V$SQL_PLAN` / `GV$SQL_PLAN` for plan-change candidates | First/last snapshot and plan hash; bounded operation/object/cardinality/cost rows omit predicates and SQL text. A hash change is a FACT, not a degradation or cause by itself. |
| Statistics | `DBA_TAB_STATISTICS` joined to sampled SQL plan objects | Last analyzed, stale flag, estimated rows, blocks and sample size for workload-related table/partition objects only. |
| Segment growth | `DBA_SEGMENTS` restricted to those workload-related objects | Bounded size snapshots; Findings require comparable snapshots and configured byte/percent growth thresholds. No capacity forecast is calculated. |
| Storage capacity | `DBA_TABLESPACES`, `DBA_DATA_FILES`, `DBA_FREE_SPACE`, `DBA_TEMP_FREE_SPACE`, `DBA_TEMP_FILES` | Permanent/undo and temporary used/free bytes, autoextend headroom and configurable warning/critical percent thresholds. No file is resized. |

Rules are isolated: one missing view or failed query does not stop unrelated probes. `SKIPPED`, `ERROR`, `UNKNOWN`, `UNAVAILABLE`, `INSUFFICIENT_PRIVILEGES` and `UNSUPPORTED_VERSION` remain visible. These states do not resolve existing Findings. Historical SQL comparisons require executions and monotonic cumulative counters; they compare a new-interval average only with a prior comparable interval. Counter resets/no new executions are explicitly marked incomparable.

RAC uses GV$ queries only when both the instance and corresponding GV$ metadata are visible; otherwise cluster-scoped rules are skipped rather than reporting a single instance as the cluster. CDB/PDB views are filtered to the connection's active `CON_ID`; the UI labels root versus PDB scope. When the active container cannot be determined, container-scoped diagnostics are skipped. A CDB-root connection does not imply that all PDBs were inspected.

## Evidence lifecycle

`oracle_diagnostic_observations` stores capped, allow-listed observations linked to an AuditRun. Findings are created only for operationally relevant blockers, high/comparably regressed SQL, observed plan changes, stale statistics on sampled SQL objects, threshold-crossing tablespaces, and comparable segment growth. They use the existing Finding fingerprints and lifecycle; Red Flags, Alerts, Fleet Health and Investigations are the existing E13DB-012/011 projections.

Investigation categories remain deterministic Facts. Blocking and workload/plan/statistics/capacity relationships may generate an explicitly labelled Hypothesis and a recommended check. They are correlations for DBA review and never operator-confirmed root causes. Active Finding and Investigation references protect diagnostic observations from bounded retention cleanup.

## Failure and licensing behavior

View access is tested with zero-row SELECT probes. `ORA-01031` is a permission failure; ambiguous missing/unsupported objects remain `UNKNOWN` unless the server version gives a reliable unsupported-version distinction. Connection configuration and network reachability are reported separately from per-view access.

`AWR_ALLOWED`/`ASH_ALLOWED` are `AVAILABLE` only with explicit `E13DB_ORACLE_AWR_LICENSED` + `E13DB_ORACLE_AWR_PRIVILEGE`, or the corresponding ASH settings. This is an explicit deployment attestation, not a license inferred from view access. The diagnostic runner contains no AWR/ASH data query or probe; workload/plan data uses the bounded `V$SQL*`/`GV$SQL*` views instead.

## Verification boundary

Fixtures exercise production runner SQL selection, normalized RuleResults, reconciliation, Findings/Investigations and browser navigation against the real API and isolated SQLite store. They do not certify Oracle view syntax, grants, version differences, licensed features, or actual RAC/CDB behavior. Until a safe Oracle test target is run, report `REAL_ORACLE_NOT_VERIFIED`.
