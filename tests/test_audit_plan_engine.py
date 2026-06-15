import asyncio
import unittest

from src.api.audit_engine import AuditEngine


class MockDBManager:
    def execute_query(self, query, params=None):
        q = " ".join((query or "").split())

        if "FROM dba_users u" in q and "Q01" not in q:
            cols = [
                "USERNAME",
                "ACCOUNT_STATUS",
                "DAYS_OLD",
                "SIZE_GB",
                "OBJECT_COUNT",
                "LAST_LOGIN_DAYS",
                "ACTIVE_JOBS",
                "APEX_APPLICATIONS",
                "EXTERNAL_DEPENDENCIES_OUT",
                "INBOUND_REFERENCES",
                "DAYS_SINCE_NEWEST_DDL",
                "TABLES_STATS_RECENT_30D",
                "TABLES_WITH_MODS_30D",
                "JOBS_STARTED_RECENT",
                "ENABLED_TRIGGERS",
                "ALARM_1_ACTIVITY_RECENT",
                "ALARM_2_JOBS",
                "ALARM_3_APEX",
                "ALARM_4_EXTERNAL_DEPS",
                "ALARM_5_INBOUND_REFS",
                "ALARM_6_TRIGGERS",
            ]
            row = (
                params.get("schema_name", "TEST"),
                "OPEN",
                2000,
                0.02,
                12,
                999,
                0,
                0,
                0,
                0,
                500,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )
            return [row], cols

        if "FROM dba_segments" in q and "GROUP BY owner" in q:
            return [(params.get("schema_name", "TEST"), 0.02, 3)], ["ESQUEMA", "SIZE_GB", "SEGMENT_COUNT"]

        if "FROM dba_users" in q and "default_tablespace" in q.lower():
            return [(params.get("schema_name", "TEST"),)], ["USERNAME"]

        # Retorn buit per la resta
        return [], ["DUMMY"]


class ErrorDBManager:
    def __init__(self):
        self.last_error = "simulated_query_error"

    def execute_query(self, query, params=None):
        self.last_error = "simulated_query_error"
        return None, None


class BindCaptureDBManager:
    def __init__(self):
        self.calls = []
        self.last_error = None

    def execute_query(self, query, params=None):
        self.calls.append((query, params))
        return [(1,)], ["VALUE"]


class OptionalErrorDBManager:
    def __init__(self):
        self.last_error = "optional_failure"

    def execute_query(self, query, params=None):
        return None, None


class TestAuditPlanEngine(unittest.TestCase):
    def test_deep_audit_returns_plan_data(self):
        engine = AuditEngine(MockDBManager())
        result = asyncio.run(engine.get_deep_schema_audit("demo_schema"))

        self.assertEqual(result["username"], "DEMO_SCHEMA")
        self.assertIn("executed_queries", result)
        self.assertGreaterEqual(len(result["executed_queries"]), 10)
        self.assertIn(result["audit_result"], ["NO ELIMINAR", "PRECAUCIO", "ELIMINAR"])
        self.assertIsInstance(result["obsolescence_score"], int)

    def test_plan_aggregate_totals(self):
        engine = AuditEngine(MockDBManager())
        report = asyncio.run(engine.run_plan_audit(["A", "B"]))

        self.assertEqual(report["plan"], "Q01-Q19")
        self.assertEqual(report["totals"]["schemas"], 2)
        self.assertIn("decision_counts", report["totals"])

    def test_deep_audit_invalidates_score_when_mandatory_queries_fail(self):
        engine = AuditEngine(ErrorDBManager())
        result = asyncio.run(engine.get_deep_schema_audit("demo_schema"))

        self.assertEqual(result["obsolescence_score"], 0)
        self.assertEqual(result["audit_result"], "PRECAUCIO")
        self.assertEqual(result["summary"].get("STATUS"), "QUERY_ERRORS")
        self.assertEqual(result["score_meta"].get("data_quality"), "insufficient")
        self.assertGreater(result["score_meta"].get("mandatory_errors", 0), 0)

    def test_run_query_filters_unused_bind_params(self):
        dbm = BindCaptureDBManager()
        engine = AuditEngine(dbm)

        rows, meta = engine._run_query(
            "QX",
            "select :schema_name from dual where owner = :owner",
            {"schema_name": "APP", "owner": "SYS", "ignored": "XXX"},
        )

        self.assertEqual(rows, [{"VALUE": 1}])
        self.assertEqual(dbm.calls[0][1], {"schema_name": "APP", "owner": "SYS"})
        self.assertEqual(meta["status"], "ok")

    def test_run_query_marks_optional_failures_without_crashing(self):
        engine = AuditEngine(OptionalErrorDBManager())

        rows, meta = engine._run_query("QX", "select 1 from dual", {}, optional=True)

        self.assertEqual(rows, [])
        self.assertEqual(meta["status"], "optional_error")
        self.assertEqual(meta["error"], "optional_failure")

    def test_as_number_returns_default_for_invalid_values(self):
        engine = AuditEngine()

        self.assertEqual(engine._as_number("broken", 7.5), 7.5)
        self.assertEqual(engine._as_number(None, 3.0), 3.0)


if __name__ == "__main__":
    unittest.main()
