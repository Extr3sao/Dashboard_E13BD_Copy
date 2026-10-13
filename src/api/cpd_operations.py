"""Local service operations. No external connectivity probes on HTTP reads."""
from __future__ import annotations

import hashlib
import datetime as dt
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
import uuid

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 1


class OperationsConfig:
    def __init__(self, values=None):
        values = os.environ if values is None else values
        self.backup_path = Path(values.get("E13DB_BACKUP_PATH", "data/backups")).resolve()
        self.keep_last = int(values.get("E13DB_BACKUP_KEEP_LAST", "7"))
        self.daily_days = int(values.get("E13DB_BACKUP_DAILY_DAYS", "30"))
        self.weekly_weeks = int(values.get("E13DB_BACKUP_WEEKLY_WEEKS", "12"))
        self.backup_seconds = int(values.get("E13DB_BACKUP_INTERVAL_SECONDS", "86400"))
        self.integrity_seconds = int(values.get("E13DB_INTEGRITY_INTERVAL_SECONDS", "86400"))
        self.warning_bytes = int(values.get("E13DB_DISK_WARNING_BYTES", str(2 * 1024**3)))
        self.critical_bytes = int(values.get("E13DB_DISK_CRITICAL_BYTES", str(512 * 1024**2)))
        self.grace_seconds = int(values.get("E13DB_SHUTDOWN_GRACE_SECONDS", "15"))
        self.missed_policy = values.get("E13DB_MISSED_JOB_POLICY", "run_once")
        self.retention = {name: int(values.get("E13DB_RETENTION_" + name.upper() + "_DAYS", str(days))) for name, days in {
            "audit_history": 365, "rule_results": 365, "finding_occurrences": 365,
            "alerts": 365, "delivery_history": 90, "reports": 365, "operational_metrics": 90,
        }.items()}
        if (self.keep_last < 1 or min(self.daily_days, self.weekly_weeks) < 0
                or min(self.backup_seconds, self.integrity_seconds, self.grace_seconds) < 1
                or min(self.retention.values()) < 0 or self.retention["reports"] < 1
                or not 0 <= self.critical_bytes < self.warning_bytes
                or self.missed_policy not in {"skip", "run_once"}):
            raise ValueError("invalid_operations_configuration")


class OperationsRuntime:
    def __init__(self, internal, automation, scheduler, alerts, config=None, clock=time.time, disk_usage=shutil.disk_usage):
        self.internal, self.automation, self.scheduler, self.alerts = internal, automation, scheduler, alerts
        self.config = config or OperationsConfig()
        self.clock, self.disk_usage = clock, disk_usage
        self.owner = str(uuid.uuid4())
        self.ready = False
        self.phase = "STARTING"
        self.scheduler_enabled = False
        self._action_lock = threading.Lock()
        self._maintenance_lock = threading.Lock()
        self._cache = {}
        self._last_refresh = 0
        self.last_tick = None
        self.last_integrity = None
        self.last_failure = None
        self.diagnostics = []
        self.startup_steps = []
        self._lease_stop = threading.Event()
        self._lease_thread = None
        self._last_maintenance_failure = None
        self.audit_evidence_service = None

    def _connect(self):
        return self.internal._get_connection()

    def migrate(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS operations_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO operations_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS operations_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL, component TEXT NOT NULL, kind TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations_backups(backup_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,status TEXT NOT NULL,size INTEGER NOT NULL DEFAULT 0,
                    checksum TEXT, database_schema_version INTEGER NOT NULL, integrity TEXT NOT NULL,
                    reason TEXT);
                CREATE TABLE IF NOT EXISTS operations_lease(name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL, heartbeat REAL NOT NULL, expires_at REAL NOT NULL);
            """)
            if "storage_path" not in {r[1] for r in conn.execute("PRAGMA table_info(operations_backups)")}:
                conn.execute("ALTER TABLE operations_backups ADD COLUMN storage_path TEXT")

    def event(self, component, kind, status, reason):
        # Call sites use fixed operator-facing messages, never exception/connection text.
        with self._connect() as conn:
            conn.execute("INSERT INTO operations_events(created_at,component,kind,status,reason) VALUES(?,?,?,?,?)",
                         (self.clock(), component, kind, status, reason))
            conn.execute("DELETE FROM operations_events WHERE id IN (SELECT id FROM operations_events ORDER BY id DESC LIMIT -1 OFFSET 2000)")

    def timeline(self, limit=100):
        with self._connect() as conn:
            return self._rows(conn, "SELECT * FROM operations_events ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),))

    @staticmethod
    def _rows(conn, sql, args=()):
        cur = conn.execute(sql, args)
        names = [col[0] for col in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    def startup(self, scheduler_enabled):
        self.ready = False
        self.phase = "STARTING"
        self.diagnostics = []
        try:
            self.startup_steps = ["load_configuration", "validate_configuration"]
            self.scheduler_enabled = scheduler_enabled
            try:
                self.config.backup_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.diagnostics.append({"level": "WARNING", "component": "Storage", "reason": "Backup directory unavailable; verify storage mount and service account permissions."})
            # Backup files contain operational data: directory is private on POSIX;
            # Windows service provisioning must apply the documented ACL.
            if os.name != "nt" and self.config.backup_path.exists():
                self.config.backup_path.chmod(0o700)
            if not os.access(self.config.backup_path, os.W_OK):
                self.diagnostics.append({"level": "WARNING", "component": "Storage", "reason": "Backup directory is not writable; verify service account permissions."})
            self.startup_steps.extend(["initialize_storage", "run_migrations"])
            self.migrate()
            self.integrity()
            self.startup_steps.extend(["storage_integrity_check", "initialize_providers"])
            try:
                smtp = self.scheduler._delivery_config()
                smtp_valid = smtp.get("smtp_host") and smtp.get("from_email") and smtp.get("default_recipients") and 1 <= int(smtp.get("smtp_port") or 587) <= 65535
            except (ValueError, TypeError):
                smtp_valid = False
            if not smtp_valid:
                self.diagnostics.append({"level": "WARNING", "component": "Notification Engine", "reason": "SMTP delivery configuration incomplete. Configure host, port, sender and recipients."})
            try:
                profiles = self.scheduler.config_loader.load_connections()
                if isinstance(profiles, dict) and any(not all(profile.get(key) for key in ("USER", "PASSWORD", "DSN")) for profile in profiles.values()):
                    self.diagnostics.append({"level": "WARNING", "component": "Audit Engine", "reason": "One or more Oracle target profiles are incomplete. Verify configured secret references and connection profiles; other targets remain available."})
            except Exception:
                self.diagnostics.append({"level": "WARNING", "component": "Audit Engine", "reason": "Oracle target configuration cannot be read. Verify service account configuration permissions."})
            if scheduler_enabled:
                if not self.acquire_ownership():
                    raise RuntimeError("scheduler_ownership_unavailable")
                self.recover()
                self._lease_stop.clear()
                self._lease_thread = threading.Thread(target=self._renew_loop, name="operations-lease", daemon=True)
                self._lease_thread.start()
            elif self.audit_evidence_service:
                # Projection recovery is safe under concurrent retries because
                # each AuditRun and Finding reconciliation is receipt-idempotent.
                self.audit_evidence_service.recover_pending_reconciliations()
            self.startup_steps.extend(["recover_interrupted_work", "acquire_scheduler_ownership"])
            if scheduler_enabled:
                self.scheduler.start()
            self.startup_steps.extend(["start_scheduler", "ready"])
            self.ready = True
            self.phase = "READY"
            self.event("API", "service_started", "HEALTHY", "Runtime initialized; readiness available.")
            self.refresh()
        except Exception:
            self.last_failure = self.clock()
            self.phase = "FAILED"
            logger.error("operations_startup_failed", extra={"event": "startup_failure", "reason": "critical_startup_dependency_unavailable", "stage": self.startup_steps[-1] if self.startup_steps else "configuration"})
            self._lease_stop.set()
            self.scheduler.stop(grace_seconds=self.config.grace_seconds)
            self.release_ownership()
            raise

    def _renew_loop(self):
        while not self._lease_stop.wait(10):
            try:
                if not self.heartbeat():
                    self.ready = False
                    self.phase = "FAILED"
                    self.scheduler._stop_event.set()
                    return
            except sqlite3.Error:
                self.ready = False
                self.phase = "FAILED"
                self.scheduler._stop_event.set()
                return

    def acquire_ownership(self):
        now = self.clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT owner,expires_at FROM operations_lease WHERE name='scheduler'").fetchone()
            if row and row[0] != self.owner and row[1] > now:
                return False
            conn.execute("INSERT INTO operations_lease VALUES('scheduler',?,?,?) ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,heartbeat=excluded.heartbeat,expires_at=excluded.expires_at", (self.owner, now, now + 60))
        return True

    def heartbeat(self):
        with self._connect() as conn:
            cur = conn.execute("UPDATE operations_lease SET heartbeat=?,expires_at=? WHERE name='scheduler' AND owner=? AND expires_at>?", (self.clock(), self.clock() + 60, self.owner, self.clock()))
            return cur.rowcount == 1

    def release_ownership(self):
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM operations_lease WHERE owner=?", (self.owner,))
        except sqlite3.Error:
            logger.error("operations_ownership_release_failed", extra={"reason": "storage_unavailable"})

    def recover(self):
        # Ownership has expired before this method: all runs from the previous sole
        # scheduler are abandoned, even when they are younger than ten minutes.
        if self.audit_evidence_service:
            self.audit_evidence_service.recover_interrupted_runs(now=self.clock(),stale_after_seconds=0)
        with self.automation._get_connection() as conn:
            count = conn.execute("UPDATE job_runs SET status='interrupted',finished_at=datetime('now'),error_message='process_recovery' WHERE status='running'").rowcount
        with self._connect() as conn:
            conn.execute("UPDATE audit_runs SET state='INTERRUPTED',completed_at=? WHERE state='RUNNING'", (self.clock(),))
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "audit_execution_leases" in tables:
                conn.execute("UPDATE audit_execution_leases SET state='INTERRUPTED',expires_at=? WHERE state='RUNNING' AND expires_at<=?", (self.clock(), self.clock()))
        if self.audit_evidence_service:
            self.audit_evidence_service.recover_pending_reconciliations()
        if count:
            self.event("Audit Engine", "work_recovered", "DEGRADED", f"Recovered {count} interrupted audits; completed audits were preserved.")

    def shutdown(self):
        self.ready = False
        self.phase = "STOPPING"
        self.scheduler.stop(grace_seconds=self.config.grace_seconds)
        with self.automation._get_connection() as conn:
            conn.execute("UPDATE job_runs SET status='interrupted',finished_at=datetime('now'),error_message='controlled_shutdown' WHERE status='running'")
        self.event("API", "service_stopped", "UNKNOWN", "Controlled shutdown; unfinished work marked interrupted.")
        self._lease_stop.set()
        if self._lease_thread:
            self._lease_thread.join(timeout=1)
        self.release_ownership()
        for store in (self.internal, self.automation):
            with store._get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def integrity(self):
        results = {}
        for name, store in (("internal", self.internal), ("automation", self.automation)):
            with store._get_connection() as conn:
                # quick_check catches page corruption without the index scan of
                # integrity_check; full integrity_check is used for every backup.
                result = conn.execute("PRAGMA quick_check").fetchall()
                foreign = conn.execute("PRAGMA foreign_key_check").fetchall()
            results[name] = "PASS" if result == [("ok",)] or (len(result) == 1 and result[0][0] == "ok") else "FAIL"
            if foreign:
                results[name] = "FAIL"
        self.last_integrity = {"checked_at": self.clock(), "status": "PASS" if all(x == "PASS" for x in results.values()) else "FAIL", "databases": results}
        if self.last_integrity["status"] != "PASS":
            self.ready = False
            self.phase = "FAILED"
            self.scheduler._stop_event.set()
            raise RuntimeError("storage_integrity_failed")
        return self.last_integrity

    def backups(self):
        with self._connect() as conn:
            # Physical paths are intentionally absent from the browser API.
            return self._rows(conn, "SELECT backup_id,created_at,status,size,checksum,database_schema_version,integrity,reason FROM operations_backups ORDER BY created_at DESC LIMIT 200")

    def backup(self):
        if not self._action_lock.acquire(blocking=False):
            raise ValueError("operations_action_in_progress")
        backup_id = uuid.uuid4().hex
        directory = self.config.backup_path / backup_id
        try:
            if self.disk_usage(self.config.backup_path).free <= self.config.critical_bytes:
                raise ValueError("disk_space_critical_backup_blocked")
            directory.mkdir(mode=0o700)
            manifest = {"backup_id": backup_id, "created_at": self.clock(), "database_schema_version": SCHEMA_VERSION, "files": {}}
            # SQLite online backup API accounts for active WAL and readers/writers.
            # Stores are independent snapshots, not a claimed cross-store atomic cut.
            for name, store in (("internal", self.internal), ("automation", self.automation)):
                path = directory / (name + ".db")
                deadline = time.monotonic() + 30
                def progress(*_):
                    if time.monotonic() > deadline:
                        raise TimeoutError("backup_deadline")
                source = store._get_connection()
                target = sqlite3.connect(path)
                try:
                    source.backup(target, pages=256, progress=progress, sleep=0.02)
                    if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or target.execute("PRAGMA foreign_key_check").fetchall():
                        raise RuntimeError("backup_integrity_failed")
                    signature = hashlib.sha256(json.dumps(target.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall(), separators=(",", ":")).encode()).hexdigest()
                finally:
                    source.close()
                    target.close()
                if os.name != "nt":
                    path.chmod(0o600)
                manifest["files"][name] = {"checksum": file_checksum(path), "size": path.stat().st_size, "schema_signature": signature}
            raw = json.dumps(manifest, sort_keys=True).encode()
            (directory / "manifest.json").write_bytes(raw)
            checksum = hashlib.sha256(raw).hexdigest()
            size = sum(item["size"] for item in manifest["files"].values())
            with self._connect() as conn:
                conn.execute("INSERT INTO operations_backups(backup_id,created_at,status,size,checksum,database_schema_version,integrity,storage_path) VALUES(?,?, 'SUCCESS',?,?,?,'PASS',?)", (backup_id, self.clock(), size, checksum, SCHEMA_VERSION, backup_id))
            self.event("Storage", "backup_completed", "HEALTHY", "Verified online backup completed for both stores.")
            self.rotate_backups()
            self.refresh()
            return {"backup_id": backup_id, "status": "SUCCESS", "size": size, "integrity": "PASS", "checksum": checksum, "database_schema_version": SCHEMA_VERSION}
        except Exception:
            if directory.exists():
                shutil.rmtree(directory)
            with self._connect() as conn:
                conn.execute("INSERT OR REPLACE INTO operations_backups(backup_id,created_at,status,size,checksum,database_schema_version,integrity,reason,storage_path) VALUES(?,?,'FAILED',0,NULL,?,'UNKNOWN','Backup unavailable; verify disk space and service account permissions.',?)", (backup_id, self.clock(), SCHEMA_VERSION, backup_id))
            self.event("Storage", "backup_failed", "DEGRADED", "Backup failed; verify disk space and directory permissions. Auditing remains available.")
            raise
        finally:
            self._action_lock.release()

    def rotate_backups(self):
        with self._connect() as conn:
            rows = self._rows(conn, "SELECT backup_id,created_at FROM operations_backups WHERE status='SUCCESS' ORDER BY created_at DESC")
        keep = {row["backup_id"] for row in rows[:self.config.keep_last]}
        days, weeks = set(), set()
        now = self.clock()
        for row in rows:
            day, week = int(row["created_at"] // 86400), int(row["created_at"] // 604800)
            if now - row["created_at"] <= self.config.daily_days * 86400 and day not in days:
                keep.add(row["backup_id"]); days.add(day)
            if now - row["created_at"] <= self.config.weekly_weeks * 604800 and week not in weeks:
                keep.add(row["backup_id"]); weeks.add(week)
        for row in rows:
            if row["backup_id"] in keep:
                continue
            directory = self.config.backup_path / row["backup_id"]
            if len(row["backup_id"]) != 32 or any(c not in "0123456789abcdef" for c in row["backup_id"]) or directory.is_symlink() or directory.resolve().parent != self.config.backup_path:
                raise ValueError("backup_directory_symlink_rejected")
            if directory.exists():
                shutil.rmtree(directory)
            with self._connect() as conn:
                conn.execute("UPDATE operations_backups SET status='EXPIRED' WHERE backup_id=?", (row["backup_id"],))

    def retention(self, execute=False, limit=1000):
        limit = max(1, min(int(limit), 5000))
        now = self.clock()
        with self._connect() as conn:
            available_tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        diagnostic_references=[]
        if {"investigation_evidence","investigations"}.issubset(available_tables):
            diagnostic_references.append("audit_run_id NOT IN (SELECT DISTINCT e.audit_run_id FROM investigation_evidence e JOIN investigations i ON i.id=e.investigation_id WHERE i.status IN ('OPEN','MONITORING') AND e.audit_run_id IS NOT NULL)")
        if {"finding_occurrences","findings"}.issubset(available_tables):
            diagnostic_references.append("audit_run_id NOT IN (SELECT DISTINCT o.audit_run_id FROM finding_occurrences o JOIN findings f ON f.id=o.finding_id WHERE f.status!='RESOLVED')")
        diagnostic_guard=" AND ".join(diagnostic_references) or "1=1"
        audit_references=[]
        if {"finding_occurrences","findings"}.issubset(available_tables):
            audit_references.append("audit_run_id NOT IN (SELECT DISTINCT o.audit_run_id FROM finding_occurrences o JOIN findings f ON f.id=o.finding_id WHERE f.status!='RESOLVED')")
        if {"investigation_evidence","investigations"}.issubset(available_tables):
            audit_references.append("audit_run_id NOT IN (SELECT DISTINCT e.audit_run_id FROM investigation_evidence e JOIN investigations i ON i.id=e.investigation_id WHERE i.status IN ('OPEN','MONITORING') AND e.audit_run_id IS NOT NULL)")
        audit_guard="state!='RUNNING'"+(" AND "+" AND ".join(audit_references) if audit_references else "")
        policies = [
            ("audit_runs", "completed_at", "audit_history", audit_guard),
            ("finding_occurrences", "observed_at", "finding_occurrences", "finding_id IN (SELECT id FROM findings WHERE status='RESOLVED')"),
            ("red_flags", "updated_at", "alerts", "status='RESOLVED' AND (finding_id IS NULL OR finding_id IN (SELECT id FROM findings WHERE status='RESOLVED'))"),
            ("alert_events", "updated_at", "alerts", "status IN ('CLOSED','RECOVERED') AND actor IS NULL AND id NOT IN (SELECT alert_id FROM alert_deliveries)"),
            ("alert_deliveries", "attempted_at", "delivery_history", "alert_id IN (SELECT id FROM alert_events WHERE status IN ('CLOSED','RECOVERED'))"),
            ("notification_outbox", "created_at", "delivery_history", "target_type='ALERT' AND target_id IN (SELECT id FROM alert_events WHERE status IN ('CLOSED','RECOVERED')) AND status IN ('SENT','FAILED','AMBIGUOUS')"),
            ("operational_reports", "generated_at", "reports", "COALESCE(delivered_at,0)<?"),
            ("operations_events", "created_at", "operational_metrics", "1=1"),
            ("operations_backups", "created_at", "operational_metrics", "status IN ('FAILED','EXPIRED')"),
            ("finding_reconciliation_receipts", "observed_at", "audit_history", "audit_run_id NOT IN (SELECT audit_run_id FROM audit_runs) AND audit_run_id NOT IN (SELECT audit_run_id FROM finding_occurrences)"),
        ]
        if "oracle_diagnostic_observations" in available_tables:
            policies.insert(1,("oracle_diagnostic_observations","observed_at","audit_history",diagnostic_guard))
        result = {"dry_run": not execute, "batch_limit": limit, "configured_retention": self.config.retention, "eligible_records": {}, "deleted": {}}
        with self._connect() as conn:
            if execute:
                conn.execute("BEGIN IMMEDIATE")
            remaining = limit
            for table, date, policy, guard in policies:
                cutoff = now - self.config.retention[policy] * 86400
                where = f"{date}<? AND {guard}"
                args = (cutoff, cutoff) if table == "operational_reports" else (cutoff,)
                count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
                result["eligible_records"][table] = count
                if execute and remaining:
                    cur = conn.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {where} LIMIT ?)", (*args, remaining))
                    result["deleted"][table] = cur.rowcount
                    remaining -= cur.rowcount
            result["oldest_audit"] = conn.execute("SELECT MIN(completed_at) FROM audit_runs").fetchone()[0]
            result["oldest_finding_history"] = conn.execute("SELECT MIN(observed_at) FROM finding_occurrences").fetchone()[0]
        # Independent store transactions are each bounded. Parent deletions are
        # eligible only after children have been purged, avoiding unbounded cascades.
        active = "run_id NOT IN (SELECT source_run_id FROM internal_tasks WHERE status NOT IN ('resolt','resolved','closed') AND source_run_id IS NOT NULL) AND run_id IN (SELECT id FROM job_runs WHERE status!='running')"
        auto_policies = [
            ("audit_check_facts", "executed_at", "rule_results", active),
            ("audit_schema_facts", "executed_at", "audit_history", active),
            ("audit_lot_facts", "executed_at", "audit_history", active),
            ("audit_execution_facts", "executed_at", "audit_history", active),
            ("job_run_lot_statuses", "executed_at", "audit_history", active),
            ("delivery_attempts", "created_at", "delivery_history", active),
            ("job_runs", "finished_at", "audit_history", "status!='running' AND id NOT IN (SELECT source_run_id FROM internal_tasks WHERE source_run_id IS NOT NULL) AND id NOT IN (SELECT run_id FROM delivery_retry_queue WHERE run_id IS NOT NULL) AND id NOT IN (SELECT run_id FROM delivery_attempts WHERE run_id IS NOT NULL) AND id NOT IN (SELECT run_id FROM job_run_lot_statuses) AND id NOT IN (SELECT run_id FROM audit_execution_facts) AND id NOT IN (SELECT run_id FROM audit_check_facts) AND id NOT IN (SELECT run_id FROM audit_schema_facts) AND id NOT IN (SELECT run_id FROM audit_lot_facts)"),
        ]
        with self.automation._get_connection() as conn:
            if execute:
                conn.execute("BEGIN IMMEDIATE")
            for table, date, policy, guard in auto_policies:
                cutoff = dt.datetime.fromtimestamp(now - self.config.retention[policy] * 86400, dt.timezone.utc).isoformat()
                where = f"{date}<? AND {guard}"
                args = (cutoff,)
                result["eligible_records"][table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
                if execute and remaining:
                    cur = conn.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {where} LIMIT ?)", (*args, remaining))
                    result["deleted"][table] = cur.rowcount
                    remaining -= cur.rowcount
        result["reclaim_note"] = "Deletion frees SQLite pages for reuse; file size need not shrink. No online VACUUM is performed."
        result["rule_results"] = "Detailed automation rule results use audit_check_facts; finding history is retained independently."
        if execute:
            self.event("Storage", "retention_completed", "HEALTHY", f"Bounded retention removed {sum(result['deleted'].values())} historical records; active findings and manual actions preserved.")
        return result

    def maintenance(self):
        if not self._maintenance_lock.acquire(blocking=False):
            return
        try:
            self.last_tick = self.clock()
            with self._connect() as conn:
                conn.execute("UPDATE operations_lease SET heartbeat=?,expires_at=? WHERE name='scheduler' AND owner=?", (self.clock(), self.clock() + 60, self.owner))
            try:
                self.alerts.run_scheduled_reports(now=self.clock())
                self._last_maintenance_failure = None
            except Exception:
                self._last_maintenance_failure = self.clock()
                self.event("Reporting Engine", "report_generation_failed", "DEGRADED", "Report generation failed; audits continue. Verify storage and report configuration.")
            if not self.last_integrity or self.clock() - self.last_integrity["checked_at"] >= self.config.integrity_seconds:
                try:
                    self.integrity()
                except (sqlite3.Error, RuntimeError):
                    self.last_failure = self.clock()
            attempts = self.backups()
            interval = 3600 if attempts and attempts[0]["status"] == "FAILED" else self.config.backup_seconds
            if not attempts or self.clock() - attempts[0]["created_at"] >= interval:
                self.backup()
            with self._connect() as conn:
                last_purge = conn.execute("SELECT MAX(created_at) FROM operations_events WHERE kind='retention_completed'").fetchone()[0]
            if last_purge is None or self.clock() - last_purge >= 86400:
                self.retention(execute=True, limit=1000)
        finally:
            try:
                self.refresh()
            finally:
                self._maintenance_lock.release()

    def refresh(self):
        storage = []
        for name, store in (("internal", self.internal), ("automation", self.automation)):
            path = Path(store.db_path)
            usage = self.disk_usage(path.parent)
            free = usage.free
            status = "CRITICAL" if free <= self.config.critical_bytes else "WARNING" if free <= self.config.warning_bytes else "HEALTHY"
            storage.append({"name": name, "database_size": path.stat().st_size, "wal_size": Path(str(path) + "-wal").stat().st_size if Path(str(path) + "-wal").exists() else 0, "available_bytes": free, "disk_status": status})
        backups = self.backups()
        old_storage = {item["name"]: item for item in self._cache.get("storage", [])}
        for item in storage:
            old = old_storage.get(item["name"])
            item["growth_bytes_since_last_check"] = item["database_size"] + item["wal_size"] - old["database_size"] - old["wal_size"] if old else None
        backup_size = sum(b["size"] for b in backups if b["status"] == "SUCCESS")
        with self._connect() as conn:
            lease = self._rows(conn, "SELECT owner,heartbeat,expires_at FROM operations_lease WHERE name='scheduler'")
            audits = self._rows(conn, "SELECT state,completed_at FROM audit_runs ORDER BY completed_at DESC LIMIT 1")
            deliveries = self._rows(conn, "SELECT status,attempted_at FROM (SELECT status,attempted_at,id AS sequence FROM alert_deliveries UNION ALL SELECT CASE WHEN delivery_status='SENT' THEN 'SENT' ELSE 'FAILED' END,delivered_at,id AS sequence FROM operational_reports WHERE delivered_at IS NOT NULL) ORDER BY attempted_at DESC,sequence DESC LIMIT 1")
            reports = self._rows(conn, "SELECT status,generated_at FROM operational_reports ORDER BY generated_at DESC LIMIT 1")
        with self.automation._get_connection() as conn:
            running = conn.execute("SELECT COUNT(*) FROM job_runs WHERE status='running'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM job_runs WHERE status IN ('failed','error','interrupted')").fetchone()[0]
            queued = conn.execute("SELECT COUNT(*) FROM scheduled_jobs WHERE enabled=1 AND next_run_at<=datetime('now')").fetchone()[0]
            next_audit = conn.execute("SELECT MIN(next_run_at) FROM scheduled_jobs WHERE enabled=1").fetchone()[0]
        def component(status, reason, success=None, failure=None, action="No action required."):
            return {"status": status, "reason": reason, "last_success": success, "last_failure": failure, "recommended_action": action}
        with self._connect() as conn:
            delivery_tail = self._rows(conn, "SELECT status,attempted_at FROM (SELECT status,attempted_at,id AS sequence FROM alert_deliveries UNION ALL SELECT CASE WHEN delivery_status='SENT' THEN 'SENT' ELSE 'FAILED' END,delivered_at,id AS sequence FROM operational_reports WHERE delivered_at IS NOT NULL) ORDER BY attempted_at DESC,sequence DESC LIMIT 20")
            consecutive_delivery_failures = 0
            for delivery in delivery_tail:
                if delivery["status"] not in {"FAILED","AMBIGUOUS"}:
                    break
                consecutive_delivery_failures += 1
            if delivery_tail:
                deliveries = [delivery_tail[0]]
        smtp_failed = bool(deliveries and deliveries[0]["status"] in {"FAILED","AMBIGUOUS"})
        try:
            current_smtp = self.scheduler._delivery_config()
            smtp_invalid = not (current_smtp.get("smtp_host") and current_smtp.get("from_email") and current_smtp.get("default_recipients"))
        except Exception:
            smtp_invalid = True
        oracle_invalid = any(d.get("component") == "Audit Engine" for d in self.diagnostics)
        storage_invalid = any(d.get("component") == "Storage" for d in self.diagnostics)
        diagnostics = [d for d in self.diagnostics if d.get("component") not in {"Notification Engine", "Audit Engine", "Storage"}]
        if smtp_invalid and not any(d.get("component") == "Notification Engine" for d in diagnostics):
            diagnostics.append({"level": "WARNING", "component": "Notification Engine", "reason": "SMTP delivery configuration incomplete. Configure host, port, sender and recipients."})
        if oracle_invalid and not any(d.get("component") == "Audit Engine" for d in diagnostics):
            diagnostics.append({"level": "WARNING", "component": "Audit Engine", "reason": "Oracle target configuration cannot be read. Verify service account configuration permissions."})
        if storage_invalid and not any(d.get("component") == "Storage" for d in diagnostics):
            diagnostics.append({"level": "WARNING", "component": "Storage", "reason": "Backup directory unavailable; verify storage mount and service account permissions."})
        scheduler_ok = bool(lease and lease[0]["owner"] == self.owner and lease[0]["expires_at"] > self.clock() and self.scheduler._thread and self.scheduler._thread.is_alive())
        components = {
            "API": component("HEALTHY" if self.ready else "UNKNOWN", "Runtime initialized." if self.ready else "Startup has not completed."),
            "Scheduler": component("HEALTHY" if scheduler_ok else "DEGRADED" if self.scheduler_enabled else "UNKNOWN", "Scheduler owns a live lease." if scheduler_ok else "Scheduler unavailable or disabled.", self.last_tick, action="Enable scheduler and verify process heartbeat." if not scheduler_ok else "No action required."),
            "Audit Engine": component("HEALTHY" if audits and audits[0]["state"] == "SUCCESS" else "DEGRADED" if audits else "UNKNOWN", "Latest audit completed." if audits and audits[0]["state"] == "SUCCESS" else "Latest target audit failed or no audit has run; other targets remain independent.", audits[0]["completed_at"] if audits and audits[0]["state"] == "SUCCESS" else None, audits[0]["completed_at"] if audits and audits[0]["state"] != "SUCCESS" else None, "Review target connectivity in Fleet Dashboard."),
            "Finding Engine": component("HEALTHY" if audits else "UNKNOWN", "Durable finding projection available." if audits else "Awaiting first reconciliation."),
            "Red Flag Engine": component("HEALTHY" if audits else "UNKNOWN", "Durable red flag projection available." if audits else "Awaiting first reconciliation."),
            "Notification Engine": component("DEGRADED" if smtp_failed or smtp_invalid else "HEALTHY" if deliveries else "UNKNOWN", "Email delivery unavailable; audits and findings continue." if smtp_failed or smtp_invalid else "Delivery available." if deliveries else "No delivery attempt recorded.", deliveries[0]["attempted_at"] if deliveries and not smtp_failed else None, deliveries[0]["attempted_at"] if smtp_failed else None, "Verify SMTP host, recipients and connectivity."),
            "Reporting Engine": component("DEGRADED" if self._last_maintenance_failure else "HEALTHY" if reports else "UNKNOWN", "Report generation failed; audits continue." if self._last_maintenance_failure else "Latest report generated." if reports else "Awaiting scheduled report generation.", reports[0]["generated_at"] if reports else None, self._last_maintenance_failure, "Verify storage and report generation configuration."),
            "Storage": component("FAILED" if any(s["disk_status"] == "CRITICAL" for s in storage) or (self.last_integrity and self.last_integrity["status"] == "FAIL") else "DEGRADED" if any(s["disk_status"] == "WARNING" for s in storage) or (backups and backups[0]["status"] == "FAILED") else "HEALTHY", "Disk critical: new backup artifacts are blocked; existing reads remain available." if any(s["disk_status"] == "CRITICAL" for s in storage) else "SQLite available; check disk thresholds and latest backup.", self.last_integrity["checked_at"] if self.last_integrity else None, action="Free space or move backups using the offline runbook."),
        }
        overall = "STARTING" if not self.ready else "CRITICAL" if any(c["status"] == "FAILED" for c in components.values()) else "DEGRADED" if diagnostics or any(c["status"] == "DEGRADED" for c in components.values()) else "HEALTHY"
        previous = self._cache.get("components", {})
        disk_low = any(item["disk_status"] != "HEALTHY" for item in storage)
        prior_disk_low = any(item["disk_status"] != "HEALTHY" for item in self._cache.get("storage", []))
        if disk_low and not prior_disk_low:
            self.alerts._upsert_event("E13DB_SERVICE", "DISK_SPACE_LOW", "P1" if any(item["disk_status"] == "CRITICAL" for item in storage) else "P2", {"id": None, "summary": "E13DB storage free space is below the configured threshold.", "severity": "CRITICAL", "recommendation": "Free disk space or move expired backups; new artifacts are blocked at critical space."}, None, {"environment": "production"}, self.clock())
        elif prior_disk_low and not disk_low:
            with self._connect() as conn:
                conn.execute("UPDATE alert_events SET status='RECOVERED',updated_at=? WHERE database_id='E13DB_SERVICE' AND type='DISK_SPACE_LOW'", (self.clock(),))
        for name, health in components.items():
            if name in previous and previous[name]["status"] != health["status"]:
                self.event(name, "component_status_changed", health["status"], health["reason"])
        self._cache = {"status": overall, "reason": "; ".join([c["reason"] for c in components.values() if c["status"] in {"DEGRADED", "FAILED"}] + [d["reason"] for d in diagnostics]) or "Core service available.", "components": components,
                       "scheduler": {"enabled": self.scheduler_enabled, "owner": lease[0]["owner"] if lease else None, "heartbeat": lease[0]["heartbeat"] if lease else None, "last_tick": self.last_tick, "next_scheduled_audit": next_audit, "running_jobs": running, "queued_jobs": queued, "failed_jobs": failed, "missed_policy": self.config.missed_policy},
                       "storage": storage, "integrity": self.last_integrity, "backup": backups[0] if backups else None,
                       "backup_storage_size": backup_size, "backup_growth_bytes_since_last_check": backup_size - self._cache.get("backup_storage_size", backup_size),
                       "next_scheduled_backup": (next((b["created_at"] for b in backups if b["status"] == "SUCCESS"), self.clock()) + self.config.backup_seconds),
                       "configuration": {"status": "DEGRADED" if diagnostics else "VALID", "diagnostics": diagnostics}, "notification_delivery": {"last_status": deliveries[0]["status"] if deliveries else "UNKNOWN", "last_attempt": deliveries[0]["attempted_at"] if deliveries else None, "consecutive_failures": consecutive_delivery_failures}, "retention": self.config.retention, "updated_at": self.clock()}
        self._last_refresh = self.clock()
        return self._cache

    def summary(self):
        if self.phase == "FAILED":
            return {**self._cache, "status": "CRITICAL", "reason": "Core runtime or storage unavailable. Stop scheduling and verify service ownership, storage and integrity using the runbook."}
        return self._cache or {"status": "STARTING", "reason": "Runtime initialization pending.", "components": {}}

    def is_ready(self):
        if not self.ready:
            return False
        try:
            for store in (self.internal, self.automation):
                path = Path(store.db_path).resolve()
                conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
                try:
                    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                finally:
                    conn.close()
            return True
        except (sqlite3.Error, OSError):
            self.ready = False
            self.phase = "FAILED"
            return False


def file_checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_backup(root, backup_id, expected_checksum=None):
    """Offline validation only; IDs cannot select arbitrary files."""
    if len(backup_id) != 32 or any(c not in "0123456789abcdef" for c in backup_id):
        raise ValueError("invalid_backup_id")
    root = Path(root).resolve()
    directory = root / backup_id
    if directory.is_symlink() or directory.resolve().parent != root:
        raise ValueError("unsafe_backup_path")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("unsafe_backup_manifest")
    if expected_checksum and file_checksum(manifest_path) != expected_checksum:
        raise ValueError("backup_manifest_checksum_mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["database_schema_version"] != SCHEMA_VERSION or manifest["backup_id"] != backup_id or set(manifest["files"]) != {"internal", "automation"}:
        raise ValueError("incompatible_backup_schema")
    for name, metadata in manifest["files"].items():
        path = directory / (name + ".db")
        if path.is_symlink() or path.resolve().parent != directory.resolve() or file_checksum(path) != metadata["checksum"]:
            raise ValueError("backup_checksum_mismatch")
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("backup_integrity_failed")
            signature = hashlib.sha256(json.dumps(conn.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall(), separators=(",", ":")).encode()).hexdigest()
            if signature != metadata["schema_signature"]:
                raise ValueError("backup_schema_mismatch")
        finally:
            conn.close()
    return manifest


def prepare_restore(root, backup_id, destination, expected_checksum):
    """Prepare a new pair of stores offline. Never overwrite a running database.

    Deployment switches paths only after stopping the service and preserving the
    previous pair. Interrupted preparation cannot damage the original stores.
    """
    manifest = validate_backup(root, backup_id, expected_checksum)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("restore_destination_must_be_new")
    destination.mkdir(mode=0o700)
    try:
        for name in ("internal", "automation"):
            shutil.copyfile(Path(root).resolve() / backup_id / (name + ".db"), destination / (name + ".db"))
            if os.name != "nt":
                (destination / (name + ".db")).chmod(0o600)
        # Backup ownership belongs to a dead process, never to the restored service.
        with sqlite3.connect(destination / "internal.db") as conn:
            conn.execute("DELETE FROM operations_lease")
        return {"status": "PREPARED", "backup_id": backup_id, "schema_version": manifest["database_schema_version"]}
    except Exception:
        shutil.rmtree(destination)
        raise
