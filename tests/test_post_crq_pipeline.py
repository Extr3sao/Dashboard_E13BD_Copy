import datetime
import unittest

from src.api import post_crq_pipeline as pipeline


class TestPostCrqPipeline(unittest.TestCase):
    def test_parse_iso_dt_accepts_iso_datetime_and_date_fallback(self):
        self.assertEqual(
            pipeline._parse_iso_dt("2026-03-26T10:11").strftime("%Y-%m-%d %H:%M"),
            "2026-03-26 10:11",
        )
        self.assertEqual(
            pipeline._parse_iso_dt("2026-03-26 broken", end=True),
            datetime.datetime(2026, 3, 26, 23, 59, 59),
        )
        self.assertIsNone(pipeline._parse_iso_dt("broken-value"))

    def test_resolve_time_window_supports_range_and_resolved_at(self):
        self.assertEqual(
            pipeline._resolve_time_window(
                {"mode": "range", "start_date": "2026-03-01", "end_date": "2026-03-05"}
            ),
            {"start_at": "2026-03-01T00:00", "end_at": "2026-03-05T23:59"},
        )
        self.assertEqual(
            pipeline._resolve_time_window(
                {"mode": "range", "range_start_at": "2026-03-24T09:30", "range_end_at": "2026-03-25T08:30"}
            ),
            {"start_at": "2026-03-24T09:30", "end_at": "2026-03-25T08:30"},
        )
        self.assertEqual(
            pipeline._resolve_time_window(
                {"resolved_at": "2026-03-10T08:00", "days_back": 3}
            ),
            {"start_at": "2026-03-07T08:00", "end_at": "2026-03-10T08:00"},
        )

    def test_build_incident_table_entry_check_05_uses_validation_state_without_crashing(self):
        entry = pipeline._build_incident_table_entry(
            "CHECK_05",
            {
                "objecte": "CONSTRAINT_APP_01",
                "tipus": "CONSTRAINT",
                "taula": "APP_USER.T1",
                "estat": "DISABLED",
                "validada": "NO",
                "validation_state": "NOT VALIDATED",
                "data_modificacio_taula": "2026-04-14 10:00",
            },
            "APP_USER",
            None,
            None,
        )

        self.assertEqual(entry["OBJECTE"], "CONSTRAINT_APP_01")
        self.assertIn("Estat validació: NOT VALIDATED", entry["DADA TÈCNICA"])


if __name__ == "__main__":
    unittest.main()
