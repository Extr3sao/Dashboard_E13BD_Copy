import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.query_sync_service import (
    FITXER_EXPL,
    FITXER_MD,
    FITXER_TXT,
    QuerySyncService,
)


class TestQuerySyncService(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.db_path = self.root / "internal.db"
        self._create_db()

    def tearDown(self):
        try:
            self.tmpdir.cleanup()
        except PermissionError:
            pass

    def _create_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE sincronitzacio_fitxers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    fitxer TEXT NOT NULL,
                    estat TEXT,
                    darrera_sync TEXT,
                    error_missatge TEXT,
                    UNIQUE(check_id, fitxer)
                )
                """
            )

    def _read_status(self, check_id: str):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT fitxer, estat, error_missatge FROM sincronitzacio_fitxers WHERE check_id = ? ORDER BY fitxer",
                (check_id,),
            ).fetchall()
        return {fitxer: {"estat": estat, "error": error} for fitxer, estat, error in rows}

    def test_sync_check_marks_explanation_ok_when_md_and_txt_succeed(self):
        (self.root / FITXER_MD).write_text(
            "```sql\n-- ====================\n-- CHECK_01: prova\n-- ====================\nSELECT 1 FROM dual;\n```\n",
            encoding="utf-8",
        )
        (self.root / FITXER_TXT).write_text("CHECK_01 | SELECT 1 FROM dual\n", encoding="utf-8")
        (self.root / FITXER_EXPL).write_text(
            "# Catàleg\n\n## CHECK_01 — Prova\n### Què detecta\nAntic contingut.\n",
            encoding="utf-8",
        )
        service = QuerySyncService(self.root, str(self.db_path))

        service.mark_pending("CHECK_01")
        result = service.sync_check(
            "CHECK_01",
            "```sql\n-- ====================\n-- CHECK_01: actualitzat\n-- ====================\nSELECT 2 FROM dual;\n```",
            "CHECK_01 | SELECT 2 FROM dual",
            "## CHECK_01 — Prova actualitzada\n### Què detecta\nNou contingut.\n### Validació posterior\nReexecutar.",
        )

        self.assertEqual(result["errors"], [])
        status = self._read_status("CHECK_01")
        self.assertEqual(status[FITXER_MD]["estat"], "OK")
        self.assertEqual(status[FITXER_TXT]["estat"], "OK")
        self.assertEqual(status[FITXER_EXPL]["estat"], "OK")
        self.assertIsNone(status[FITXER_EXPL]["error"])
        self.assertIn("Prova actualitzada", (self.root / FITXER_EXPL).read_text(encoding="utf-8"))

    def test_sync_check_marks_explanation_error_when_one_file_fails(self):
        (self.root / FITXER_MD).write_text(
            "```sql\n-- ====================\n-- CHECK_01: prova\n-- ====================\nSELECT 1 FROM dual;\n```\n",
            encoding="utf-8",
        )
        (self.root / FITXER_EXPL).write_text(
            "# Catàleg\n\n## CHECK_01 — Prova\n### Què detecta\nAntic contingut.\n",
            encoding="utf-8",
        )
        service = QuerySyncService(self.root, str(self.db_path))

        service.mark_pending("CHECK_01")
        result = service.sync_check(
            "CHECK_01",
            "```sql\n-- ====================\n-- CHECK_01: actualitzat\n-- ====================\nSELECT 2 FROM dual;\n```",
            "CHECK_01 | SELECT 2 FROM dual",
            "## CHECK_01 — Prova actualitzada\n### Què detecta\nNou contingut.\n### Validació posterior\nReexecutar.",
        )

        self.assertEqual(result["txt"], "ERROR")
        status = self._read_status("CHECK_01")
        self.assertEqual(status[FITXER_MD]["estat"], "OK")
        self.assertEqual(status[FITXER_TXT]["estat"], "ERROR")
        self.assertEqual(status[FITXER_EXPL]["estat"], "OK")

    def test_sync_check_updates_explanation_block_without_duplicating_it(self):
        (self.root / FITXER_MD).write_text(
            "```sql\n-- ====================\n-- CHECK_01: prova\n-- ====================\nSELECT 1 FROM dual;\n```\n",
            encoding="utf-8",
        )
        (self.root / FITXER_TXT).write_text("CHECK_01 | SELECT 1 FROM dual\n", encoding="utf-8")
        (self.root / FITXER_EXPL).write_text(
            "# Catàleg\n\n## CHECK_01 — Prova\n### Què detecta\nAntic contingut.\n\n## CHECK_02 — Altre\n### Què detecta\nFix.\n",
            encoding="utf-8",
        )
        service = QuerySyncService(self.root, str(self.db_path))

        result = service.sync_check(
            "CHECK_01",
            "```sql\n-- ====================\n-- CHECK_01: actualitzat\n-- ====================\nSELECT 2 FROM dual;\n```",
            "CHECK_01 | SELECT 2 FROM dual",
            "## CHECK_01 — Prova actualitzada\n### Què detecta\nNou contingut.\n### Validació posterior\nReexecutar.",
        )

        self.assertEqual(result["expl"], "OK")
        content = (self.root / FITXER_EXPL).read_text(encoding="utf-8")
        self.assertEqual(content.count("## CHECK_01"), 1)
        self.assertIn("Prova actualitzada", content)
        self.assertIn("## CHECK_02 — Altre", content)

    def test_sync_txt_restores_backup_when_write_fails(self):
        txt_path = self.root / FITXER_TXT
        txt_path.write_text("CHECK_01 | ORIGINAL\n", encoding="utf-8")
        service = QuerySyncService(self.root, str(self.db_path))
        original_write_text = Path.write_text

        def broken_write(path_obj, content, encoding=None, errors=None, newline=None):
            if Path(path_obj) == txt_path:
                original_write_text(path_obj, "CORRUPT\n", encoding=encoding, errors=errors, newline=newline)
                raise OSError("disk full")
            return original_write_text(path_obj, content, encoding=encoding, errors=errors, newline=newline)

        with patch("pathlib.Path.write_text", autospec=True, side_effect=broken_write):
            ok, err = service._sync_txt("CHECK_01", "CHECK_01 | UPDATED", txt_path)

        self.assertFalse(ok)
        self.assertIn("disk full", err)
        self.assertEqual(txt_path.read_text(encoding="utf-8"), "CHECK_01 | ORIGINAL\n")

    def test_sync_md_replaces_and_deduplicates_same_check_block(self):
        (self.root / FITXER_MD).write_text(
            "# Titol\n\n"
            "```sql\n-- ====================\n-- CHECK 01: antic\n-- ====================\nSELECT old FROM dual;\n```\n\n---\n\n"
            "```sql\n-- ====================\n-- CHECK 02: fix\n-- ====================\nSELECT 2 FROM dual;\n```\n\n---\n\n"
            "```sql\n-- ====================\n-- CHECK 01: duplicat\n-- ====================\nSELECT duplicate FROM dual;\n```\n",
            encoding="utf-8",
        )
        service = QuerySyncService(self.root, str(self.db_path))

        ok, err = service._sync_md(
            "CHECK_01",
            "```sql\n-- ====================\n-- CHECK 01: nou\n-- ====================\nSELECT fresh FROM dual;\n```",
            self.root / FITXER_MD,
        )

        self.assertTrue(ok, err)
        content = (self.root / FITXER_MD).read_text(encoding="utf-8")
        self.assertEqual(content.count("CHECK 01:"), 1)
        self.assertIn("SELECT fresh FROM dual;", content)
        self.assertIn("CHECK 02: fix", content)


if __name__ == "__main__":
    unittest.main()
