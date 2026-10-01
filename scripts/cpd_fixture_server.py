"""Explicit test-only Oracle/SMTP adapters around the real API and scheduler."""
import os
from pathlib import Path
import time

if os.environ.get("E13DB_CPD_FIXTURE_MODE") != "true":
    raise RuntimeError("CPD fixture server requires explicit test-mode opt-in")

from src.api import main
from src.api.alerting_engine import SmtpNotificationChannel

controls = Path(os.environ["E13DB_CPD_FIXTURE_CONTROLS"])
controls.mkdir(parents=True, exist_ok=True)


def send_fixture(self, subject, body, recipients):
    if (controls / "smtp-down").exists():
        raise ConnectionError("fixture_smtp_unavailable")


SmtpNotificationChannel.send = send_fixture


def audit_fixture(job):
    (controls / "audit-started").write_text(str(job["id"]))
    while (controls / "hold-audit").exists():
        time.sleep(0.05)
    with main.automation_store._get_connection() as conn:
        row = conn.execute("SELECT MAX(id) FROM job_runs WHERE job_id=? AND status='running'", (job["id"],)).fetchone()
    run_id = f"fixture-job-{job['id']}-run-{row[0]}"
    target = job["profile"]
    main.finding_store.reconcile(target, [{"database_id": target, "rule_id": "CAPACITY", "status": "FAIL", "severity": "CRITICAL", "summary": "Fixture capacity issue", "metrics": {"value": 10}, "recommendation": "Review target capacity."}], audit_run_id=run_id)
    main.alerting_service.evaluate(target)
    return [{"username": target, "summary": {"STATUS": "OK"}}]


def report_fixture(job, run_id, data, **_):
    path = controls / f"audit-{run_id}.md"
    path.write_text(f"# Fixture audit {run_id}\nTarget: {job['profile']}\n")
    return str(path)


main.automation_service._run_audit = audit_fixture
main.automation_service._write_report = report_fixture
main.automation_service._deliver_targets = lambda *_, **__: []
main.automation_service._apply_rules = lambda *_, **__: []
if not main.automation_store.list_jobs():
    main.automation_store.create_job({"name": "CPD fixture", "audit_type": "deep_scan", "profile": "CPD-FIXTURE", "schedule_type": "once", "next_run_at": "2020-01-01T00:00:00Z"})
main.finding_store.set_target_context("CPD-FIXTURE", environment="production", criticality="critical")
if not main.finding_store.list_findings(database="CPD-FIXTURE"):
    main.finding_store.reconcile("CPD-FIXTURE", [{"database_id":"CPD-FIXTURE", "rule_id":"SQL_ELAPSED", "status":"FAIL", "severity":"CRITICAL", "summary":"SQL execution duration increased", "owner":"APP_FIXTURE", "object_name":"ORDERS_FIXTURE", "object_type":"TABLE", "metrics":{"value":11.4,"comparison_direction":"higher_is_worse"}, "evidence":{"elapsed_seconds":11.4,"unit":"s","sql_id":"FIXTURE_SQL"}}], audit_run_id="fixture-investigation", observed_at=time.time())

app = main.app
