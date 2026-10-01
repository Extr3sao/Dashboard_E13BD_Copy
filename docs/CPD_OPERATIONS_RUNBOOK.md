# E13DB CPD operations runbook

## Installation assumptions

The verified development/runtime platform is Windows, Python and SQLite on a
local disk. Use a dedicated least-privilege service account, a single API worker,
and one scheduler per pair of stores. WAL databases must not reside on SMB/NFS.
Oracle drivers/client installation follows the main README. External Oracle and
SMTP credentials remain in the existing environment/secret-reference mechanism;
do not put them in service XML, source control, backup metadata or incident notes.
Protect `config/.env`, connection profile files, both database directories and the
backup directory with service-account/administrator-only NTFS ACLs. Database
backups contain operational evidence and are confidential data even without
credentials. Store off-host copies under the same access policy.

Create a venv and install `requirements.txt` with `constraints.txt`. In
`src/web-app`, run `npm ci`, `npm run lint`, `npm test`, `npm run build`. Deploy the
built `dist` directory; Uvicorn serves it directly. No Vite dev server is needed.

## Windows service

Use the established WinSW Windows service wrapper. Install the official signed
WinSW release as `deploy/e13db-service.exe`, beside `deploy/e13db-service.xml`.
Review the XML paths for your deployment and provision `resources/service-logs`.
Run `deploy\e13db-service.exe install` and `deploy\e13db-service.exe start` from an
elevated maintenance terminal. The definition specifies automatic startup,
restart delays, working directory, bounded graceful stop and rotated logs.
Use `deploy\e13db-service.exe stop` and `... restart` for controlled operations.
Verify SCM service status and `/ready` after installation and after reboot.
Do not use `run-clean.ps1` as a production supervisor: it forcibly kills ports.
The wrapper first sends the console stop signal; its 35-second timeout bounds
unresponsive workers. Uvicorn has a 25-second grace budget and application work
has a 15-second total grace budget. Oracle driver timeouts remain required.
Run a single worker (`--workers 1`); live ownership refuses competing schedulers.

## Configuration and startup

Set absolute `INTERNAL_DB_PATH`, `AUTOMATION_DB_PATH`, `E13DB_BACKUP_PATH` and
`E13DB_SCHEDULER_ENABLED=true` in the service account environment or protected
`config/.env`. Configure USER credentials using the existing secret provider.
Tune these operating values for the actual capacity of the CPD:

| Variable | Default |
| --- | --- |
| `E13DB_BACKUP_KEEP_LAST` | 7 |
| `E13DB_BACKUP_DAILY_DAYS` | 30 |
| `E13DB_BACKUP_WEEKLY_WEEKS` | 12 |
| `E13DB_BACKUP_INTERVAL_SECONDS` | 86400 |
| `E13DB_INTEGRITY_INTERVAL_SECONDS` | 86400 |
| `E13DB_DISK_WARNING_BYTES` | 2147483648 |
| `E13DB_DISK_CRITICAL_BYTES` | 536870912 |
| `E13DB_SHUTDOWN_GRACE_SECONDS` | 15 |
| `E13DB_MISSED_JOB_POLICY` | run_once |

Retention variables use `E13DB_RETENTION_<NAME>_DAYS`: `AUDIT_HISTORY` (365),
`RULE_RESULTS` (365), `FINDING_OCCURRENCES` (365), `ALERTS` (365),
`DELIVERY_HISTORY` (90), `REPORTS` (365), `OPERATIONAL_METRICS` (90).
Detailed automation rule results are retained in `audit_check_facts`; finding
observations have their own retention policy. Configuration values must be positive,
critical disk bytes below warning bytes, and keep_last at least one.

Startup validates numeric policy before constructing storage, initializes/migrates
both stores, checks page and FK integrity, initializes delivery diagnostics,
recovers abandoned work and starts scheduling before readiness. Recovery requires
ownership acquisition first internally, so a second live process cannot interrupt
the first process's work. Critical dependency failures abort lifespan and do not
start scheduling. Missing SMTP is a warning; audits remain possible.

## Liveness, readiness and initial diagnosis

`GET /health` and `/healthz` mean the process responds; `GET /ready` and `/readyz`
return 503 until the runtime finishes startup and after shutdown begins. Log in
and open **Operations** for the overall status, reason, recommended component
actions, ownership heartbeat, last tick, queue, database/WAL sizes, free disk,
backup status, configuration diagnostics and recent operational events.
UNKNOWN means no evidence of execution yet, not a fabricated success.
Fleet Dashboard is the health of audited databases, not of E13DB itself.
Use **Run health check** to refresh measurements; reads use cached local health
and never perform integrity scans or SMTP/Oracle probes. Requests carry a safe
`X-Request-ID` for correlation with rotated service stdout/stderr logs.

## Shutdown, restart and crash recovery

Stop through the service manager. New scheduled work stops immediately. Running
audits may finish within the total grace budget; unfinished durable jobs become
`interrupted`. Completion cannot overwrite an interrupted state. The owner lease
is released and a passive WAL checkpoint is performed.
For a hard crash, the next owner waits for the old 60-second lease to expire;
supervisor restart retries are bounded by delays. The owner heartbeat renews every
10 seconds independently of report/backup maintenance. Expired ownership is not
allowed to dispatch scheduled work. The recovered owner interrupts abandoned
runs. Reconciliation receipts and unique keys prevent repeated completed
observations, duplicate active findings/red flags and alert storms. This is not
an exactly-once promise for an external SMTP recipient: a crash after SMTP accepts
mail but before the delivery transaction commits can still cause an ambiguous
delivery outcome. Inspect delivery history before a manual retry.
Missed jobs either `skip` or `run_once`; subsequent schedule advancement skips all
older intervals rather than replaying a backlog storm.

## Storage integrity and SQLite locking

Connections use WAL, foreign_keys ON, busy_timeout 5000 ms and synchronous FULL.
WAL allows readers during writes; FULL prioritizes durability at commit. Bounded
temporary locks wait and recover; a lock exceeding the timeout is an explicit
failure, never an automatic switch to a fresh database. **Run integrity check**
uses quick_check plus foreign_key_check. Startup and daily maintenance do the
same; every backup uses full integrity_check and foreign_key_check.
On corruption: stop the service, preserve both databases and their WAL/SHM,
then follow offline restore. Do not delete WAL files while the process is live.

## Backup and retention

Click **Create Backup** after USER login. The action requires CSRF. SQLite's
online backup API captures committed WAL contents; active files are never copied
directly. Each UUID backup directory contains `internal.db`, `automation.db` and
a manifest with SHA-256 checksums, sizes, schema signatures and schema version.
Operations exposes backup ID, status, size and integrity, not filesystem paths.
Keep the manifest checksum from creation in trusted incident/change records.
Backup rotation preserves keep_last plus one daily/weekly representative within
their configured windows. Two stores are independently consistent snapshots;
no cross-store atomic snapshot is claimed. Stop scheduling before a backup when
an exact cross-store change-window cut is needed. A failed scheduled backup is
retried no more than hourly. Critical low space blocks new backup artifacts.

**Preview retention purge** never deletes anything. Active findings, active red
flags, configuration and manual finding-action audit trails are preserved. For
explicit execution, stop the service and run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.cpd_storage purge --internal C:\E13DB\data\internal.db --automation C:\E13DB\data\automation.db
.\.venv\Scripts\python.exe -m scripts.cpd_storage purge --internal C:\E13DB\data\internal.db --automation C:\E13DB\data\automation.db --execute --limit 1000
```

Each transaction removes at most the limit (maximum 5000) across supported
historical categories. Repeat only after reviewing the new preview. SQLite reuses
freed pages; deletion need not shrink files. No online VACUUM is run. For physical
reclamation, take another backup and use SQLite VACUUM offline with ample space.
CPD maintenance supersedes the older unbounded history purge with a daily bounded
batch using these policies. Active tasks and live delivery retry references also
protect their parent scheduled-audit history. Each store has its own transaction;
cross-store purge is not advertised as a crash-atomic global transaction.

## Offline restore and drill

Restore requires downtime. Stop the service, preserve the current pair and logs,
then validate and prepare into a **new** directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.cpd_storage validate --backup-root C:\E13DB\backups --backup-id <32-hex-id> --checksum <manifest-sha256>
.\.venv\Scripts\python.exe -m scripts.cpd_storage restore --backup-root C:\E13DB\backups --backup-id <32-hex-id> --checksum <manifest-sha256> --destination C:\E13DB\restored-20261001 --confirm-service-stopped
```

Validation checks the trusted manifest checksum, file checksums, full SQLite/FK
integrity and schema signatures/version. Arbitrary IDs, symlinks and existing
restore destinations are rejected. Preparation never overwrites active stores;
the prior pair remains available even if preparation fails. Point **both** store
environment variables at the prepared pair, start the service, check readiness,
then verify Findings/history, Red Flags, Alerts, Reports and audit history in UI.
Protect the prepared directory ACL before switching. Secrets are configured
separately and are not restored from the databases.
Run `python -m pytest tests/test_cpd_operations.py -q` for the fixture restore
drill that backs up all six operational entity groups, changes/deletes data,
prepares the restore and verifies exact original rows.

## Disk, Oracle and SMTP incidents

Disk WARNING/CRITICAL thresholds are deployment-specific. Check Operations free
space and growth; relocate/remove expired off-host backups or run explicit safe
retention. Do not let backup failures create unbounded artifact retries. At
critical space, existing reads may work but new writes can fail: prioritize
freeing disk space before resuming normal dispatch.
One unreachable Oracle target is a target failure: review Fleet Dashboard
connectivity/coverage and validate profile secret references and listener/network
access. Other targets remain independently executable.
SMTP failure degrades Notifications while audits/findings/red flags remain
available. Check SMTP host/port/TLS, sender, recipient list and secret reference.
The last successful delivery restores component health. Do not retry every
failed event at once; preserve cooldown/dedupe policy.

## Upgrade and rollback

1. Create and validate a backup; record backup ID, manifest checksum and current
   application SHA. Preserve external secret configuration separately.
2. Stop service, confirm no live owner; preserve the current complete DB pair.
3. Deploy the intended application revision, requirements and built frontend.
4. Start once; schema initialization/migrations and integrity execute before
   readiness. If startup fails, keep the service stopped and preserve evidence.
5. Check `/ready`, Operations health, login, Fleet/Findings and one fixture or
   approved target audit. Verify backup creation and timeline.

Application rollback means redeploying the previous executable/UI. It is safe
only if that revision is compatible with the current database schema. Do not
assume reverse migrations exist. Database rollback means stopping service and
preparing/restoring the pre-upgrade backup pair with the previous application.
This discards post-backup operational changes; agree the recovery point with the
incident owner. The operations schema is additive; future incompatible changes
must update restore compatibility/version and the upgrade drill.

## Incident evidence

Record service SHA, health/readiness HTTP codes, overall/component explanation,
last ownership heartbeat/tick, running/queued counts, disk/WAL sizes, last
integrity and backup ID/checksum, timeline events and request ID. Operations is
the initial diagnostic surface; raw logs are only needed for deeper root cause.
Never include passwords, Oracle DSNs with embedded credentials, SMTP tokens,
filesystem secret files or unredacted database evidence in tickets.
