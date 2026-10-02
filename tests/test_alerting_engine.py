import tempfile
import unittest

from src.api.alerting_engine import AlertingService
from src.api.finding_engine import FindingStore
from src.core.internal_db import InternalDBManager


def result(status="FAIL", severity="CRITICAL", value=94):
    return {"rule_id": "SPACE", "status": status, "severity": severity, "summary": "password=secret Tablespace USERS at 94%", "recommendation": "Review capacity", "metrics": {"row_count": value, "comparison_direction": "higher_is_worse"}}


class Channel:
    name = "test"
    def __init__(self): self.calls = 0
    def send(self, subject, body, recipients): self.calls += 1


class AmbiguousChannel(Channel):
    def send(self, subject, body, recipients):
        self.calls += 1
        raise TimeoutError("connection closed before SMTP receipt")


class AlertingTests(unittest.TestCase):
    def setUp(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False); db.close()
        self.findings = FindingStore(InternalDBManager(db.name)); self.service = AlertingService(self.findings)
        self.findings.reconcile("DWH", [result()], audit_run_id="one", target_context={"environment":"production", "criticality":"critical"}, observed_at=100)

    def test_alert_storm_is_deduplicated(self):
        first = self.service.evaluate("DWH", now=100); self.assertEqual(len(first), 1)
        self.assertNotIn("secret", first[0]["summary"])
        for point in range(101, 121): self.service.evaluate("DWH", now=point)
        self.assertEqual(len(self.service.list_alerts()), 1)

    def test_escalation_is_a_distinct_priority_policy(self):
        self.findings.set_target_context("DWH", environment="development", criticality="low")
        self.service.evaluate("DWH", now=100)
        self.findings.set_target_context("DWH", environment="production", criticality="critical")
        self.service.evaluate("DWH", now=101)
        self.assertEqual(self.service.list_alerts()[0]["priority"], "P1")

    def test_maintenance_preserves_alert_and_suppresses_initial_delivery(self):
        self.service.add_maintenance("DWH", 90, 110, "planned", "operator")
        events = self.service.evaluate("DWH", now=100)
        self.assertEqual(events[0]["status"], "SUPPRESSED")

    def test_reports_include_aging_and_are_persisted(self):
        daily = self.service.generate_report("daily", now=100 + 90000)
        weekly = self.service.generate_report("weekly", now=100 + 90000)
        self.assertEqual(len(self.service.list_reports()), 2)
        self.assertIn("aging_findings", daily["payload"])
        self.assertIn("E13DB WEEKLY REPORT", weekly["markdown"])

    def test_recovery_links_to_prior_alert(self):
        original = self.service.evaluate("DWH", now=100)[0]
        self.findings.reconcile("DWH", [result("PASS", "LOW", 0)], audit_run_id="two", observed_at=101)
        recovered = self.service.evaluate("DWH", now=102)
        self.assertEqual(self.service.alert(original["id"])["status"], "RECOVERED")
        self.assertEqual(recovered[0]["type"], "RECOVERY")

    def test_existing_scheduler_hook_only_generates_due_reports(self):
        self.assertEqual(len(self.service.run_scheduled_reports(now=100)), 2)
        self.assertEqual(self.service.run_scheduled_reports(now=101), [])

    def test_ambiguous_smtp_attempt_is_never_blindly_retried(self):
        event=self.service.evaluate("DWH",now=100)[0]
        channel=AmbiguousChannel()
        with self.service._connect() as conn:
            self.service._deliver(conn,event,101,channel)
            self.service._deliver(conn,event,102,channel)
        self.assertEqual(channel.calls,1)
        with self.service._connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM notification_outbox WHERE target_id=? ORDER BY id DESC LIMIT 1",(event["id"],)).fetchone()[0],"AMBIGUOUS")

    def test_interrupted_smtp_attempt_recovers_as_ambiguous(self):
        with self.service._connect() as conn:
            conn.execute("INSERT INTO notification_outbox(delivery_key,target_type,target_id,channel,status,attempts,created_at,updated_at,attempt_started_at) VALUES('lost','ALERT',1,'email','ATTEMPTING',1,1,1,1)")
        self.assertEqual(self.service.recover_delivery_attempts(now=1000,stale_after_seconds=120),1)
        with self.service._connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM notification_outbox WHERE delivery_key='lost'").fetchone()[0],"AMBIGUOUS")
