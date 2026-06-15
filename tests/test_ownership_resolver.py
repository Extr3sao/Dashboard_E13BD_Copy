import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.core.ownership_resolver import detect_ownership_table, load_ownership_mapping, resolve_ownership


class TestOwnershipResolver(unittest.TestCase):
    def _build_db(self, ddl: str, rows: list[tuple]) -> str:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        path = Path(handle.name)
        with sqlite3.connect(str(path)) as connection:
            connection.execute(ddl)
            placeholders = ", ".join(["?"] * len(rows[0])) if rows else ""
            table_name = "esquema_lot" if "esquema_lot" in ddl else "schema_lots"
            if rows:
                connection.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
            connection.commit()
        return str(path)

    def test_detects_current_schema_lots_table(self):
        path = self._build_db(
            "CREATE TABLE schema_lots (schema_name TEXT PRIMARY KEY, lot_name TEXT NOT NULL)",
            [("E13_RTT", "LOT_01")],
        )
        info = detect_ownership_table(path)
        self.assertEqual(info["table"], "schema_lots")
        mapping = load_ownership_mapping(path)
        self.assertEqual(mapping["E13_RTT"]["lot"], "LOT_01")

    def test_detects_future_esquema_lot_table_with_responsable(self):
        path = self._build_db(
            "CREATE TABLE esquema_lot (esquema TEXT PRIMARY KEY, lot TEXT NOT NULL, responsable TEXT)",
            [("E13_GCON", "LOT_02", "Equip GCON")],
        )
        info = detect_ownership_table(path)
        self.assertEqual(info["table"], "esquema_lot")
        assignment = resolve_ownership("E13_GCON", db_path=path)
        self.assertEqual(assignment["lot"], "LOT_02")
        self.assertEqual(assignment["responsable"], "Equip GCON")

    def test_returns_fallback_when_schema_not_found(self):
        path = self._build_db(
            "CREATE TABLE schema_lots (schema_name TEXT PRIMARY KEY, lot_name TEXT NOT NULL)",
            [("E13_RTT", "LOT_01")],
        )
        assignment = resolve_ownership("E13_XYZ", db_path=path)
        self.assertEqual(assignment["lot"], "SENSE LOT")
        self.assertEqual(assignment["responsable"], "No assignat")


if __name__ == "__main__":
    unittest.main()
