# Oracle monitoring privileges for E13DB

## Scope and safe account

Use a dedicated, non-`SYS`/non-`SYSTEM` monitoring account. E13DB diagnostics execute only bounded `SELECT` statements and do not create an Oracle job, gather statistics, alter objects, resize files, kill sessions or invoke remediation packages. The grant examples below are DBA deployment guidance; the application never executes them.

Prefer direct object grants to a narrowly scoped role used by the E13DB connection. Avoid `SELECT ANY DICTIONARY` when individual view grants meet the target's policy. A view capability is reported only after the read-only probe for that view succeeds; a missing grant never becomes a PASS.

## View-to-rule mapping

| Capability / purpose | Minimum Oracle objects used |
|---|---|
| Base context and CDB | `SYS.V_$DATABASE`, `SYS.V_$CONTAINERS`; `SYS_CONTEXT('USERENV', ...)` needs no grant |
| Single-instance sessions | `SYS.V_$SESSION`; optional open transaction: `SYS.V_$TRANSACTION` |
| RAC session scope | `SYS.GV_$INSTANCE`, `SYS.GV_$SESSION`; optional transaction: `SYS.GV_$TRANSACTION` |
| Lock-chain confirmation | `SYS.V_$LOCK` or `SYS.GV_$LOCK`, in addition to the session view |
| SQL workload | `SYS.V_$SQLSTATS` or `SYS.GV_$SQLSTATS`; fallback `SYS.V_$SQL` / `SYS.GV_$SQL` only when the corresponding capability is visible |
| Execution plan shapes | `SYS.V_$SQL_PLAN` or `SYS.GV_$SQL_PLAN` |
| Workload-related table statistics | `SYS.DBA_TAB_STATISTICS` |
| Workload-related segment size | `SYS.DBA_SEGMENTS` |
| Permanent/undo capacity | `SYS.DBA_TABLESPACES`, `SYS.DBA_DATA_FILES`, `SYS.DBA_FREE_SPACE` |
| Temporary capacity and limits | `SYS.DBA_TEMP_FREE_SPACE`, `SYS.DBA_TEMP_FILES` |
| Grant discovery | `SESSION_PRIVS` is queried only for declared required system privileges; per-view zero-row probes determine actual object visibility |

Example DBA-reviewed direct view grants (adapt to the version and selected single-instance/RAC scope):

```sql
GRANT SELECT ON SYS.V_$SESSION TO E13DB_MONITOR;
GRANT SELECT ON SYS.V_$LOCK TO E13DB_MONITOR;
GRANT SELECT ON SYS.V_$SQLSTATS TO E13DB_MONITOR;
GRANT SELECT ON SYS.V_$SQL_PLAN TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_TAB_STATISTICS TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_SEGMENTS TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_TABLESPACES TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_DATA_FILES TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_FREE_SPACE TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_TEMP_FREE_SPACE TO E13DB_MONITOR;
GRANT SELECT ON SYS.DBA_TEMP_FILES TO E13DB_MONITOR;
```

For RAC, grant the matching `SYS.GV_$...` views as well as `SYS.GV_$INSTANCE`. RAC rules use GV$ only when the cluster-wide probes succeed and the observed instance count establishes the scope. If cluster-wide views are not available, E13DB marks the RAC scope limited and skips affected rules rather than treating one instance as the whole cluster.

## CDB/PDB scope

E13DB records the effective container ID of the connected session and includes it in session, SQL, plan and object identities. Queries against GV$ data in a CDB are constrained to that active `CON_ID`; dictionary and capacity views are read in the connected container. A connection to `CDB$ROOT` is therefore root-scoped, not proof that all PDBs were inspected. If the active container cannot be identified, container-sensitive rules are skipped and coverage is degraded.

`V$CONTAINERS` is a 12c+ capability. On older versions the snapshot reports `UNSUPPORTED_VERSION`; non-CDB targets explicitly report that container identity is not applicable.

## AWR/ASH licensing gate

E13DB does not probe or query AWR/ASH views. Their statuses are deployment attestations, not inferred from view access:

- `E13DB_ORACLE_AWR_LICENSED=true` and `E13DB_ORACLE_AWR_PRIVILEGE=true`
- `E13DB_ORACLE_ASH_LICENSED=true` and `E13DB_ORACLE_ASH_PRIVILEGE=true`

Without both explicit settings for a feature, its capability is `NOT_LICENSED` or `INSUFFICIENT_PRIVILEGES`; a rule requiring it is skipped. These settings require an operator/DBA to confirm the applicable licensing and access policy. They do not turn on AWR/ASH queries in the current diagnostic pack.

## Resource/coverage limits

- Capability probes select zero rows and restore the connection's prior call timeout.
- Diagnostic data queries use a bounded timeout, a maximum of 200 rows per ordinary view, 80 lock edges, 200 plan steps and a per-AuditRun observation cap.
- SQL plan rows omit predicates and SQL text. No SQL text or bind values are retained.
- SQL statistics are cumulative SGA counters; a comparison requires increased executions and monotonic counters. A reset/no-new-execution sample is marked incomparable.
- Statistics sampling is limited to table objects referenced by sampled SQL plans; segment sampling is limited to those workload-related objects.
- TEMP capacity uses `DBA_TEMP_FREE_SPACE` and `DBA_TEMP_FILES`; no tempfile modification is made.
- Query failures are isolated. `ORA-01031` maps to `INSUFFICIENT_PRIVILEGES`; ambiguous object/version errors remain `UNKNOWN` unless a version check is definitive.

Verify the exact grants against a non-production target before enabling scheduled diagnostics. E13DB-013 fixtures validate query selection and evidence semantics but do not certify the grants or syntax on a live Oracle installation (`REAL_ORACLE_NOT_VERIFIED` until such a test is performed).
