# DBA Investigation Intelligence

## Scope and language contract

The Investigation Center is a deterministic Oracle-first projection over stored,
redacted E13DB Findings, Finding occurrences, audit runs and target metadata. It
does not use an LLM, ML, arbitrary SQL, probabilities, bind values or claims of
root cause. Its labels have fixed meanings:

* **FACT** — an observation already stored in a Finding occurrence/audit record,
  normalized for display. Plan-hash changes are facts about identifiers observed;
  they do not imply a plan regression.
* **CORRELATION** — same-target evidence within the investigation window, related
  by object/schema/SQL identifier/tablespace/time/category or a documented rule
  relationship. The explanation names the matching signals. Strength is a
  deterministic label, not probability: DIRECT = same schema and object; STRONG =
  same SQL identifier or schema; RELATED = same tablespace/documented rule edge;
  WEAK = temporal proximity only.
* **HYPOTHESIS** — an explicit rule-based possibility. Its description states
  that correlation is not causal proof. Supporting and contradicting evidence
  links are persisted separately. Automated refresh never overwrites an
  operator’s disposition.
* **RECOMMENDED CHECK** — non-destructive operator guidance. E13DB does not
  execute free-form investigative SQL or destructive remediation from a case.

The change window starts around the primary Finding’s first observation and is
extended as its last observation advances. Correlation searches constrain by
database and time window and cap candidates to 100 Findings and 1,000 occurrence
rows per refresh. Timeline/evidence are separately capped at 500 normalized rows.
SQLite indexes cover target/time, investigation/time and target/object/time.

## Evidence normalization and privacy

Categories are assigned by a fixed category/rule-summary vocabulary:
`CAPACITY`, `LOCKING`, `PERFORMANCE`, `EXECUTION_PLAN`, `STATISTICS`,
`OBJECT_HEALTH`, `CONNECTIVITY`, `AUDIT_COVERAGE`, `WORKLOAD`, `CONFIGURATION`,
`AVAILABILITY`. New categories may be added in `investigation_engine.py` without
changing the investigation API contract.

Only allow-listed scalar metric and metadata keys are retained (for example,
elapsed seconds, execution count, plan hash, SQL ID, tablespace, object identity,
blocking/blocked session IDs, statistics age/state and threshold). Raw SQL text,
bind values, password/token fields and unrestricted evidence payloads are never
copied to the investigation projection. Existing evidence redaction is applied to
summaries and operator-entered cause/resolution text. Investigation detail returns
a sanitized primary-Finding summary rather than raw Finding JSON.

## Automatic and manual case lifecycle

Automatic opening is enabled by default and can be disabled with
`E13DB_INVESTIGATIONS_AUTO_OPEN=false`. It opens for P1 Findings/Red Flags,
critical WORSENING or REOPENED Findings, and repeated database-level audit or
connectivity failure Red Flags. Minor WARNs do not create cases. One open case per
primary Finding is enforced with a SQLite partial unique index. Manual cases can
be opened by a USER from Finding detail or the authenticated API; actor, source
and timestamp are recorded.

Statuses are `OPEN`, `MONITORING`, `RESOLVED`, `CLOSED`. Successful audit evidence
that resolves the primary Finding automatically resolves an open case. A manual
cause record is explicitly labelled operator-confirmed and records actor/time and
selected evidence references. Resolution records actor, timestamp, resolution
and actions taken. A later matching Finding creates a new case and presents prior
confirmed causes/resolutions as historical context only; old remediation is
never applied automatically.

## Correlation relationships

Rules are deterministic and explainable. Same database is mandatory; temporal
proximity alone is WEAK. Same schema and object is DIRECT. Same schema or SQL ID is
STRONG. Same tablespace or a declared category/rule edge is RELATED. Other
time-window matches are WEAK and explicitly say no object/rule relationship was
established. Default conceptual edges include:

| Source category | Related category | Interpretation |
| --- | --- | --- |
| LOCKING | PERFORMANCE / LONG_RUNNING_SQL | possible temporal association |
| STATISTICS | EXECUTION_PLAN / PERFORMANCE | investigate optimizer/statistics context |
| EXECUTION_PLAN | PERFORMANCE | plan identifier and degradation may overlap |
| CAPACITY | SEGMENT_GROWTH / PERFORMANCE | resource pressure may be relevant |
| OBJECT_HEALTH | DEPLOYMENT_CHANGE / SCHEMA_CHANGE | review recent object changes |

These edges are explanatory metadata, not causal rules. A USER+CSRF-protected
rule-relationship endpoint can declare a category edge with optional source and
target rule IDs; all matches show the operator-readable declared reason.

## Hypotheses and contrary evidence

Plan-change hypotheses require both performance evidence and an observed plan
hash change for an SQL identifier. Statistics hypotheses require performance
evidence plus a stale indicator or age of at least seven days. Blocking hypotheses
require performance and lock evidence. Capacity hypotheses are generated only
when capacity observations exist. If degradation precedes the relevant plan,
statistics or blocking evidence, the earlier performance observation is linked
as contradicting evidence and the hypothesis is WEAKENED. A hypothesis is never
labelled root cause or statistically confident. Only an operator can set
`CONFIRMED_BY_OPERATOR` or record a confirmed cause.

## Recommended checks and lock chains

Checks are curated read-only guidance: compare current/prior plan, inspect
blocking chain, review statistics state against normal policy, compare workload
and performance, review capacity/validity/connectivity/coverage. They are not SQL
scripts. The operator records PENDING/RUNNING/COMPLETED/NOT_APPLICABLE and an
optional redacted result summary. Blocking edges are shown only where normalized
evidence explicitly contains both blocking and blocked session identifiers.

## Oracle capabilities and license/privilege gates

The current engine operates only on existing normalized Oracle Findings/evidence.
There are no implicit database-view probes. AWR and ASH are `SKIPPED` unless both
deployment license acknowledgement and privilege gates are explicitly enabled:
`E13DB_ORACLE_AWR_LICENSED`, `E13DB_ORACLE_AWR_PRIVILEGE`,
`E13DB_ORACLE_ASH_LICENSED`, `E13DB_ORACLE_ASH_PRIVILEGE`. Enabling a capability
reports availability; this release still does not run AWR/ASH queries. Missing
privileges/licensing never degrades normal audits.

Plan observations retain database, SQL ID, plan hash, first/last seen and
allow-listed metrics. A plan A→B creates an `EXECUTION_PLAN` evidence item only.
Execution duration/reads/workload evidence must independently exist before the
engine offers a possible contributing-factor hypothesis.

## Capacity projection

A simple linear time-to-threshold projection is shown only with at least three
dated growth samples, positive growth, per-interval growth rates within 25% of
their mean, and an explicit future threshold in normalized evidence. Output gives
sample count, observation window, rate and assumption and is labelled a linear
projection, not a forecast. Missing/unstable evidence suppresses the projection.

## API and operator workflow

`/api/investigations` supports paginated/filterable USER access by database,
status, rule, category, object, confirmed cause and date. Mutations (manual open,
status, cause, resolution, hypothesis disposition, check result and relationship
declaration) require USER authentication plus CSRF. Restore, arbitrary file paths,
arbitrary SQL and destructive database actions are not exposed. The Finding
detail action opens/reuses a case; Investigations Center presents the incident
hierarchy, facts, timeline, reasons for correlations, both sides of hypotheses,
safe checks, operator cause/resolution and recurrence history.
