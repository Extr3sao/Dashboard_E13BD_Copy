import gc
import os
import sqlite3
import tempfile
import unittest

from src.core.internal_db import InternalDBManager


class TestInternalDBMetaNormalization(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "internal.db")
        self.db = InternalDBManager(self.db_path)

    def tearDown(self):
        self.db = None
        gc.collect()
        self.tempdir.cleanup()

    def test_add_meta_object_normalizes_key_fields(self):
        obj_id = self.db.add_meta_object(
            schema_name=" app_user ",
            object_name=" tmp_alpha ",
            object_type=" table ",
            reason=" reason ",
            risk_level=" high ",
            recommendation=" review ",
            description=" desc ",
            source=" user ",
        )

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT schema_name, object_name, object_type, reason, risk_level, recommendation, description, source FROM meta_objects WHERE id = ?",
                (obj_id,),
            ).fetchone()

        self.assertEqual(
            row,
            ("APP_USER", "tmp_alpha", "TABLE", "reason", "HIGH", "review", "desc", "USER"),
        )

    def test_update_meta_object_normalizes_key_fields(self):
        obj_id = self.db.add_meta_object(
            schema_name="APP_USER",
            object_name="TMP_ALPHA",
            object_type="TABLE",
            reason="reason",
            risk_level="HIGH",
            source="USER",
        )

        updated = self.db.update_meta_object(
            obj_id,
            schema_name=" billing ",
            object_type=" view ",
            risk_level=" medium ",
            source=" detected ",
            description="  new desc  ",
        )

        self.assertTrue(updated)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT schema_name, object_type, risk_level, source, description FROM meta_objects WHERE id = ?",
                (obj_id,),
            ).fetchone()

        self.assertEqual(row, ("BILLING", "VIEW", "MEDIUM", "DETECTED", "new desc"))

    def test_update_meta_object_normalizes_is_obsolete_flag(self):
        obj_id = self.db.add_meta_object(
            schema_name="APP_USER",
            object_name="TMP_ALPHA",
            object_type="TABLE",
            reason="reason",
            risk_level="HIGH",
            is_obsolete=1,
            source="USER",
        )

        updated = self.db.update_meta_object(obj_id, is_obsolete=False)

        self.assertTrue(updated)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT is_obsolete FROM meta_objects WHERE id = ?", (obj_id,)).fetchone()

        self.assertEqual(row, (0,))

    def test_list_meta_objects_normalizes_filter_values(self):
        self.db.add_meta_object(
            schema_name="APP_USER",
            object_name="TMP_ALPHA",
            object_type="TABLE",
            reason="reason",
            risk_level="HIGH",
            source="USER",
        )

        rows, cols = self.db.list_meta_objects(
            schema_name=" app_user ",
            risk_level=" high ",
            source=" user ",
        )

        self.assertEqual(cols[1], "schema_name")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "APP_USER")


if __name__ == "__main__":
    unittest.main()
