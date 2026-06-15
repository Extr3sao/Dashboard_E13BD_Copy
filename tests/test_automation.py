import io
import json
import os
import sqlite3
import time
import unittest
import datetime as dt
from unittest.mock import patch
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from pypdf import PdfReader

from src.api.automation_service import AutomationService, compute_next_run, parse_iso_utc
from src.api.automation_analytics_pdf import build_automation_analytics_monthly_pdf
from src.api.main import app
from src.core.automation_store import AutomationStore, _json_loads
from src.core.time_utils import utc_now_iso


class DummyConfigLoader:
    def load_connections(self):
        return {
            "E13DB": {
                "USER": "demo",
                "PASSWORD": "demo",
                "DSN": "demo",
            }
        }

    def resolve_profile_name(self, requested, profiles):
        return requested or "E13DB"

    def get_env_var(self, key, default=""):
        return default


class FakeDBManager:
    def __init__(self, config):
        self.config = config

    def close(self):
        return None


class FakeSMTP:
    sent_messages = []

    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        return None

    def login(self, username, password):
        return None

    def send_message(self, message):
        self.__class__.sent_messages.append(message)


class FlakySMTP(FakeSMTP):
    failures_remaining = 0

    def send_message(self, message):
        if self.__class__.failures_remaining > 0:
            self.__class__.failures_remaining -= 1
            raise OSError("connection reset by peer")
        self.__class__.sent_messages.append(message)


def sample_post_crq_report():
    return {
        "audit_type": "post_crq",
        "context": {
            "profile": "E13DB",
            "schemas": ["APP_USER"],
            "time_filter": {"mode": "preset", "preset": "weekly", "days_back": 7},
            "source_file": "auditoria_post_crq.md",
        },
        "summary": {
            "selected_checks": 1,
            "executed_checks": 1,
            "checks_with_findings": 1,
            "total_findings": 2,
            "checks_with_errors": 0,
            "findings_by_severity": {"ALT": 2},
        },
        "executed_checks": [
            {
                "check_id": "CHECK_01",
                "title": "TAULES RECENTS SENSE PRIMARY KEY",
                "severitat": "ALT",
                "status": "ok",
                "row_count": 2,
            }
        ],
        "results_by_check": [
            {
                "check_id": "CHECK_01",
                "title": "TAULES RECENTS SENSE PRIMARY KEY",
                "severitat": "ALT",
                "status": "ok",
                "row_count": 2,
                "columns": ["ESQUEMA", "TAULA"],
                "rows": [
                    {"ESQUEMA": "APP_USER", "TAULA": "TMP_ALPHA"},
                    {"ESQUEMA": "APP_USER", "TAULA": "TMP_BETA"},
                ],
            }
        ],
        "errors": [],
    }


def sample_post_crq_distribution_report():
    return {
        "audit_type": "post_crq",
        "context": {
            "profile": "E13DB",
            "schemas": ["APP_USER", "APP_AUX"],
            "time_filter": {"mode": "preset", "preset": "weekly", "days_back": 7},
            "source_file": "auditoria_post_crq.md",
        },
        "summary": {
            "selected_checks": 2,
            "executed_checks": 2,
            "checks_with_findings": 2,
            "total_findings": 2,
            "checks_with_errors": 0,
            "findings_by_severity": {"ALT": 1, "MITJA": 1},
        },
        "report_model": {
            "execution_parameters": {
                "profile": "E13DB",
                "generated_at": "2026-03-18 10:00",
                "time_window": {"start_at": "2026-03-11T10:00", "end_at": "2026-03-18T10:00"},
            },
            "enabled_checks": [
                {"check_id": "CHECK_01", "title": "TAULES", "criticality": "Mitjà"},
                {"check_id": "CHECK_03", "title": "SEQÜÈNCIES", "criticality": "Alt"},
            ],
            "lot_summary": [
                {
                    "lot": "LOT_APP",
                    "critical": 0,
                    "medium": 1,
                    "low": 0,
                    "checks": ["CHECK_01"],
                    "schemas": ["APP_USER"],
                    "affected_objects": 1,
                    "first_action": "Crear PK",
                    "dominant_impact": "Risc integritat",
                    "priority": "Mitjà",
                },
                {
                    "lot": "LOT_AUX",
                    "critical": 1,
                    "medium": 0,
                    "low": 0,
                    "checks": ["CHECK_03"],
                    "schemas": ["APP_AUX"],
                    "affected_objects": 1,
                    "first_action": "Definir CACHE",
                    "dominant_impact": "Risc rendiment",
                    "priority": "Alt",
                },
            ],
            "lot_incident_groups": [
                {
                    "lot": "LOT_APP",
                    "check": "CHECK_01",
                    "title": "TAULES RECENTS SENSE PRIMARY KEY",
                    "description": "Taula sense PK",
                    "severity": "Mitjà",
                    "termini_dies": 15,
                    "impacte": "Integritat",
                    "accio_recomanada": "Crear PK",
                    "validacio_posterior": "Reexecutar check",
                    "schemas": [{"nom": "APP_USER", "object_count": 1, "objectes": [{"OBJECTE": "TMP_ALPHA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense PK"}]}],
                },
                {
                    "lot": "LOT_AUX",
                    "check": "CHECK_03",
                    "title": "SEQÜÈNCIES RECENTS SENSE CACHE",
                    "description": "Seqüència sense cache",
                    "severity": "Alt",
                    "termini_dies": 0,
                    "impacte": "Rendiment",
                    "accio_recomanada": "Definir CACHE",
                    "validacio_posterior": "Reexecutar check",
                    "schemas": [{"nom": "APP_AUX", "object_count": 1, "objectes": [{"OBJECTE": "SEQ_BETA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE=0"}]}],
                },
            ],
            "detail_sections": [
                {
                    "check_id": "CHECK_01",
                    "title": "TAULES RECENTS SENSE PRIMARY KEY",
                    "criticality": "Mitjà",
                    "duration_ms": 800,
                    "finding_count": 1,
                    "overview": "Detecta taules sense PK",
                    "columns": ["Lot", "OBJECTE"],
                    "rows": [{"Lot": "LOT_APP", "OBJECTE": "TMP_ALPHA"}],
                },
                {
                    "check_id": "CHECK_03",
                    "title": "SEQÜÈNCIES RECENTS SENSE CACHE",
                    "criticality": "Alt",
                    "duration_ms": 900,
                    "finding_count": 1,
                    "overview": "Detecta seqüències sense cache",
                    "columns": ["Lot", "OBJECTE"],
                    "rows": [{"Lot": "LOT_AUX", "OBJECTE": "SEQ_BETA"}],
                },
            ],
            "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Aplicar correccions"]},
        },
        "executed_checks": [],
        "results_by_check": [
            {"check_id": "CHECK_01", "rows": [{"Lot": "LOT_APP", "OBJECTE": "TMP_ALPHA"}]},
            {"check_id": "CHECK_03", "rows": [{"Lot": "LOT_AUX", "OBJECTE": "SEQ_BETA"}]},
        ],
        "errors": [],
    }


def sample_post_crq_distribution_report_with_no_findings():
    report = sample_post_crq_distribution_report()
    report["report_model"]["lot_summary"].append(
        {
            "lot": "LOT_EMPTY",
            "critical": 0,
            "medium": 0,
            "low": 0,
            "checks": [],
            "schemas": ["APP_EMPTY"],
            "affected_objects": 0,
            "first_action": "-",
            "dominant_impact": "-",
            "priority": "Baix",
        }
    )
    report["context"]["schemas"].append("APP_EMPTY")
    return report


def sample_post_crq_distribution_report_with_generation_errors():
    report = sample_post_crq_distribution_report()
    report["summary"]["checks_with_errors"] = 1
    report["executed_checks"] = [
        {
            "check_id": "CHECK_99",
            "title": "CONNECTIVITAT",
            "severitat": "ALT",
            "status": "error",
            "row_count": 0,
            "error": "ORA-12170: TNS:Connect timeout occurred",
        }
    ]
    report["errors"] = [{"message": "ORA-12170: TNS:Connect timeout occurred"}]
    return report


class TestAutomation(unittest.TestCase):
    def setUp(self):
        unique_path = f"src/db/test_automation_{int(time.time() * 1000000)}.db"
        self.store = AutomationStore(unique_path)
        self.loader = DummyConfigLoader()
        self.reports_dir = "resources/test_automation_reports"
        os.makedirs(self.reports_dir, exist_ok=True)

    def test_compute_next_run_weekly(self):
        next_run = compute_next_run("weekly", {"start_at": "2026-03-01T10:00"}, now=None)
        self.assertTrue(str(next_run).startswith("2026-03-"))

    def test_compute_next_run_interprets_datetime_local_in_local_timezone(self):
        with patch("src.api.automation_service._local_timezone", return_value=ZoneInfo("Europe/Madrid")):
            next_run = compute_next_run(
                "once",
                {"start_at": "2026-03-18T15:40"},
                now=dt.datetime(2026, 3, 18, 14, 0, 0),
            )
        self.assertEqual(next_run, "2026-03-18T14:40:00Z")

    def test_parse_iso_utc_returns_none_for_invalid_values(self):
        self.assertIsNone(parse_iso_utc("not-a-date"))
        self.assertIsNone(parse_iso_utc("2026-99-99"))

    def test_persist_post_crq_analytics_safely_logs_and_returns_false(self):
        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with patch.object(service, "_persist_post_crq_analytics", side_effect=RuntimeError("analytics boom")):
            with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
                persisted = service._persist_post_crq_analytics_safely(
                    7,
                    {"id": 13, "audit_type": "post_crq", "profile": "E13DB"},
                    sample_post_crq_report(),
                    executed_at="2026-03-18T10:00:00Z",
                )

        self.assertFalse(persisted)
        self.assertTrue(any("Post-CRQ analytics persistence failed" in message for message in captured.output))

    def test_json_loads_logs_invalid_payload_and_returns_default(self):
        with self.assertLogs("src.core.automation_store", level="WARNING") as captured:
            result = _json_loads("{bad json", {})
        self.assertEqual(result, {})
        self.assertTrue(any("Invalid JSON payload in automation store" in message for message in captured.output))

    def test_store_job_crud(self):
        created = self.store.create_job(
            {
                "name": "Job CRUD",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [{"type": "email", "enabled": True, "config": {"recipients": ["dba@example.com"]}}],
                "severity_rules": [],
            }
        )
        self.assertEqual(created["name"], "Job CRUD")
        self.assertEqual(len(self.store.list_jobs()), 1)

        updated = self.store.update_job(created["id"], {"name": "Job CRUD 2", "enabled": False})
        self.assertEqual(updated["name"], "Job CRUD 2")
        self.assertFalse(updated["enabled"])

        self.assertTrue(self.store.delete_job(created["id"]))
        self.assertEqual(len(self.store.list_jobs()), 0)

    def test_store_hydrates_post_crq_effective_config_from_job_config(self):
        created = self.store.create_job(
            {
                "name": "Job config hydrated",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "job_config": {
                    "scheduler_options": {"max_concurrency": 3, "max_retries": 1},
                    "criticality_overrides": {"CHECK_01": "CRITIC"},
                },
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        self.assertEqual(created["scheduler_options"], {"max_concurrency": 3, "max_retries": 1})
        self.assertEqual(created["criticality_overrides"], {"CHECK_01": "CRITIC"})

    def test_delete_job_cascades_run_rows_with_foreign_keys_enabled(self):
        created = self.store.create_job(
            {
                "name": "Cascade check",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [{"type": "email", "enabled": True, "config": {"recipients": ["dba@example.com"]}}],
                "severity_rules": [{"severity": "ALT", "create_task": True}],
            }
        )
        run_id = self.store.create_run(created["id"], started_at="2026-03-08T10:00:00Z")
        self.store.complete_run(
            run_id,
            status="success",
            duration_ms=1,
            summary={},
            error_message=None,
            report_path="C:/tmp/report.pdf",
            deliveries=[],
            created_tasks=[],
        )
        self.assertTrue(self.store.delete_job(created["id"]))
        with sqlite3.connect(self.store.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM scheduled_jobs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0], 0)

    def test_store_delivery_routes_roundtrip(self):
        saved = self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True}
                ],
            }
        )
        self.assertEqual(saved["tic_summary_recipients"], ["tic@example.com"])
        self.assertEqual(saved["providers"][0]["provider_code"], "LOT_APP")

    def test_default_delivery_templates_include_without_findings(self):
        templates = self.store.list_delivery_templates()
        self.assertTrue(any(item["template_key"] == "provider_without_findings" for item in templates))

    def test_date_range_for_month_rejects_out_of_range_month(self):
        self.assertEqual(self.store._date_range_for_month("2026-13"), (None, None))
        self.assertEqual(self.store._date_range_for_month("2026-00"), (None, None))

    def test_default_delivery_config_roundtrip_includes_failure_notification_recipients(self):
        saved = self.store.update_delivery_config(
            {
                "failure_notification_recipients": ["suport@example.com", "dba@example.com"],
            }
        )
        self.assertEqual(saved["failure_notification_recipients"], ["suport@example.com", "dba@example.com"])
        templates = self.store.list_delivery_templates()
        self.assertTrue(any(item["template_key"] == "job_generation_failure" for item in templates))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_report())
    def test_execute_job_creates_run_task_and_email(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
                "default_recipients": ["default@example.com"],
            }
        )
        job = self.store.create_job(
            {
                "name": "Post CRQ setmanal",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [{"type": "email", "enabled": True, "config": {"recipients": ["dba@example.com"]}}],
                "severity_rules": [
                    {
                        "severity": "ALT",
                        "create_task": True,
                        "task_priority": "high",
                        "send_email": True,
                        "attach_report": True,
                        "recipients": ["owners@example.com"],
                        "conditions": {"min_findings": 1, "only_when_findings": True},
                        "enabled": True,
                    }
                ],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertTrue(run["report_path"])
        self.assertEqual(len(self.store.list_runs()), 1)
        self.assertEqual(len(self.store.list_tasks()), 1)
        self.assertGreaterEqual(len(FakeSMTP.sent_messages), 2)

    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    def test_execute_post_crq_job_persists_snapshot_and_passes_effective_config(self):
        captured = {}

        def _fake_run_post_crq_audit(**kwargs):
            captured.update(kwargs)
            return sample_post_crq_report()

        job = self.store.create_job(
            {
                "name": "Post CRQ snapshot",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "job_config": {
                    "scheduler_options": {"max_concurrency": 3, "max_heavy_concurrency": 1, "max_retries": 1},
                    "criticality_overrides": {"CHECK_01": "CRITIC"},
                },
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with patch("src.api.automation_service.run_post_crq_audit", side_effect=_fake_run_post_crq_audit):
            run = service.execute_job(job["id"], manual=True)

        self.assertEqual(captured["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(captured["scheduler_options"]["max_concurrency"], 3)

        artifacts_dir = os.path.splitext(run["report_path"])[0] + "_artifacts"
        report_data_path = os.path.join(artifacts_dir, "report_data.json")
        manifest_path = os.path.join(artifacts_dir, "manifest.json")
        self.assertTrue(os.path.exists(report_data_path))
        self.assertTrue(os.path.exists(manifest_path))

        with open(report_data_path, "r", encoding="utf-8") as handle:
            snapshot_payload = json.load(handle)
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        self.assertEqual(snapshot_payload["snapshot_metadata"]["selected_checks"], ["CHECK_01"])
        self.assertEqual(snapshot_payload["snapshot_metadata"]["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(manifest["scheduler_options"]["max_concurrency"], 3)
        self.assertEqual(manifest["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(manifest["selected_checks"], ["CHECK_01"])

    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    def test_execute_post_crq_distribution_job_persists_snapshot_artifacts(self):
        captured = {}

        def _fake_run_post_crq_audit(**kwargs):
            captured.update(kwargs)
            return sample_post_crq_distribution_report()

        job = self.store.create_job(
            {
                "name": "Post CRQ distribution snapshot",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "job_config": {
                    "scheduler_options": {"max_concurrency": 3, "max_heavy_concurrency": 1},
                    "criticality_overrides": {"CHECK_01": "CRITIC"},
                    "delivery": {"targets": ["lots"]},
                    "report_options": {"include_summary": True, "include_lot_reports": True},
                },
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with patch("src.api.automation_service.run_post_crq_audit", side_effect=_fake_run_post_crq_audit):
            run = service.execute_job(job["id"], manual=True)

        self.assertEqual(captured["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(captured["scheduler_options"]["max_concurrency"], 3)

        artifacts_dir = os.path.splitext(run["report_path"])[0] + "_artifacts"
        report_data_path = os.path.join(artifacts_dir, "report_data.json")
        manifest_path = os.path.join(artifacts_dir, "manifest.json")
        self.assertTrue(os.path.exists(report_data_path))
        self.assertTrue(os.path.exists(manifest_path))

        with open(report_data_path, "r", encoding="utf-8") as handle:
            snapshot_payload = json.load(handle)
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        self.assertEqual(snapshot_payload["snapshot_metadata"]["selected_checks"], ["CHECK_01", "CHECK_03"])
        self.assertEqual(snapshot_payload["snapshot_metadata"]["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(manifest["scheduler_options"]["max_concurrency"], 3)
        self.assertEqual(manifest["criticality_overrides"], {"CHECK_01": "CRITIC"})
        self.assertEqual(manifest["selected_checks"], ["CHECK_01", "CHECK_03"])
        self.assertEqual(manifest["summary"]["selected_checks"], 2)

    @patch.object(AutomationService, "_send_email", side_effect=RuntimeError("smtp_down"))
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_report())
    def test_execute_job_logs_rule_email_failures_without_breaking_run(self, _mock_post_crq, _mock_send_email):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        job = self.store.create_job(
            {
                "name": "Regla amb error d'email",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [
                    {
                        "severity": "ALT",
                        "create_task": True,
                        "task_priority": "high",
                        "send_email": True,
                        "attach_report": False,
                        "recipients": ["owners@example.com"],
                        "conditions": {"min_findings": 1, "only_when_findings": True},
                        "enabled": True,
                    }
                ],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
            run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertTrue(any("Severity rule email delivery failed" in message for message in captured.output))

    def test_run_job_avoids_duplicate_parallel_execution(self):
        job = self.store.create_job(
            {
                "name": "No duplicate",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": [],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)

        def slow_execute(*args, **kwargs):
            time.sleep(0.4)
            return {}

        with patch.object(service, "execute_job", side_effect=slow_execute):
            first = service.run_job(job["id"], manual=True)
            second = service.run_job(job["id"], manual=True)
            self.assertTrue(first)
            self.assertFalse(second)
            time.sleep(0.6)

    def test_run_job_is_rejected_when_service_is_stopping(self):
        job = self.store.create_job(
            {
                "name": "Stopping gate",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": [],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )
        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        service._stop_event.set()
        self.assertFalse(service.run_job(job["id"], manual=True))

    def test_run_job_cleans_up_state_when_thread_start_fails(self):
        job = self.store.create_job(
            {
                "name": "Thread fail",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with patch("threading.Thread.start", side_effect=RuntimeError("thread boom")):
            with self.assertRaises(RuntimeError):
                service.run_job(job["id"], manual=True)

        self.assertEqual(service._running_jobs, set())
        self.assertEqual(service._job_threads, set())

    def test_send_failure_notification_logs_delivery_errors(self):
        self.store.update_delivery_config(
            {
                "failure_notification_recipients": ["ops@example.com"],
            }
        )
        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        with patch.object(service, "_send_email_with_tracking", side_effect=RuntimeError("smtp down")):
            with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
                result = service._send_failure_notification(
                    {"id": 5, "name": "Job fail", "profile": "E13DB"},
                    run_id=9,
                    failure_reason="boom",
                )

        self.assertEqual(result[0]["status"], "error")
        self.assertIn("smtp down", result[0]["error"])
        self.assertTrue(any("Failure notification delivery failed" in message for message in captured.output))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_builds_zip_and_sends_split_emails(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proveidors",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertTrue(run["report_path"].endswith(".zip"))
        self.assertEqual(len(run["deliveries"]), 3)
        self.assertEqual(len(FakeSMTP.sent_messages), 3)
        lot_rows = self.store.list_run_lot_statuses(run["id"])
        self.assertTrue(any(item["lot"] == "LOT_APP" and item["detection_status"] == "CON_HALLAZGOS" for item in lot_rows))
        self.assertTrue(any(item["lot"] == "LOT_AUX" and item["email_sent"] for item in lot_rows))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_respects_delivery_targets(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio nomes lots",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "delivery": {
                        "targets": ["lots"],
                        "override_recipients": [],
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertEqual(len(FakeSMTP.sent_messages), 2)
        recipients = [str(message.get("To") or "") for message in FakeSMTP.sent_messages]
        self.assertTrue(all("tic@example.com" not in value for value in recipients))
        self.assertTrue(any("app@example.com" in value for value in recipients))
        self.assertTrue(any("aux@example.com" in value for value in recipients))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_can_override_all_recipients_for_testing(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proves",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "delivery": {
                        "targets": ["lots", "tic"],
                        "test_mode": True,
                        "override_recipients": ["tester@gencat.cat"],
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertEqual(len(FakeSMTP.sent_messages), 3)
        recipients = [str(message.get("To") or "") for message in FakeSMTP.sent_messages]
        self.assertTrue(all(value == "tester@gencat.cat" for value in recipients))
        self.assertFalse(any("app@example.com" in value or "aux@example.com" in value or "tic@example.com" in value for value in recipients))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_test_mode_without_explicit_targets_simulates_all_audiences(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proves sense targets",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "delivery": {
                        "targets": [],
                        "test_mode": True,
                        "override_recipients": ["tester@gencat.cat"],
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertEqual(len(FakeSMTP.sent_messages), 3)
        recipients = [str(message.get("To") or "") for message in FakeSMTP.sent_messages]
        self.assertTrue(all(value == "tester@gencat.cat" for value in recipients))
        self.assertTrue(any(item["audience"] == "tic" and item["status"] == "ok" for item in run["deliveries"]))
        self.assertEqual(sum(1 for item in run["deliveries"] if item["audience"] == "provider" and item["status"] == "ok"), 2)

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_ignores_override_recipients_when_test_mode_is_disabled(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio real",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "delivery": {
                        "targets": ["lots", "tic"],
                        "test_mode": False,
                        "override_recipients": ["tester@gencat.cat"],
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        self.assertEqual(len(FakeSMTP.sent_messages), 3)
        recipients = [str(message.get("To") or "") for message in FakeSMTP.sent_messages]
        self.assertTrue(any("tic@example.com" in value for value in recipients))
        self.assertTrue(any("app@example.com" in value for value in recipients))
        self.assertTrue(any("aux@example.com" in value for value in recipients))
        self.assertFalse(any("tester@gencat.cat" in value for value in recipients))


    def test_deliver_targets_logs_provider_delivery_failures(self):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": [],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proveidor",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        lot_execution = {
            "job_config": {"report_options": {"include_summary": False}},
            "routes": self.store.get_delivery_routes(),
            "items": [
                {
                    "lot": "LOT_APP",
                    "detection_status": "CON_HALLAZGOS",
                    "num_findings": 2,
                    "route_emails": ["app@example.com"],
                    "route_label": "Aplicacions",
                }
            ],
        }
        report_output = {"provider_paths": {"LOT_APP": __file__}, "general_attachment_path": None}

        with patch.object(service, "_send_email_with_tracking", side_effect=RuntimeError("smtp down")):
            with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
                result = service._deliver_targets(job, sample_post_crq_distribution_report(), report_output, run_id=7, lot_execution=lot_execution)

        self.assertEqual(result[0]["status"], "error")
        self.assertIn("smtp down", result[0]["error"])
        self.assertTrue(any("Provider delivery failed" in message for message in captured.output))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_distribution_email_uses_catalan_summary_and_technical_legend(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proveidors",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        service.execute_job(job["id"], manual=True)

        provider_message = next(
            message for message in FakeSMTP.sent_messages
            if "app@example.com" in str(message.get("To") or "")
        )
        body = provider_message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("Resum de l'execució", body)
        self.assertIn("Estat: Amb troballes", body)
        self.assertIn("Llegenda tècnica", body)
        self.assertIn("Consultes afectades:", body)
        self.assertIn("CHECK_01 - TAULES RECENTS SENSE PRIMARY KEY", body)
        self.assertIn("Esquemes afectats:", body)
        self.assertIn("- APP_USER", body)
        self.assertNotIn("- APP_AUX", body)

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_distribution_summary_email_merges_tic_summary_and_tic_route_recipients(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["franciscovalladares@gencat.cat"],
                "providers": [
                    {"provider_code": "TIC", "label": "TIC", "emails": ["joseasdrubal_ext@gencat.cat", "ferran.elias@gencat.cat"], "enabled": True},
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio proveidors",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        service.execute_job(job["id"], manual=True)

        tic_message = next(
            message for message in FakeSMTP.sent_messages
            if "joseasdrubal_ext@gencat.cat" in str(message.get("To") or "")
        )
        recipients_header = str(tic_message.get("To") or "")
        self.assertIn("franciscovalladares@gencat.cat", recipients_header)
        self.assertIn("joseasdrubal_ext@gencat.cat", recipients_header)
        self.assertIn("ferran.elias@gencat.cat", recipients_header)

    @patch("src.api.automation_service.build_post_crq_provider_artifact", side_effect=RuntimeError("pdf lot boom"))
    def test_write_report_logs_provider_artifact_failures(self, _provider_artifact):
        job = self.store.create_job(
            {
                "name": "Distribucio pdfs",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        report = sample_post_crq_distribution_report()
        lot_execution = service._build_distribution_execution(job, report)

        with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
            output = service._write_report(job, 77, report, lot_execution=lot_execution)

        self.assertTrue(any("Provider report generation failed" in message for message in captured.output))
        self.assertEqual(output["lot_execution"]["items"][0]["report_generated"], False)

    def test_technical_legend_only_uses_detected_schemas_not_all_mapped_schemas(self):
        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        report = {
            "report_model": {
                "lot_incident_groups": [
                    {
                        "lot": "AM10",
                        "check": "CHECK_01",
                        "title": "TAULES RECENTS SENSE PRIMARY KEY",
                        "schemas": [
                            {"nom": "E13_RALC_DC"},
                        ],
                    }
                ],
                "lot_summary": [
                    {
                        "lot": "AM10",
                        "checks": ["CHECK_01"],
                        "schemas": ["E13_RALC_DC"],
                    }
                ],
            },
            "finding_envelopes": [
                {
                    "check_id": "CHECK_01",
                    "title": "TAULES RECENTS SENSE PRIMARY KEY",
                    "schema": "E13_RALC_DC",
                    "lot_assignment": {"lot": "AM10"},
                }
            ],
        }

        legend = service._build_technical_legend(report, "AM10")

        self.assertIn("- E13_RALC_DC", legend["affected_schemas"])
        self.assertNotIn("E13_RALC_CFG", legend["affected_schemas"])

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_marks_partial_error_when_provider_route_missing(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio parcial",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "partial_error")
        errors = [item for item in run["deliveries"] if item["status"] == "error"]
        self.assertTrue(any(item.get("provider_code") == "LOT_AUX" for item in errors))
        lot_rows = self.store.list_run_lot_statuses(run["id"])
        self.assertTrue(any(item["lot"] == "LOT_AUX" and not item["email_sent"] for item in lot_rows))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report_with_no_findings())
    def test_execute_distribution_job_can_send_template_without_findings(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                    {"provider_code": "LOT_EMPTY", "label": "Sense troballes", "emails": ["empty@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio sense troballes",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX", "APP_EMPTY"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "send_policy": {
                        "send_only_with_findings": True,
                        "send_without_findings": True,
                        "record_without_findings": True,
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "success")
        lot_rows = self.store.list_run_lot_statuses(run["id"])
        empty_row = next(item for item in lot_rows if item["lot"] == "LOT_EMPTY")
        self.assertEqual(empty_row["detection_status"], "SIN_HALLAZGOS")
        self.assertTrue(empty_row["email_sent"])
        self.assertEqual(empty_row["delivery_result"], "sent")

        without_findings_message = next(
            message for message in FakeSMTP.sent_messages
            if "empty@example.com" in str(message.get("To") or "")
        )
        body_part = without_findings_message.get_body(preferencelist=("plain",))
        body = (body_part or without_findings_message).get_content()
        self.assertIn("no s'hi han detectat anomalies", body)
        self.assertIn("Estat: Sense troballes", body)
        self.assertIn("No s'adjunta cap informe individual", body)
        self.assertFalse(without_findings_message.is_multipart())

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report_with_no_findings())
    def test_manual_retry_without_findings_does_not_require_attachment(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                    {"provider_code": "LOT_EMPTY", "label": "Sense troballes", "emails": ["empty@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Retry sense troballes",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX", "APP_EMPTY"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "send_policy": {
                        "send_only_with_findings": True,
                        "send_without_findings": True,
                        "record_without_findings": True,
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)
        queue_item = service.enqueue_manual_retry(run_id=run["id"], lot="LOT_EMPTY", audience="provider", requested_by="tester")

        processed = service.process_retry_queue_item(queue_item["id"])

        self.assertEqual(processed["status"], "done")
        lot_rows = self.store.list_run_lot_statuses(run["id"], audience="provider", delivery_result="sent")
        self.assertTrue(any(item["lot"] == "LOT_EMPTY" for item in lot_rows))
        self.assertTrue(any("empty@example.com" in str(message.get("To") or "") for message in FakeSMTP.sent_messages))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report_with_generation_errors())
    def test_execute_distribution_job_with_generation_errors_skips_normal_deliveries_and_sends_failure_notification(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
                "failure_notification_recipients": ["suport@example.com"],
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio amb fallada",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {},
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)

        self.assertEqual(run["status"], "error")
        self.assertIsNone(run["report_path"])
        self.assertEqual(len(FakeSMTP.sent_messages), 1)
        self.assertEqual(run["deliveries"][0]["audience"], "failure")
        self.assertEqual(run["deliveries"][0]["status"], "ok")
        message = FakeSMTP.sent_messages[0]
        self.assertIn("suport@example.com", str(message.get("To") or ""))
        body_part = message.get_body(preferencelist=("plain",))
        body = (body_part or message).get_content()
        self.assertIn("No s'ha pogut generar l'informe", body)
        self.assertIn("No s'ha pogut connectar correctament a la BBDD", body)
        self.assertNotIn("app@example.com", str(message.get("To") or ""))
        lot_rows = self.store.list_run_lot_statuses(run["id"])
        self.assertTrue(all(not row["email_sent"] for row in lot_rows))

    def test_list_run_lot_statuses_filters_by_delivery_fields(self):
        job = self.store.create_job(
            {
                "name": "Filters",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": [],
                "checks": [],
                "time_filter": {},
                "report_format": "pdf",
                "schedule_type": "once",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": None,
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {},
            }
        )
        run_id = self.store.create_run(job["id"], started_at="2026-03-19T10:00:00Z")
        self.store.replace_run_lot_statuses(
            run_id,
            job["id"],
            [
                {"lot": "LOT_APP", "detection_status": "CON_HALLAZGOS", "num_findings": 2, "report_generated": True, "email_sent": True, "delivery_audience": "provider", "delivery_result": "sent"},
                {"lot": "LOT_B", "detection_status": "SIN_HALLAZGOS", "num_findings": 0, "report_generated": False, "email_sent": False, "delivery_audience": "provider", "delivery_result": "skipped_no_findings"},
                {"lot": "SIN_MAPEO", "detection_status": "SIN_MAPEO", "num_findings": 1, "report_generated": False, "email_sent": False, "delivery_audience": "none", "delivery_result": "manual_review"},
            ],
            execution_id=f"job-{job['id']}-run-{run_id}",
            executed_at="2026-03-19T10:00:00Z",
        )

        filtered = self.store.list_run_lot_statuses(run_id, audience="provider", delivery_result="sent")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["lot"], "LOT_APP")

    @patch("src.api.automation_service.smtplib.SMTP", FlakySMTP)
    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report_with_no_findings())
    def test_process_due_retry_queue_keeps_processing_after_item_exception(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                    {"provider_code": "LOT_EMPTY", "label": "Sense troballes", "emails": ["empty@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Batch retry resilient",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX", "APP_EMPTY"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {
                    "send_policy": {
                        "send_only_with_findings": True,
                        "send_without_findings": True,
                        "record_without_findings": True,
                    }
                },
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        FakeSMTP.sent_messages = []
        run = service.execute_job(job["id"], manual=True)
        failing_item = service.enqueue_manual_retry(run_id=run["id"], lot="LOT_APP", audience="provider", requested_by="tester")
        valid_item = service.enqueue_manual_retry(run_id=run["id"], lot="LOT_EMPTY", audience="provider", requested_by="tester")
        self.store.update_retry_queue_item(failing_item["id"], {"retry_mode": "auto", "next_attempt_at": "2000-01-01T00:00:00Z"})
        self.store.update_retry_queue_item(valid_item["id"], {"retry_mode": "auto", "next_attempt_at": "2000-01-01T00:00:00Z"})

        original = service.process_retry_queue_item

        def flaky_process(queue_id, *, auto_claimed=False):
            if int(queue_id) == int(failing_item["id"]):
                raise RuntimeError("forced_retry_failure")
            return original(queue_id, auto_claimed=auto_claimed)

        with patch.object(service, "process_retry_queue_item", side_effect=flaky_process):
            processed = service.process_due_retry_queue()

        self.assertTrue(any(item["id"] == int(valid_item["id"]) and item["status"] == "done" for item in processed))
        self.assertTrue(any(item["id"] == int(failing_item["id"]) and item["status"] == "failed" and item.get("error_message") == "forced_retry_failure" for item in processed))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_process_retry_queue_item_logs_delivery_failures(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Retry manual provider",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        run = service.execute_job(job["id"], manual=True)
        queue_item = service.enqueue_manual_retry(run_id=run["id"], lot="LOT_APP", audience="provider", requested_by="tester")

        with patch.object(service, "_send_email_with_tracking", side_effect=RuntimeError("retry down")):
            with self.assertLogs("src.api.automation_service", level="WARNING") as captured:
                result = service.process_retry_queue_item(queue_item["id"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_message"], "retry down")
        self.assertTrue(any("Retry queue delivery failed" in message for message in captured.output))

    @patch("src.api.automation_service.smtplib.SMTP", FakeSMTP)
    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_distribution_report())
    def test_execute_distribution_job_persists_post_crq_analytics(self, _mock_post_crq):
        self.store.update_delivery_config(
            {
                "smtp_host": "smtp.local",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "secret",
                "smtp_use_tls": True,
                "from_email": "oracle-audit@example.com",
            }
        )
        self.store.update_delivery_routes(
            {
                "tic_summary_recipients": ["tic@example.com"],
                "providers": [
                    {"provider_code": "LOT_APP", "label": "Aplicacions", "emails": ["app@example.com"], "enabled": True},
                    {"provider_code": "LOT_AUX", "label": "Auxiliar", "emails": ["aux@example.com"], "enabled": True},
                ],
            }
        )
        job = self.store.create_job(
            {
                "name": "Distribucio analytics",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "checks": ["CHECK_01", "CHECK_03"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "pdf",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {},
            }
        )

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        run = service.execute_job(job["id"], manual=True)

        overview = self.store.get_post_crq_analytics_overview()
        self.assertEqual(overview["runs"], 1)
        self.assertEqual(overview["total_findings"], 2)

        lot_summary = self.store.list_post_crq_lot_analytics(limit=10)
        self.assertTrue(any(item["lot"] == "LOT_APP" and item["total_findings"] >= 1 for item in lot_summary))
        self.assertTrue(any(item["lot"] == "LOT_AUX" and item["total_findings"] >= 1 for item in lot_summary))

        schema_summary = self.store.list_post_crq_schema_analytics(limit=10)
        self.assertTrue(any(item["schema_name"] == "APP_USER" and item["lot"] == "LOT_APP" for item in schema_summary))
        self.assertTrue(any(item["schema_name"] == "APP_AUX" and item["lot"] == "LOT_AUX" for item in schema_summary))

        check_summary = self.store.list_post_crq_check_analytics(limit=10)
        self.assertTrue(any(item["check_id"] == "CHECK_01" and item["total_findings"] >= 1 for item in check_summary))
        self.assertTrue(any(item["check_id"] == "CHECK_03" and item["total_findings"] >= 1 for item in check_summary))

        with self.store._get_connection() as conn:
            execution_rows = conn.execute("SELECT COUNT(*) AS total FROM audit_execution_facts WHERE run_id = ?", (run["id"],)).fetchone()
            self.assertEqual(execution_rows["total"], 1)

    def test_purge_history_removes_old_runs_and_related_records(self):
        job = self.store.create_job(
            {
                "name": "Retention",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": [],
                "checks": [],
                "time_filter": {},
                "report_format": "pdf",
                "schedule_type": "once",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": None,
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {},
            }
        )
        old_started = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45))
        recent_started = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5))
        old_report = os.path.join(self.reports_dir, "old_run_report.zip")
        with open(old_report, "wb") as handle:
            handle.write(b"zip")

        old_run_id = self.store.create_run(job["id"], started_at=old_started)
        self.store.complete_run(
            old_run_id,
            status="success",
            duration_ms=1000,
            summary={},
            report_path=old_report,
            deliveries=[],
            created_tasks=[],
        )
        with self.store._get_connection() as conn:
            conn.execute("UPDATE job_runs SET finished_at = ? WHERE id = ?", (old_started, old_run_id))
            conn.commit()
        self.store.replace_run_lot_statuses(
            old_run_id,
            job["id"],
            [{"lot": "LOT_OLD", "detection_status": "CON_HALLAZGOS", "num_findings": 2}],
            execution_id=f"job-{job['id']}-run-{old_run_id}",
            executed_at=old_started,
        )
        self.store.create_delivery_attempt(
            {
                "run_id": old_run_id,
                "job_id": job["id"],
                "lot": "LOT_OLD",
                "audience": "provider",
                "attempt_no": 1,
                "status": "error",
                "error_message": "timeout",
                "recipients": ["old@example.com"],
                "attachment_name": "provider_lot_old.pdf",
                "template_key": "provider_with_findings",
                "template_snapshot": {},
            }
        )
        self.store.create_retry_queue_item(
            {
                "run_id": old_run_id,
                "job_id": job["id"],
                "lot": "LOT_OLD",
                "audience": "provider",
                "status": "pending",
                "requested_by": "test",
            }
        )
        self.store.create_task(
            source_run_id=old_run_id,
            source_job_id=job["id"],
            title="Old task",
            severity="ALT",
            metadata={},
        )

        recent_run_id = self.store.create_run(job["id"], started_at=recent_started)
        self.store.complete_run(
            recent_run_id,
            status="success",
            duration_ms=1000,
            summary={},
            report_path=None,
            deliveries=[],
            created_tasks=[],
        )
        with self.store._get_connection() as conn:
            conn.execute("UPDATE job_runs SET finished_at = ? WHERE id = ?", (recent_started, recent_run_id))
            conn.commit()

        summary = self.store.get_maintenance_summary(retain_days=30)
        self.assertEqual(summary["old_runs"], 1)
        self.assertEqual(summary["old_lot_statuses"], 1)
        self.assertEqual(summary["old_delivery_attempts"], 1)
        self.assertEqual(summary["old_retry_items"], 1)

        result = self.store.purge_history(retain_days=30)
        self.assertEqual(result["deleted_runs"], 1)
        self.assertEqual(result["deleted_lot_statuses"], 1)
        self.assertEqual(result["deleted_delivery_attempts"], 1)
        self.assertEqual(result["deleted_retry_items"], 1)
        self.assertEqual(result["deleted_tasks"], 1)
        self.assertIn(old_report, result["report_paths"])
        self.assertIsNone(self.store.get_run(old_run_id))
        self.assertIsNotNone(self.store.get_run(recent_run_id))

    def test_purge_retry_queue_clears_items(self):
        job = self.store.create_job(
            {
                "name": "Retry queue",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )
        run_id = self.store.create_run(job["id"], started_at="2026-03-08T10:00:00Z")
        self.store.create_retry_queue_item(
            {
                "run_id": run_id,
                "job_id": job["id"],
                "lot": "LOT_A",
                "audience": "provider",
                "status": "pending",
                "requested_by": "test",
            }
        )
        second_run_id = self.store.create_run(job["id"], started_at="2026-03-08T11:00:00Z")
        self.store.create_retry_queue_item(
            {
                "run_id": second_run_id,
                "job_id": job["id"],
                "lot": "LOT_B",
                "audience": "provider",
                "status": "failed",
                "requested_by": "test",
            }
        )

        result = self.store.purge_retry_queue()
        self.assertEqual(result["deleted_retry_items"], 2)
        self.assertEqual(self.store.list_retry_queue(limit=10), [])

    def test_tick_runs_auto_purge_once_per_day_and_keeps_pending_retry_items(self):
        self.store.update_delivery_config(
            {
                "auto_purge_enabled": True,
                "history_retention_days": 30,
                "retry_retention_days": 30,
                "last_auto_purge_at": "2026-02-01T00:00:00Z",
            }
        )
        job = self.store.create_job(
            {
                "name": "Auto purge",
                "enabled": True,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "schemas": [],
                "checks": [],
                "time_filter": {},
                "report_format": "pdf",
                "schedule_type": "once",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "timeout_seconds": 120,
                "next_run_at": None,
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
                "job_config": {},
            }
        )
        old_started = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45))
        old_run_id = self.store.create_run(job["id"], started_at=old_started)
        self.store.complete_run(
            old_run_id,
            status="success",
            duration_ms=1000,
            summary={},
            report_path=None,
            deliveries=[],
            created_tasks=[],
        )
        with self.store._get_connection() as conn:
            conn.execute("UPDATE job_runs SET finished_at = ? WHERE id = ?", (old_started, old_run_id))
            conn.execute(
                "UPDATE delivery_retry_queue SET updated_at = ? WHERE 1 = 0",
                (old_started,),
            )
            conn.commit()
        self.store.replace_run_lot_statuses(
            old_run_id,
            job["id"],
            [{"lot": "LOT_OLD", "detection_status": "CON_HALLAZGOS", "num_findings": 1}],
            execution_id=f"job-{job['id']}-run-{old_run_id}",
            executed_at=old_started,
        )
        failed_retry = self.store.create_retry_queue_item(
            {
                "run_id": old_run_id,
                "job_id": job["id"],
                "lot": "LOT_OLD",
                "audience": "provider",
                "status": "failed",
                "requested_by": "test",
                "retry_mode": "manual",
            }
        )
        pending_retry = self.store.create_retry_queue_item(
            {
                "run_id": None,
                "job_id": job["id"],
                "lot": "LOT_PENDING",
                "audience": "provider",
                "status": "pending",
                "requested_by": "test",
                "retry_mode": "manual",
            }
        )
        with self.store._get_connection() as conn:
            conn.execute("UPDATE delivery_retry_queue SET updated_at = ? WHERE id = ?", (old_started, int(failed_retry["id"])))
            conn.execute("UPDATE delivery_retry_queue SET updated_at = ? WHERE id = ?", (old_started, int(pending_retry["id"])))
            conn.commit()

        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        result = service.run_scheduled_maintenance()

        self.assertIsNotNone(result)
        self.assertIsNone(self.store.get_run(old_run_id))
        retry_items = self.store.list_retry_queue(limit=20)
        self.assertFalse(any(item["id"] == int(failed_retry["id"]) for item in retry_items))
        self.assertTrue(any(item["id"] == int(pending_retry["id"]) for item in retry_items))

        second = service.run_scheduled_maintenance()
        self.assertIsNone(second)

    def test_build_automation_analytics_monthly_pdf_returns_readable_pdf(self):
        pdf_bytes = build_automation_analytics_monthly_pdf(
            month="2026-03",
            overview={"runs": 3, "total_findings": 9, "lots_with_findings": 4, "checks_with_errors": 1},
            lots=[{"lot": "LOT_APP", "runs": 2, "total_findings": 5, "runs_with_findings": 2}],
            schemas=[{"schema_name": "APP_USER", "lot": "LOT_APP", "runs": 2, "total_findings": 5, "total_checks": 2}],
            checks=[{"check_id": "CHECK_01", "title": "TAULES", "severity": "ALT", "runs": 2, "total_findings": 5, "affected_lots": 1, "affected_schemas": 1}],
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Dashboard mensual d'automatitzacions", extracted)
        self.assertIn("LOT_APP", extracted)
        self.assertIn("CHECK_01", extracted)

    def test_analytics_monthly_pdf_endpoint_returns_pdf(self):
        client = TestClient(app)
        response = client.get("/api/automation/analytics/monthly-report.pdf?month=2026-03")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    @patch("src.api.automation_service.OracleDBManager", FakeDBManager)
    @patch("src.api.automation_service.run_post_crq_audit", side_effect=lambda **kwargs: sample_post_crq_report())
    def test_report_data_endpoint_returns_saved_snapshot(self, _mock_post_crq):
        job = self.store.create_job(
            {
                "name": "Snapshot endpoint",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": ["APP_USER"],
                "checks": ["CHECK_01"],
                "time_filter": {"mode": "preset", "preset": "weekly"},
                "report_format": "markdown",
                "schedule_type": "weekly",
                "schedule_config": {"start_at": "2026-03-08T10:00"},
                "job_config": {
                    "scheduler_options": {"max_concurrency": 2},
                    "criticality_overrides": {"CHECK_01": "CRITIC"},
                },
                "timeout_seconds": 120,
                "next_run_at": "2026-03-08T10:00:00Z",
                "last_run_at": None,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )
        service = AutomationService(self.store, self.loader, reports_dir=self.reports_dir)
        run = service.execute_job(job["id"], manual=True)

        client = TestClient(app)
        with patch("src.api.main.automation_store", self.store):
            response = client.get(f"/api/automation/runs/{run['id']}/report-data")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["audit_type"], "post_crq")
        self.assertEqual(payload["snapshot_metadata"]["selected_checks"], ["CHECK_01"])
        self.assertEqual(payload["snapshot_metadata"]["criticality_overrides"], {"CHECK_01": "CRITIC"})


if __name__ == "__main__":
    unittest.main()
