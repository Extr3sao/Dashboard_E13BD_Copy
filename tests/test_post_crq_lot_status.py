import os
import sqlite3
import time
import unittest
from pathlib import Path

from src.api.post_crq_lot_status import (
    LOT_STATUS_NOT_APPLICABLE,
    LOT_STATUS_QUERY_ERROR,
    LOT_STATUS_UNMAPPED,
    LOT_STATUS_WITHOUT_FINDINGS,
    LOT_STATUS_WITH_FINDINGS,
    build_post_crq_lot_execution_matrix,
)


def build_report(*, schemas=None, findings=None, results_by_check=None):
    return {
        "context": {
            "schemas": schemas or [],
        },
        "finding_envelopes": findings or [],
        "results_by_check": results_by_check or [],
        "report_model": {
            "lot_summary": [],
            "lot_incident_groups": [],
        },
    }


class TestPostCrqLotStatus(unittest.TestCase):
    def setUp(self):
        self.db_path = f"src/db/test_post_crq_lot_status_{int(time.time() * 1000000)}.db"
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE schema_lots (schema_name TEXT, lot_name TEXT)")
            connection.execute("INSERT INTO schema_lots (schema_name, lot_name) VALUES ('APP_USER', 'LOT_APP')")
            connection.execute("INSERT INTO schema_lots (schema_name, lot_name) VALUES ('APP_AUX', 'LOT_AUX')")
            connection.commit()

    def tearDown(self):
        if os.path.exists(self.db_path):
            for _ in range(5):
                try:
                    Path(self.db_path).unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.05)

    def test_con_hallazgos_when_lot_has_findings(self):
        report = build_report(
            schemas=["APP_USER"],
            findings=[
                {
                    "runtime_status": "ok",
                    "schema": "APP_USER",
                    "lot_assignment": {"lot": "LOT_APP"},
                }
            ],
            results_by_check=[{"check_id": "CHECK_01", "status": "ok", "rows": [{}]}],
        )

        matrix = build_post_crq_lot_execution_matrix(report, mapping_db_path=self.db_path)
        row = next(item for item in matrix["items"] if item["lot"] == "LOT_APP")

        self.assertEqual(row["detection_status"], LOT_STATUS_WITH_FINDINGS)
        self.assertEqual(row["num_findings"], 1)

    def test_sin_hallazgos_when_lot_is_mapped_and_has_no_findings(self):
        report = build_report(
            schemas=["APP_USER"],
            findings=[],
            results_by_check=[{"check_id": "CHECK_01", "status": "ok", "rows": []}],
        )

        matrix = build_post_crq_lot_execution_matrix(report, mapping_db_path=self.db_path)
        row = next(item for item in matrix["items"] if item["lot"] == "LOT_APP")

        self.assertEqual(row["detection_status"], LOT_STATUS_WITHOUT_FINDINGS)
        self.assertEqual(row["num_findings"], 0)

    def test_no_aplica_when_selected_lot_is_outside_schema_scope(self):
        report = build_report(
            schemas=["APP_USER"],
            findings=[],
            results_by_check=[{"check_id": "CHECK_01", "status": "ok", "rows": []}],
        )

        matrix = build_post_crq_lot_execution_matrix(
            report,
            mapping_db_path=self.db_path,
            job_config={"lot_scope": {"mode": "selected", "selected_lots": ["LOT_AUX"]}},
        )
        row = next(item for item in matrix["items"] if item["lot"] == "LOT_AUX")

        self.assertEqual(row["detection_status"], LOT_STATUS_NOT_APPLICABLE)
        self.assertIsNone(row["num_findings"])

    def test_sin_mapeo_when_findings_cannot_be_associated_to_a_lot(self):
        report = build_report(
            schemas=["APP_USER"],
            findings=[
                {
                    "runtime_status": "ok",
                    "schema": "",
                    "lot_assignment": {"lot": "SENSE LOT"},
                }
            ],
            results_by_check=[{"check_id": "CHECK_01", "status": "ok", "rows": [{}]}],
        )

        matrix = build_post_crq_lot_execution_matrix(report, mapping_db_path=self.db_path)
        row = next(item for item in matrix["items"] if item["detection_status"] == LOT_STATUS_UNMAPPED)

        self.assertEqual(row["lot"], LOT_STATUS_UNMAPPED)
        self.assertTrue(row["needs_manual_review"])

    def test_error_consulta_when_check_fails_for_mapped_lot(self):
        report = build_report(
            schemas=["APP_USER"],
            findings=[],
            results_by_check=[{"check_id": "CHECK_01", "status": "error", "error": "ORA-00942"}],
        )

        matrix = build_post_crq_lot_execution_matrix(report, mapping_db_path=self.db_path)
        row = next(item for item in matrix["items"] if item["lot"] == "LOT_APP")

        self.assertEqual(row["detection_status"], LOT_STATUS_QUERY_ERROR)
        self.assertIsNone(row["num_findings"])


if __name__ == "__main__":
    unittest.main()
