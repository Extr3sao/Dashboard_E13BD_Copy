import tempfile
import unittest

from src.api.finding_engine import FindingStore, finding_fingerprint
from src.core.internal_db import InternalDBManager


def result(status, value=None, severity="CRITICAL"):
    return {
        "database_id": "PROD_DB", "rule_id": "TABLESPACE_USAGE", "status": status,
        "severity": severity, "summary": "USERS tablespace usage", "metrics": {
            "row_count": value, "comparison_direction": "higher_is_worse",
        }, "evidence": {"usage": value}, "recommendation": "Add capacity or reclaim space.",
    }


class FindingEngineTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False); handle.close()
        self.store = FindingStore(InternalDBManager(handle.name))
        self.context = {"environment": "production", "criticality": "critical"}

    def test_fingerprint_is_stable_only_for_identity_fields(self):
        self.assertEqual(finding_fingerprint("db", "r", "table", "app", "x"), finding_fingerprint(" DB ", "R", "TABLE", "APP", "X"))
        self.assertNotEqual(finding_fingerprint("db", "r", "table", "app", "x"), finding_fingerprint("db", "r", "table", "app", "y"))

    def test_multi_run_lifecycle_prevents_false_resolution_and_dedupes_flags(self):
        first = self.store.reconcile("PROD_DB", [result("FAIL", 82)], audit_run_id="one", target_context=self.context, observed_at=1)
        finding = self.store.list_findings()[0]
        self.assertEqual(finding["delta"], "NEW")
        self.assertEqual(first["red_flags"][0]["priority"], "P1")

        self.store.reconcile("PROD_DB", [result("FAIL", 88)], audit_run_id="two", observed_at=2)
        finding = self.store.list_findings()[0]
        self.assertEqual((finding["delta"], finding["occurrences"]), ("WORSENING", 2))

        third = self.store.reconcile("PROD_DB", [result("FAIL", 94)], audit_run_id="three", observed_at=3)
        self.assertEqual(self.store.list_findings()[0]["delta"], "WORSENING")
        self.assertTrue(any(item["flag_type"] == "WORSENING_FINDING" and item["priority"] == "P1" for item in third["red_flags"]))

        outage = self.store.reconcile("PROD_DB", [result("ERROR")], audit_run_id="four", observed_at=4)
        self.assertEqual(self.store.list_findings()[0]["status"], "OPEN")
        self.assertTrue(any(item["flag_type"] == "COVERAGE_DEGRADED" for item in outage["red_flags"]))

        self.store.reconcile("PROD_DB", [result("FAIL", 86)], audit_run_id="five", observed_at=5)
        self.assertEqual(self.store.list_findings()[0]["delta"], "IMPROVING")
        self.store.reconcile("PROD_DB", [result("PASS")], audit_run_id="six", observed_at=6)
        self.assertEqual(self.store.list_findings(resolved=True)[0]["delta"], "RESOLVED")
        self.store.reconcile("PROD_DB", [result("FAIL", 93)], audit_run_id="seven", observed_at=7)
        reopened = self.store.list_findings()[0]
        self.assertEqual((reopened["delta"], reopened["status"], reopened["occurrences"]), ("REOPENED", "OPEN", 5))
        self.assertEqual(len(self.store.get_finding(reopened["id"])["history"]), 6)

    def test_manual_actions_are_retained_and_audited(self):
        self.store.reconcile("PROD_DB", [result("FAIL", 82)], target_context=self.context)
        finding = self.store.list_findings()[0]
        updated = self.store.action(finding["id"], "ACCEPTED_RISK", "dba", "Capacity project approved", "2030-01-01")
        self.assertEqual(updated["status"], "ACCEPTED_RISK")
        self.store.reconcile("PROD_DB", [result("FAIL", 88)])
        retained = self.store.get_finding(finding["id"])
        self.assertEqual(retained["status"], "ACCEPTED_RISK")
        self.assertEqual(retained["actions"][0]["actor"], "dba")

    def test_failed_execution_creates_health_flag_without_resolving(self):
        self.store.reconcile("PROD_DB", [result("FAIL", 82)], target_context=self.context)
        state = self.store.reconcile("PROD_DB", [], audit_state="FAILED")
        self.assertEqual(self.store.list_findings()[0]["status"], "OPEN")
        self.assertTrue(any(item["flag_type"] == "AUDIT_EXECUTION_FAILURE" for item in state["red_flags"]))
