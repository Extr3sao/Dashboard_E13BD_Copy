# E13DB product and architecture review — milestones 001–011

**Review branch base:** `feature/e13db-011-dba-intelligence` at
`58fc4de4634cef51110147b1f00d9508ccf977f1`.

## Executive assessment

E13DB is a useful Oracle audit and operator-response application, with durable
Findings, fleet views, alerts, CPD operations and an explainable investigation
surface. It is not yet one end-to-end durable audit product for every execution
path: the manual Post-CRQ route reconciles Findings and alerts, but the scheduled
automation path stores its own run facts without calling that reconciliation
service. The schedule can therefore complete while the Findings/Fleet/Alert/
Investigation view has not observed that scheduled result. This is the highest
priority product defect and is directly visible in the two execution paths.

The 011 investigation model is deliberately deterministic. It can explain
temporal/object/schema/rule relationships among already stored observations; it
does not acquire live Oracle performance data. AWR/ASH remain skipped unless
license and privilege flags are set, and even then this release reports the gate
but does not issue AWR/ASH queries. The next milestone should first bind every
audit result to a durable, versioned evidence/capability snapshot and feed all
audit execution paths through one reconciliation contract. Oracle deep
diagnostics should follow that authority foundation. Multi-database support is
not the next step.

## DEV Agent source actually inspected

* Latest certified source authority inspected: DEV Agent 4.7.1, canonical Git
  source SHA `ae7d5dfff9e5e8beb9386ec305663aa515b6f569`, release flip commit
  `1a06aaa92f87a0cee7152d1ac58c912de6192f46`, release
  `REL-4.7.1-4478A6813F8D` (`OPERATIONALLY_CERTIFIED_WITH_GOVERNANCE_EXCEPTION`).
* Evidence inspected in `C:\dev\devagent-fw-468-entrypoint\reports\v4.7.1`:
  `RELEASE_IDENTITY_4_7_1.json`, `DEV_AGENT_4_7_1_REPORT.json`,
  `FULL_REGRESSION.json` (2,914 passed / 0 failed / 11 skipped),
  `ADVERSARIAL_VERIFICATION_471.json`, `TRACEABILITY_471.json`,
  `FRESH_CLONE.json`, `CI_SHA_BINDING.json` and E2E/provider receipts.
* The directory name/branch label is `release/4.6.8-canonical-entrypoint`; the
  certified product content in its immutable lineage is 4.7.1. The working
  checkout has later 4.7.2 work and unrelated dirty/untracked artifacts. It was
  inspected read-only and not modified.
* Latest candidate inspected: DEV Agent 4.7.2, worktree head
  `ee8a9a3749253ecb4835b6efd235987627ff1124`; its identity artifact binds
  canonical candidate SHA `eb25237a8e77592574f56a1705f10a94c3c9d70d`, fingerprint
  `9b758f933a5f1ea52e0f7f7108d8ae2607b7d0b0d5c0be47680635205ec61d89`, and says
  `SEALED_NOT_CERTIFIED`. Its available full-regression JSON identifies a
  4.7.1 mandate/head (`6bbd927...`), not a full regression of this 4.7.2 sealed
  identity. I inspected its source patterns, but do not treat 4.7.2 as certified
  evidence. The checkout was dirty and advancing during review; it was not
  modified.

## Product map and current flow

| Domain | Implementation and interface | Durable source / verification |
|---|---|---|
| Authentication/configuration | `src/api/security.py`, `main.py`; cookie USER sessions, CSRF, environment-backed `SecretProvider` | `tests/test_security.py`, `tests/test_main_runtime.py` |
| Oracle target profiles | `src/core/config_loader.py`, `src/core/db_manager.py`, connection profile text/env; Finding target metadata in `target_contexts` | No common first-class `DatabaseTarget` aggregate; profile name is commonly the target key |
| Scheduler / scheduled audits | `src/api/automation_service.py`, `/api/automation/*`; durable job/run/retry storage | `src/core/automation_store.py`: `scheduled_jobs`, `job_runs`, retry queue, `audit_*_facts` |
| Manual Post-CRQ audit | `src/api/main.py` → `run_post_crq_audit` → `FindingStore.reconcile_post_crq` → `AlertingService.evaluate` | `audit_runs`, `findings`, `finding_occurrences`, `red_flags`, alerts; `tests/test_finding_engine.py`, `test_alerting_engine.py` |
| Rule definitions/results | Legacy Markdown/YAML plus `audit_checks` / `consulta_versions`; `check_engine.RuleDefinition/RuleResult` and `post_crq_rule_adapter.py` | Adapter normalizes data, but the manual execution route still uses legacy report dictionaries; adapter is not the sole execution/result authority |
| Findings / history | `src/api/finding_engine.py`, `/api/findings/*` | `findings`, `finding_occurrences`, `finding_actions`, `finding_reconciliation_receipts` |
| Red Flags / fleet / trends | `FindingStore` and `/api/operations/fleet`, `/trends`, `/audits`; `FleetDashboardView` | Derived from current Findings, Red Flags, target metadata and `audit_runs` |
| Alerts / notifications / reports | `src/api/alerting_engine.py`, `alerting_router.py`, `AlertingReportsView` | `alert_events`, `alert_deliveries`, `operational_reports`, period uniqueness |
| E13DB Operations | `src/api/cpd_operations.py`, `cpd_router.py`, Operations view | Operations event/lease/backup metadata; two independent SQLite stores; online SQLite backup + offline restore preparation |
| DBA investigations | `src/api/investigation_engine.py`, `investigations_router.py`, Investigations view | `investigations`, normalized evidence, correlations, hypotheses, checks, plan observations and operator cause/resolution |
| Report generation | `report_builder.py`, `alerting_engine.py`, automation report pipeline | Persisted operational report periods and automation artifacts; delivery is a separate external side effect |

### Reconstructed product flow

```text
profile configuration ──→ manual or scheduled audit executor
manual Post-CRQ → legacy RuleResult dictionaries → FindingStore reconciliation
                                     ↓                    ↓
                               audit response       occurrences / Findings
                                                        ↓
                                              Red Flags → alerts/reports
                                                        ↓
                                                investigations

scheduled AutomationService → job_runs + audit_execution/lots/schemas/check facts
                              └── does not currently call FindingStore reconciliation
```

The explicit split above is the principal source-of-truth divergence. The
CPD recovery browser fixture replaces the scheduled audit function and calls
`finding_store.reconcile` itself (`scripts/cpd_fixture_server.py`); that proves
recovery/UI behavior, but is not evidence that the production scheduled audit
path performs this reconciliation. This is an important scope limitation in the
E13DB-010 acceptance fixture.

### Interface, persistence, verification and documentation inventory

| Surface | Current inventory |
|---|---|
| API route families | Legacy `/api/audit/*`, `/api/automation/*`, `/api/queries/*`, `/api/db/*`; USER routes `/api/findings/*`, `/api/operations/*`, `/api/alerting/*`, `/api/investigations/*`; health `/health[z]`, `/ready[z]`; SPA routes served by `main.py` |
| Browser views | `DatabaseAuditWorkspace`, `FleetDashboardView`, `FindingsView`, `AlertingReportsView`, `OperationsView`, `InvestigationsView`, `AutomationView`, `MailConfigView`, `PostCrqAuditView`, `DeepScanView` |
| Internal SQLite tables | Legacy query/check/explanation tables; `findings`, `finding_occurrences`, `finding_actions`, `target_contexts`, `red_flags`, `audit_runs`, `finding_reconciliation_receipts`; `alert_events`, `alert_deliveries`, `maintenance_windows`, `operational_reports`; operations lease/events/backups; investigation cases/events/evidence/correlations/hypotheses/checks/plan observations/relationships |
| Automation SQLite tables | `scheduled_jobs`, `job_runs`, `delivery_targets`, `severity_rules`, `internal_tasks`, retry queue/attempts/config/templates/routes; scheduled audit fact tables `audit_execution_facts`, `audit_lot_facts`, `audit_schema_facts`, `audit_check_facts` |
| Backend tests | `test_main_runtime`, `test_security`, `test_check_engine`, `test_execution_reliability`, `test_automation`, `test_finding_engine`, `test_findings_router`, `test_operational_dashboard`, `test_alerting_engine`, `test_alerting_router`, `test_cpd_operations`, `test_investigation_engine` |
| Frontend tests | `App.smoke`, `DatabaseAuditWorkspace`, `FindingsView`, `InvestigationsView`, `FleetDashboard`, `AlertingReports`, `OperationsView`, automation/help/auth navigation tests |
| Runbooks/specification | `docs/CPD_OPERATIONS_RUNBOOK.md`, `docs/DBA_INVESTIGATION_ENGINE.md`, `docs/E13DB_010_IMPLEMENTATION_PLAN.md`, `docs/E13DB_011_IMPLEMENTATION_PLAN.md` |

The store constructors create/migrate domain tables independently. There is no
central versioned migration manifest covering both databases; CPD backup schema
compatibility is currently an operations schema constant/signature.

## Data authority and lineage

| Data | Authority class | Notes |
|---|---|---|
| Profile credentials/DSN | AUTHORITATIVE configuration/secret source | Secrets are outside Findings; delivery DB startup clears legacy SMTP password/webhook columns |
| Scheduled job definition | AUTHORITATIVE `scheduled_jobs` | Definitions and run facts are in the automation DB |
| Completed job state | HISTORICAL `job_runs` | Lowercase legacy job statuses; separate from Finding `audit_runs` |
| Manual audit result | HISTORICAL response plus Finding projection | Full normalized `RuleResult` list is not uniformly stored as a canonical standalone result set |
| Finding current lifecycle | AUTHORITATIVE `findings` | History in append-oriented occurrences; manual decisions in `finding_actions` |
| Red Flags, Fleet Health, Trends | DERIVED | Recomputed from stored Findings/audits/target metadata |
| Alerts and reports | DERIVED, then HISTORICAL | Alert event and report period are durable; SMTP acceptance cannot be transactionally coupled to SQLite |
| Investigation facts | DERIVED projection of stored occurrences/audit runs | Allow-listed and redacted; retained evidence links to local finding/occurrence IDs, not a versioned rule/capability authority |
| Hypothesis status | DERIVED until operator disposition | `updated_by` preserves an operator’s disposition against automated refresh |
| Confirmed cause/resolution | AUTHORITATIVE operator assertion | Actor/time and resolution are stored separately from hypotheses |
| Backup checksum | VERIFICATION metadata | Online backup files are individually SQLite-consistent; the two database files are not a cross-store atomic snapshot |

Important lineage currently present: rule id, Finding id, audit run ID,
occurrence ID, investigation evidence ID, report/alert references. Important
lineage currently absent or inconsistent: immutable RuleDefinition version/hash
on every execution; a common AuditRun identity across manual and scheduled
paths; capability/privilege/license snapshot on AuditRun; producer/runtime SHA
on evidence; one canonical RuleResult store. `RuleResult` does carry engine and
version in the library contract, but the report adapter and persisted facts do
not consistently preserve a complete per-run snapshot.

## State machines and invariants

| Aggregate | Observed states / transitions | Review finding |
|---|---|---|
| ExecutionReliability `AuditExecution` | PENDING → RUNNING → SUCCESS / FAILED / INTERRUPTED | In-memory generic runner; not the sole durable scheduled audit model |
| Automation `job_runs` | `running`, `success`, `partial_error`, `error`, `interrupted` | String states and writers span multiple service branches; completion is guarded against overwriting interrupted state |
| Finding audit run | SUCCESS or caller-provided failure state; coverage FULL/PARTIAL/DEGRADED/UNKNOWN | Separate from automation `job_runs`; manual Post-CRQ derives this record |
| Finding | OPEN/ACKNOWLEDGED/ACCEPTED_RISK/FALSE_POSITIVE/RESOLVED; delta is a separate evolution label | SQL updates do not declare one centralized transition table; manual lifecycle records are retained |
| Red Flag | OPEN/RESOLVED | Reconciliation refreshes active projections; run-health flags have a separate key path |
| Alert | OPEN/SUPPRESSED/ACKNOWLEDGED/CLOSED/RECOVERED | Cooldown/priority logic is code-based; external delivery receipt can be ambiguous after crash |
| Investigation | OPEN/MONITORING/RESOLVED/CLOSED | Automatic resolution follows primary Finding resolution; operator cause stays separate |
| Report | GENERATED plus a separate `delivery_status` | Unique report-type/calendar-period key is idempotent for creation; send acceptance can be ambiguous |
| Backup | SUCCESS/FAILED/EXPIRED | Metadata/version/integrity are represented; atomicity is per database file |

The explicit false-success control is sound in Findings health: `0 Findings`
does not imply HEALTHY if no audit exists, the latest audit failed/is stale, or
coverage is incomplete. The remaining risk is that not every audit path writes
to the same health/evidence source.

## Architecture, storage, API and UX findings

* The API composition root `src/api/main.py` remains roughly 2.8k lines and owns
  route handlers, profile setup, and wiring; `AutomationService` and
  `AutomationStore` are also large multi-responsibility modules. This is real
  brownfield coupling, but a broad extraction now would have no measurable
  user benefit relative to the risk.
* There are two SQLite databases plus filesystem reports/backups. Foreign keys
  and transactions work within each DB, not across stores. Audit job rows,
  rule facts, Findings and report artifacts can therefore represent different
  transaction cut points. CPD backup documentation correctly disclaims a
  cross-store atomic snapshot.
* Migrations are idempotent `CREATE TABLE` / `_ensure_column` code distributed
  among store constructors, rather than one ordered migration ledger. Backup
  schema compatibility currently uses a manual schema version/signature.
* API responsibilities are split between a large `main.py` and smaller routers
  (`findings_router`, `alerting_router`, `cpd_router`, `investigations_router`).
  Auth is globally USER+CSRF for `/api` when production `E13DB_AUTH_REQUIRED`
  remains true, with router dependencies on new surfaces. Legacy test mode can
  set auth false; deployment configuration must not do so.
* Findings list/detail and investigation use expose evidence to a USER operator;
  investigation evidence is allow-listed/redacted. The pre-existing Finding
  detail view still displays a JSON evidence block, so the investigation view is
  more usable than the older detail pane but has not removed that legacy UX.
* The real browser E2E exercised Dashboard/Fleet, Finding detail, Investigation,
  Alerts & Reports and Operations using the CPD fixture app. This is true
  application/browser evidence but synthetic Oracle/SMTP adapters; no production
  Oracle system was available or queried.

## Principal conclusions

1. **One audit-result authority is missing across execution paths.** Schedule
   success and Finding/Fleet success can diverge. Prioritize this before more
   rules or database engines.
2. **External side effects remain at-least-once/ambiguous.** `AlertingService`
   calls SMTP before the surrounding SQLite transaction commits its delivery
   row. A crash after SMTP accepts but before commit can cause a duplicate on
   later evaluation/retry. No honest exactly-once guarantee exists without
   channel idempotency or an operator-visible UNKNOWN/RECONCILE state.
3. **Evidence is useful but not yet reproducible enough for historical DBA
   decisions.** Findings retain observations, but rule implementation version,
   effective capabilities/privileges, and runtime identity are not consistently
   bound to them. Precise invalidation/replay is not possible for every case.
4. **The architecture is Oracle-first, not yet multi-engine-ready.** Profiles,
   direct `OracleDBManager` creation and Post-CRQ SQL/window rules are spread
   through main/service code. The `check_engine` contracts show a possible
   adapter boundary but are not the sole production executor.
5. **No P0 was substantiated by this review.** P1s below are material workflow,
   duplicate-side-effect and evidence-authority risks; they do not imply known
   data corruption in the certified test fixture.

## Review implementation and validation receipt

Two low-risk query-batching improvements were implemented in
`src/api/finding_engine.py`: Fleet status uses batched context/latest-audit/
finding/Red Flag reads rather than calling `health()` once per target; the
Investigation list now batch-loads primary Findings, top hypotheses, pending
checks and latest correlations rather than opening several queries per row.
On the same synthetic local dataset, observed Fleet wall time moved from about
3.4 s to 1.5–1.7 s for 100 targets, and Investigation list from about 3.0 s to
0.01–0.02 s for a 100-row page with 500 stored cases. These are relative
single-host SQLite measurements, not production SLOs.

Evidence and validation on the review branch:

* Base: `58fc4de4634cef51110147b1f00d9508ccf977f1` (E13DB-011).
* Current backend full regression after the query change: **335 passed / 0
  failed** (`scripts/run_backend_regression_full.py`).
* Frontend full suite: **91 passed / 0 failed**. Under concurrent external host
  load one parallel run hit five 15-second test timeouts; the same full suite
  then passed serially with bounded test/hook timeout after diagnosis. No code
  changes were made to work around those timeouts.
* `npm run lint`, `npm run build`, `npm audit --audit-level=low`, and
  `git diff --check`: PASS; audit reported zero vulnerabilities.
* Browser/API walkthrough used the real served SPA, Uvicorn, USER session,
  temporary SQLite, and controlled CPD fixtures. It traversed Operations,
  Fleet Dashboard/database detail, Problems/Finding detail, Investigations and
  Alerts & Reports. Evidence screenshots are in the local run directory
  `C:\Users\GVLLFR0035\AppData\Local\Temp\opencode\e13db-cpd-smoke-1790895412113`.
* Scale harness and result: `scripts/review_e13db_scale.py` and
  `reports/product-audit/E13DB_SCALE_SIMULATION_001.json`. Synthetic only:
  100 targets, 365 days, 73,000 audit runs, 292,000 rule facts, 5,000 Findings,
  2,000 Alerts and 500 Investigations. It contains no real target credentials,
  SQL text or production rows.

The source baseline passed through E13DB-011 before review; this review did not
rewrite or alter `main`.

## Subsequent milestone implementation — E13DB-012/013

This review is historical and describes the 001–011 baseline. E13DB-012 was
subsequently delivered at `7be7f228b8404a2e910c01e311ca7c07502bac4a` with a
durable AuditRun/RuleResult and reconciliation contract. E13DB-013 is implemented
on `feature/e13db-013-oracle-deep-diagnostics` from that SHA.

The 013 diagnostic boundary is `src/api/oracle_diagnostics.py`: a bounded,
read-only Oracle rule pack produces normalized RuleResults, redacted diagnostic
observations and object/session Finding envelopes. `AuditEvidenceService` stores
those observations alongside each AuditRun and sends the same data through the
existing FindingStore, RedFlag, Alert and Investigation projections. There is no
second incident store. Oracle visibility is scoped to the effective current
instance/container; RAC-dependent rules require matching GV$ capability.

The new operator route is the Database Audit **Diagnòstics Oracle** tab. Manual
runs and scheduled `oracle_diagnostics` jobs use the same runner. Fixtures test
blocking, plan changes, privilege loss, capacity lifecycle, retention and
replay. The Playwright real-backend smoke uses isolated SQLite plus a seeded
diagnostic fixture; it validates browser-to-API-to-persisted-evidence navigation,
not a live Oracle connection. Oracle server syntax, grants, license attestations
and real RAC/CDB behavior remain `REAL_ORACLE_NOT_VERIFIED` until tested against
a non-production Oracle target.
