import gc
import os
import tempfile
import unittest

from src.core.internal_db import InternalDBManager


class TestSchemaLotMapping(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "internal.db")
        self.db = InternalDBManager(self.db_path)

    def tearDown(self):
        self.db = None
        gc.collect()
        self.tempdir.cleanup()

    def test_list_schema_lots_empty_by_default(self):
        self.assertEqual(self.db.list_schema_lots(), [])

    def test_upsert_schema_lots_normalizes_and_replaces_mapping(self):
        updated = self.db.upsert_schema_lots(
            [
                {"schema_name": "app_user", "lot_name": "lot_app"},
                {"schema_name": "billing", "lot_name": " lot_bill "},
            ]
        )
        self.assertEqual(
            updated,
            [
                {"schema_name": "APP_USER", "lot_name": "LOT_APP"},
                {"schema_name": "BILLING", "lot_name": "LOT_BILL"},
            ],
        )

        replaced = self.db.upsert_schema_lots(
            [
                {"schema_name": "ops", "lot_name": ""},
            ]
        )
        self.assertEqual(replaced, [{"schema_name": "OPS", "lot_name": "SENSE LOT"}])


if __name__ == "__main__":
    unittest.main()
