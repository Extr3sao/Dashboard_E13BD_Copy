import json
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.alerting_engine import AlertingService
from src.api.automation_service import AutomationService
from src.api.cpd_operations import OperationsConfig, OperationsRuntime, prepare_restore, validate_backup
from src.api.cpd_router import create_cpd_router
from src.api.finding_engine import FindingStore
from src.api.security import SessionStore
from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager


@pytest.fixture
def runtime(tmp_path):
    internal = InternalDBManager(str(tmp_path / "internal.db"))
    automation = AutomationStore(str(tmp_path / "automation.db"))
    automation.update_delivery_config({"smtp_host": "localhost", "from_email": "service@example.test", "default_recipients": ["operator@example.test"]})
    service = AutomationService(automation, Mock(), reports_dir=str(tmp_path / "reports"))
    alerts = AlertingService(FindingStore(internal), service)
    config = OperationsConfig({"E13DB_BACKUP_PATH": str(tmp_path / "backups"), "E13DB_DISK_WARNING_BYTES": "100", "E13DB_DISK_CRITICAL_BYTES": "10", "E13DB_BACKUP_DAILY_DAYS": "0", "E13DB_BACKUP_WEEKLY_WEEKS": "0", "E13DB_BACKUP_KEEP_LAST": "3"})
    result = OperationsRuntime(internal, automation, service, alerts, config)
    service.operations_runtime = result
    result.startup(False)
    yield result
    result.shutdown()


def result(target="A", value=10):
    return {"database_id": target, "rule_id": "CAPACITY", "status": "FAIL", "severity": "CRITICAL", "metrics": {"value": value}, "summary": "Capacity requires attention", "recommendation": "Review capacity"}


def test_readiness_order_and_shutdown(runtime):
    assert runtime.ready
    assert runtime.startup_steps == ["load_configuration", "validate_configuration", "initialize_storage", "run_migrations", "storage_integrity_check", "initialize_providers", "recover_interrupted_work", "acquire_scheduler_ownership", "start_scheduler", "ready"]
    assert runtime.summary()["status"] == "HEALTHY"
    runtime.shutdown()
    assert not runtime.ready


@pytest.mark.parametrize("values", [
    {"E13DB_BACKUP_KEEP_LAST": "0"}, {"E13DB_DISK_WARNING_BYTES": "1", "E13DB_DISK_CRITICAL_BYTES": "2"},
    {"E13DB_RETENTION_ALERTS_DAYS": "-1"}, {"E13DB_RETENTION_REPORTS_DAYS": "0"}, {"E13DB_MISSED_JOB_POLICY": "storm"},
    {"E13DB_SHUTDOWN_GRACE_SECONDS": "0"}, {"E13DB_BACKUP_INTERVAL_SECONDS": "abc"},
])
def test_invalid_config_fails_closed(values):
    with pytest.raises(ValueError):
        OperationsConfig(values)


def test_integrity_failure_does_not_start_scheduler(runtime, monkeypatch):
    runtime.ready = False
    monkeypatch.setattr(runtime, "integrity", Mock(side_effect=RuntimeError("corrupt")))
    start = Mock()
    monkeypatch.setattr(runtime.scheduler, "start", start)
    with pytest.raises(RuntimeError):
        runtime.startup(True)
    assert not runtime.ready
    start.assert_not_called()


def test_sqlite_configuration(runtime):
    for store in (runtime.internal, runtime.automation):
        with store._get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_backup_restore_drill_all_operational_entities(runtime, tmp_path):
    findings = runtime.alerts.findings
    findings.reconcile("A", [result()], audit_run_id="audit-original")
    # Use a fixture channel: no network dependence in a storage restore drill.
    runtime.alerts._deliver = lambda *_: None
    runtime.alerts.evaluate("A")
    runtime.alerts.generate_report()
    tables = ["findings", "finding_occurrences", "red_flags", "alert_events", "operational_reports", "audit_runs"]
    with runtime._connect() as conn:
        original = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
    assert all(original.values())
    backup = runtime.backup()
    validate_backup(runtime.config.backup_path, backup["backup_id"], backup["checksum"])
    with runtime._connect() as conn:
        conn.execute("DELETE FROM finding_occurrences")
        conn.execute("UPDATE findings SET summary='modified'")
        conn.execute("DELETE FROM operational_reports")
    restored = tmp_path / "restored"
    prepare_restore(runtime.config.backup_path, backup["backup_id"], restored, backup["checksum"])
    with sqlite3.connect(restored / "internal.db") as conn:
        for table in tables:
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == original[table]
        assert conn.execute("SELECT COUNT(*) FROM operations_lease").fetchone()[0] == 0


def test_checksum_and_traversal_rejected(runtime, tmp_path):
    backup = runtime.backup()
    with pytest.raises(ValueError, match="invalid_backup_id"):
        validate_backup(runtime.config.backup_path, "../internal.db")
    path = runtime.config.backup_path / backup["backup_id"] / "internal.db"
    with path.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        validate_backup(runtime.config.backup_path, backup["backup_id"], backup["checksum"])
    with pytest.raises(ValueError):
        prepare_restore(runtime.config.backup_path, backup["backup_id"], tmp_path, backup["checksum"])


def test_manifest_tampering_rejected(runtime):
    backup = runtime.backup()
    manifest = runtime.config.backup_path / backup["backup_id"] / "manifest.json"
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(ValueError, match="manifest_checksum"):
        validate_backup(runtime.config.backup_path, backup["backup_id"], backup["checksum"])


def test_backup_rotation(runtime):
    for _ in range(7):
        runtime.backup()
    assert len([b for b in runtime.backups() if b["status"] == "SUCCESS"]) == 3
    assert len(list(runtime.config.backup_path.iterdir())) == 3


def test_low_disk_blocks_artifacts_and_explains_impact(runtime):
    runtime.disk_usage = lambda _: SimpleNamespace(free=1)
    summary = runtime.refresh()
    assert summary["status"] == "CRITICAL"
    assert "backup artifacts are blocked" in summary["reason"]
    with pytest.raises(ValueError, match="disk_space"):
        runtime.backup()
    assert not list(runtime.config.backup_path.iterdir())


def test_backup_path_failure_is_controlled(runtime):
    runtime.config.backup_path.rmdir()
    runtime.config.backup_path.write_text("not a directory")
    with pytest.raises(OSError):
        runtime.backup()
    assert runtime.backups()[0]["status"] == "FAILED"
    assert runtime.ready


def test_crash_recovery_fenced_ownership_and_no_duplicate_findings(runtime):
    job = runtime.automation.create_job({"name": "test", "audit_type": "post_crq", "profile": "A"})
    run = runtime.automation.create_run(job["id"])
    runtime.alerts.findings.reconcile("A", [result()], audit_run_id="same-audit")
    assert runtime.acquire_ownership()
    rival = OperationsRuntime(runtime.internal, runtime.automation, runtime.scheduler, runtime.alerts, runtime.config)
    rival.migrate()
    assert not rival.acquire_ownership()
    with runtime._connect() as conn:
        conn.execute("UPDATE operations_lease SET expires_at=0")
    assert rival.acquire_ownership()
    assert not runtime.heartbeat()
    rival.recover()
    assert runtime.automation.get_run(run)["status"] == "interrupted"
    rival.alerts.findings.reconcile("A", [result()], audit_run_id="same-audit")
    finding = rival.alerts.findings.list_findings()[0]
    assert finding["occurrences"] == 1
    with runtime._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM finding_occurrences").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0] == 1
    rival.release_ownership()


def test_graceful_stop_has_total_bound_and_persists_interrupted(runtime):
    job = runtime.automation.create_job({"name": "long", "audit_type": "post_crq", "profile": "A"})
    run = runtime.automation.create_run(job["id"])
    blocker = threading.Event()
    worker = threading.Thread(target=lambda: blocker.wait(5), daemon=True)
    runtime.scheduler._job_threads.add(worker)
    worker.start()
    runtime.config.grace_seconds = 0.05
    started = time.monotonic()
    runtime.shutdown()
    assert time.monotonic() - started < 1
    assert runtime.automation.get_run(run)["status"] == "interrupted"
    runtime.automation.complete_run(run, status="success")
    assert runtime.automation.get_run(run)["status"] == "interrupted"
    blocker.set(); worker.join()


def test_missed_execution_is_coalesced_to_one_without_backlog_storm(runtime, monkeypatch):
    job = runtime.automation.create_job({"name": "daily", "audit_type": "post_crq", "profile": "A", "schedule_type": "daily", "schedule_config": {"start_at": "2020-01-01T00:00:00Z"}, "next_run_at": "2020-01-01T00:00:00Z"})
    with runtime.automation._get_connection() as conn:
        conn.execute("UPDATE scheduled_jobs SET next_run_at='2020-01-01T00:00:00Z' WHERE id=?", (job["id"],))
    assert runtime.acquire_ownership()
    runtime.scheduler._stop_event.clear()
    now = "2030-01-01T00:00:00Z"
    monkeypatch.setattr("src.api.automation_service.utc_now", lambda: __import__("datetime").datetime.fromisoformat(now.replace("Z", "+00:00")).replace(tzinfo=None))
    executed = []
    monkeypatch.setattr(runtime.scheduler, "run_job", lambda job_id, **kwargs: executed.append(kwargs) or True)
    runtime.scheduler.tick()
    persisted = runtime.automation.get_job(job["id"])["next_run_at"]
    assert len(executed) == 1
    assert "2030" in persisted
    runtime.scheduler.tick()
    assert len(executed) == 1


def test_safe_bounded_retention_preserves_active_and_manual_state(runtime):
    old = time.time() - 800 * 86400
    runtime.alerts.findings.reconcile("A", [result()], audit_run_id="old-active", observed_at=old)
    runtime.alerts.findings.reconcile("B", [result("B")], audit_run_id="old-resolved", observed_at=old)
    runtime.alerts.findings.reconcile("B", [{**result("B"), "status": "PASS"}], audit_run_id="resolve-B", observed_at=old)
    preview = runtime.retention()
    assert preview["eligible_records"]["audit_runs"] == 3
    assert preview["eligible_records"]["finding_occurrences"] == 2
    assert preview["dry_run"]
    outcome = runtime.retention(True, limit=1)
    assert sum(outcome["deleted"].values()) == 1
    assert runtime.alerts.findings.list_findings(database="A")[0]["status"] == "OPEN"
    with runtime._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM finding_occurrences WHERE finding_id IN (SELECT id FROM findings WHERE database_id='A')").fetchone()[0] == 1


def test_sqlite_temporarily_locked_recovers(runtime):
    lock = sqlite3.connect(runtime.internal.db_path, check_same_thread=False)
    lock.execute("BEGIN IMMEDIATE")
    timer = threading.Timer(0.05, lock.commit)
    timer.start()
    try:
        runtime.event("Storage", "lock_recovered", "HEALTHY", "Storage lock released within busy timeout.")
    finally:
        timer.join(); lock.close()
    assert runtime.timeline()[0]["kind"] == "lock_recovered"


def test_report_failure_isolated(runtime, monkeypatch):
    monkeypatch.setattr(runtime.alerts, "run_scheduled_reports", Mock(side_effect=RuntimeError("report failed")))
    runtime.maintenance()
    assert runtime.summary()["components"]["Reporting Engine"]["status"] == "DEGRADED"
    runtime.alerts.findings.reconcile("A", [result()], audit_run_id="continues")
    assert runtime.alerts.findings.list_findings()


def test_operations_api_user_csrf_and_no_filesystem_paths(runtime):
    app = FastAPI()
    sessions = SessionStore()
    app.include_router(create_cpd_router(runtime, sessions, "session"))
    client = TestClient(app)
    assert client.get("/api/operations/summary").status_code == 401
    session = sessions.create("operator")
    csrf = sessions.csrf_token(session)
    client.cookies.set("session", session)
    assert client.post("/api/operations/backups").status_code == 403
    response = client.post("/api/operations/backups", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    summary = client.get("/api/operations/summary")
    assert str(runtime.internal.db_path) not in summary.text
    assert str(runtime.config.backup_path) not in summary.text
    service_session = sessions.create("machine", role="SERVICE")
    client.cookies.set("session", service_session)
    assert client.post("/api/operations/backups", headers={"X-CSRF-Token": sessions.csrf_token(service_session)}).status_code == 401


def test_hard_process_crash_and_restart_recovery(runtime):
    source = '''
import sys, time
from unittest.mock import Mock
from src.core.internal_db import InternalDBManager
from src.core.automation_store import AutomationStore
from src.api.automation_service import AutomationService
from src.api.finding_engine import FindingStore
from src.api.alerting_engine import AlertingService
from src.api.cpd_operations import OperationsRuntime, OperationsConfig
i=InternalDBManager(sys.argv[1]); a=AutomationStore(sys.argv[2])
s=AutomationService(a, Mock(), reports_dir=sys.argv[3])
r=OperationsRuntime(i,a,s,AlertingService(FindingStore(i),s),OperationsConfig({'E13DB_BACKUP_PATH':sys.argv[4],'E13DB_DISK_WARNING_BYTES':'100','E13DB_DISK_CRITICAL_BYTES':'10'}))
r.startup(True)
j=a.create_job({'name':'hard-crash','audit_type':'post_crq','profile':'A'})
run=a.create_run(j['id'])
print(run, flush=True)
time.sleep(120)
'''
    child = subprocess.Popen([sys.executable, "-c", source, str(runtime.internal.db_path), str(runtime.automation.db_path), runtime.scheduler.reports_dir, str(runtime.config.backup_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = child.stdout.readline().strip()
        assert line.isdigit(), child.stderr.read() if child.poll() is not None else line
        run = int(line)
        assert runtime.automation.get_run(run)["status"] == "running"
        child.kill()  # actual OS process termination, no lifespan/finally callback
        child.wait(timeout=10)
        assert runtime.automation.get_run(run)["status"] == "running"
        assert not runtime.acquire_ownership()
        # Fast-forward the real persisted lease expiry, rather than sleeping a minute.
        runtime.clock = lambda: time.time() + 61
        assert runtime.acquire_ownership()
        runtime.recover()
        assert runtime.automation.get_run(run)["status"] == "interrupted"
        assert runtime.integrity()["status"] == "PASS"
        runtime.release_ownership()
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=10)
        child.stdout.close(); child.stderr.close()


def test_backup_credentials_and_metadata_are_secret_free(runtime):
    runtime.automation.update_delivery_config({"smtp_password": "must-not-store", "teams_webhook": "must-not-store"})
    backup = runtime.backup()
    directory = runtime.config.backup_path / backup["backup_id"]
    with sqlite3.connect(directory / "automation.db") as conn:
        assert conn.execute("SELECT smtp_password,teams_webhook FROM delivery_config").fetchone() == (None, None)
    assert "must-not-store" not in json.dumps(runtime.backups())
    assert "must-not-store" not in (directory / "manifest.json").read_text()


def test_upgrade_readiness_and_application_rollback_compatible_schema(runtime):
    # Additive migration is repeatable on the same storage; previous runtime data
    # survives a new manager/runtime initialization and a prepared restore.
    runtime.alerts.findings.reconcile("A", [result()], audit_run_id="pre-upgrade")
    backup = runtime.backup()
    runtime.shutdown()
    runtime.migrate(); runtime.migrate()
    runtime.startup(False)
    assert runtime.ready
    assert runtime.alerts.findings.list_findings()[0]["occurrences"] == 1
    validate_backup(runtime.config.backup_path, backup["backup_id"], backup["checksum"])


def test_service_definition_has_supervision_contract():
    from pathlib import Path
    import xml.etree.ElementTree as ET
    service = ET.parse(Path(__file__).parents[1] / "deploy" / "e13db-service.xml").getroot()
    assert service.findtext("startmode") == "Automatic"
    assert service.findall("onfailure")[0].attrib["action"] == "restart"
    assert service.findtext("workingdirectory")
    assert "--workers 1" in service.findtext("arguments")
    assert service.findtext("stoptimeout") == "35 sec"
    assert "password" not in ET.tostring(service).decode().lower()


def test_accelerated_soak_and_cpd_failure_recovery(runtime, monkeypatch):
    """420 cycles / 3 targets / 14 days, with real durable engines and storage."""
    start = int(time.time() // 604800) * 604800 + 3600
    now = [start]
    runtime.clock = lambda: now[0]
    sent = []
    failing = [False]
    class Channel:
        name = "fixture-smtp"
        def send(self, *_):
            if failing[0]:
                raise ConnectionError("SMTP unavailable")
            sent.append(now[0])
    original_deliver = runtime.alerts._deliver
    monkeypatch.setattr(runtime.alerts, "_deliver", lambda conn, event, at: original_deliver(conn, event, at, Channel()))
    failing[0] = True
    # First active finding tests delivery isolation before the long soak.
    runtime.alerts.findings.reconcile("SMTP-PROBE", [result("SMTP-PROBE")], audit_run_id="smtp-probe", observed_at=now[0])
    runtime.alerts.evaluate("SMTP-PROBE", now=now[0])
    assert runtime.refresh()["components"]["Notification Engine"]["status"] == "DEGRADED"
    failing[0] = False
    runtime.alerts.findings.reconcile("SMTP-PROBE", [{**result("SMTP-PROBE"), "status": "PASS"}], audit_run_id="smtp-probe-recovered", observed_at=now[0])
    runtime.alerts.evaluate("SMTP-PROBE", now=now[0] + 1)
    with runtime._connect() as conn:
        conn.execute("UPDATE alert_deliveries SET status='SENT',attempted_at=?", (now[0] + 2,))
    assert runtime.acquire_ownership()
    runtime.scheduler_enabled = True
    runtime.scheduler.start()
    jobs = [runtime.automation.create_job({"name": target, "audit_type": "post_crq", "profile": target}) for target in ("A", "B", "C")]
    audits = 0
    for day in range(14):
        now[0] = start + day * 86400
        # Accelerated lease heartbeat remains real SQL, using the simulated clock.
        with runtime._connect() as conn:
            conn.execute("UPDATE operations_lease SET expires_at=?", (now[0] + 60,))
        assert runtime.heartbeat()
        runtime.last_tick = now[0]
        for cycle in range(10):
            runtime.scheduler.tick()
            for job in jobs:
                target = job["profile"]
                run = runtime.automation.create_run(job["id"])
                run_id = f"{day}-{cycle}-{target}"
                runtime.alerts.findings.reconcile(target, [result(target, 10 + cycle)], audit_run_id=run_id, observed_at=now[0])
                runtime.alerts.evaluate(target, now=now[0])
                runtime.automation.complete_run(run, status="success")
                audits += 1
        runtime.alerts.run_scheduled_reports(now=now[0])
        runtime.backup()
        runtime.retention(True, limit=50)
        if day == 3:
            failing[0] = True
            runtime.alerts.findings.reconcile("SMTP-DOWN", [result("SMTP-DOWN")], audit_run_id="smtp-down", observed_at=now[0])
            runtime.alerts.evaluate("SMTP-DOWN", now=now[0])
            with runtime._connect() as conn:
                assert conn.execute("SELECT COUNT(*) FROM alert_deliveries WHERE status IN ('FAILED','AMBIGUOUS')").fetchone()[0] > 0
            assert runtime.refresh()["components"]["Notification Engine"]["status"] == "DEGRADED"
        if day == 4:
            abandoned = runtime.automation.create_run(jobs[0]["id"])
            runtime.recover()
            assert runtime.automation.get_run(abandoned)["status"] == "interrupted"
        if day == 5:
            failing[0] = False
            runtime.alerts.findings.reconcile("SMTP-DOWN", [{**result("SMTP-DOWN"), "status": "PASS"}], audit_run_id="smtp-up", observed_at=now[0])
            runtime.alerts.evaluate("SMTP-DOWN", now=now[0])
            assert runtime.refresh()["components"]["Notification Engine"]["status"] == "HEALTHY"
    runtime.integrity()
    summary = runtime.refresh()
    assert summary["status"] == "HEALTHY"
    with runtime.automation._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM job_runs WHERE status='running'").fetchone()[0] == 0
    with runtime._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM operations_lease WHERE expires_at<?", (now[0],)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM (SELECT fingerprint FROM findings GROUP BY fingerprint HAVING COUNT(*)>1)").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM (SELECT dedupe_key FROM red_flags GROUP BY dedupe_key HAVING COUNT(*)>1)").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM operational_reports WHERE report_type='daily'").fetchone()[0] == 14
        assert conn.execute("SELECT COUNT(*) FROM operational_reports WHERE report_type='weekly'").fetchone()[0] == 2
    assert len([b for b in runtime.backups() if b["status"] == "SUCCESS"]) == 3
    assert len(sent) < audits / 5
    assert audits == 420
    assert len(jobs) == 3
    assert runtime.scheduler._thread.is_alive()
