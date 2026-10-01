import tempfile
import unittest

from src.api.finding_engine import FindingStore
from src.core.internal_db import InternalDBManager


def check(status, severity="LOW", value=0):
    return {"rule_id": "R1", "status": status, "severity": severity, "summary": "capacity", "metrics": {"row_count": value, "comparison_direction": "higher_is_worse"}}


class OperationalDashboardTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False); handle.close()
        self.store = FindingStore(InternalDBManager(handle.name))

    def test_fleet_distinguishes_healthy_critical_unreachable_and_degraded(self):
        self.store.reconcile("DB-A", [check("PASS")], audit_run_id="a", target_context={"environment": "production", "criticality": "critical"}, observed_at=100)
        self.store.reconcile("DB-B", [check("FAIL", "CRITICAL", 94)], audit_run_id="b", target_context={"environment": "production", "criticality": "critical"}, observed_at=100)
        self.store.reconcile("DB-C", [], audit_run_id="c", audit_state="FAILED", target_context={"environment": "production", "criticality": "high"}, observed_at=100)
        self.store.reconcile("DB-D", [check("PASS"), check("ERROR")], audit_run_id="d", target_context={"environment": "preproduction", "criticality": "medium"}, observed_at=100)
        fleet = self.store.fleet(now=101)
        health = {item["database_id"]: item["health_status"] for item in fleet["targets"]}
        self.assertEqual(health, {"DB-A": "HEALTHY", "DB-B": "CRITICAL", "DB-C": "AUDIT_FAILED", "DB-D": "DEGRADED"})
        self.assertEqual(fleet["targets"][0]["database_id"], "DB-B")

    def test_staleness_and_trends_are_explicit(self):
        self.store.reconcile("DB-A", [check("PASS")], audit_run_id="a", target_context={"environment": "production", "criticality": "critical"}, observed_at=1)
        self.assertEqual(self.store.health("DB-A", now=90000)["health_status"], "UNKNOWN")
        self.assertEqual(len(self.store.trends("DB-A", 48, now=90000)), 1)
        history = self.store.audit_history("DB-A")
        self.assertEqual((history[0]["coverage_state"], history[0]["checks_total"]), ("FULL", 1))
