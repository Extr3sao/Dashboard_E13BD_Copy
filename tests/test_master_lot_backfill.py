import gc
import os
import sqlite3
import tempfile
import unittest

from src.api.master_lot_backfill import apply_master_lot_backfill, build_master_lot_backfill_preview
from src.core.automation_store import AutomationStore


class TestMasterLotBackfill(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.automation_db = os.path.join(self.tempdir.name, "automation.db")
        self.mapping_db = os.path.join(self.tempdir.name, "internal.db")
        self.store = AutomationStore(self.automation_db)
        with sqlite3.connect(self.mapping_db) as connection:
            connection.execute("CREATE TABLE schema_lots (schema_name TEXT PRIMARY KEY, lot_name TEXT NOT NULL)")
            connection.execute("INSERT INTO schema_lots (schema_name, lot_name) VALUES ('APP_USER', 'LOT_APP')")
            connection.execute("INSERT INTO schema_lots (schema_name, lot_name) VALUES ('APP_AUX', 'LOT_APP')")
            connection.execute("INSERT INTO schema_lots (schema_name, lot_name) VALUES ('BILLING', 'LOT_BILL')")
            connection.commit()

    def tearDown(self):
        self.store = None
        gc.collect()
        self.tempdir.cleanup()

    def test_preview_creates_backfill_run_and_items(self):
        preview = build_master_lot_backfill_preview(
            self.store,
            mapping_db_path=self.mapping_db,
            actor="tester",
            reason="preview",
        )
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(preview["summary"]["distinct_lots"], 2)
        self.assertEqual(preview["summary"]["to_create"], 2)
        self.assertTrue(any(item["lot_code"] == "LOT_APP" and item["action"] == "create" for item in preview["items"]))
        events = self.store.list_change_events(entity_type="master_lot_backfill")
        self.assertTrue(any(event["action"] == "preview" for event in events))
        second_preview = build_master_lot_backfill_preview(self.store, mapping_db_path=self.mapping_db)
        self.assertEqual(second_preview["id"], preview["id"])

    def test_preview_marks_disabled_master_lot_as_conflict(self):
        self.store.upsert_master_lots(
            [{"code": "LOT_APP", "label": "Aplicacions", "description": "", "enabled": False, "metadata": {}}],
            actor="tester",
            reason="seed",
        )
        preview = build_master_lot_backfill_preview(self.store, mapping_db_path=self.mapping_db)
        lot_app = next(item for item in preview["items"] if item["lot_code"] == "LOT_APP")
        self.assertEqual(lot_app["action"], "conflict")
        self.assertEqual(lot_app["conflict_code"], "disabled_master_lot")

    def test_apply_backfill_creates_selected_master_lots_and_audits(self):
        preview = build_master_lot_backfill_preview(self.store, mapping_db_path=self.mapping_db)
        applied = apply_master_lot_backfill(
            self.store,
            run_id=preview["id"],
            selected_lot_codes=["LOT_APP"],
            actor="tester",
            reason="apply",
        )
        self.assertEqual(applied["status"], "applied")
        master_lots = {item["code"]: item for item in self.store.list_master_lots()}
        self.assertIn("LOT_APP", master_lots)
        self.assertNotIn("LOT_BILL", master_lots)
        self.assertEqual(master_lots["LOT_APP"]["metadata"]["backfill_run_id"], preview["id"])
        updated_run = self.store.get_master_lot_backfill_run(preview["id"])
        lot_app_item = next(item for item in updated_run["items"] if item["lot_code"] == "LOT_APP")
        self.assertTrue(lot_app_item["applied"])
        events = self.store.list_change_events()
        self.assertTrue(any(event["entity_type"] == "master_lot" and event["entity_key"] == "LOT_APP" for event in events))
        self.assertTrue(any(event["entity_type"] == "master_lot_backfill" and event["action"] == "apply" for event in events))


if __name__ == "__main__":
    unittest.main()
