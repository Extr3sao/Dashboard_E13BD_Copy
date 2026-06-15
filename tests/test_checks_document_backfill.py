import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.core.checks_document_backfill import backfill_check_states_from_documents


class TestChecksDocumentBackfill(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.db_path = self.root / "internal.db"
        self.md_path = self.root / "auditoria_post_crq.md"
        self.txt_path = self.root / "consultes_post_crq.txt"
        self.expl_path = self.root / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"
        self._create_db()
        self._create_docs()

    def tearDown(self):
        try:
            self.tmpdir.cleanup()
        except PermissionError:
            pass

    def _create_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE audit_checks (
                    check_id TEXT PRIMARY KEY,
                    titol TEXT NOT NULL,
                    severitat_base TEXT NOT NULL,
                    parametres TEXT,
                    tipus TEXT NOT NULL,
                    ordre INTEGER NOT NULL,
                    actiu INTEGER NOT NULL,
                    context_check TEXT,
                    ai_enabled INTEGER NOT NULL DEFAULT 0,
                    creat_en TEXT NOT NULL,
                    actualitzat_en TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE consulta_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    versio INTEGER NOT NULL,
                    sql_text TEXT NOT NULL,
                    checksum TEXT,
                    creat_per TEXT,
                    creat_en TEXT,
                    es_vigent INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE explicacions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    consulta_version_id INTEGER,
                    resum_executiu TEXT,
                    explicacio_funcional TEXT,
                    explicacio_tecnica TEXT,
                    impacte TEXT,
                    riscos TEXT,
                    canvis_respecte_anterior TEXT,
                    recomanacio_revisio TEXT,
                    nivell_confianca REAL,
                    advertiments TEXT,
                    model_utilitzat TEXT,
                    estat TEXT,
                    error_missatge TEXT,
                    creat_en TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE sincronitzacio_fitxers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    fitxer TEXT NOT NULL,
                    estat TEXT,
                    darrera_sync TEXT,
                    error_missatge TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO audit_checks (
                    check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, ai_enabled, creat_en, actualitzat_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "CHECK_01",
                    "TAULES RECENTS SENSE PRIMARY KEY",
                    "Mitjà",
                    "days_back",
                    "SQL",
                    1,
                    1,
                    "context",
                    0,
                    "2026-04-01T10:00:00",
                    "2026-04-01T10:00:00",
                ),
            )
            conn.execute(
                "INSERT INTO consulta_versions (check_id, versio, sql_text, checksum, creat_per, creat_en, es_vigent) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("CHECK_01", 1, "-- CHECK 01\nSELECT 1 FROM dual", "x", "test", "2026-04-01T10:00:00", 1),
            )
            conn.execute(
                "INSERT INTO explicacions (check_id, consulta_version_id, estat, model_utilitzat) VALUES (?, ?, ?, ?)",
                ("CHECK_01", 1, "OBSOLETA", "old"),
            )
            conn.commit()

    def _create_docs(self):
        self.md_path.write_text(
            """```sql
-- =============================================================================
-- CHECK 01: TAULES RECENTS SENSE PRIMARY KEY
-- Severitat: MITJÀ
-- Criteri:
--   Només taules recents
-- =============================================================================
SELECT 1 FROM dual
```
""",
            encoding="utf-8",
        )
        self.txt_path.write_text(
            "CHECK_01 | TAULES RECENTS SENSE PRIMARY KEY | severitat base: Mitjà | paràmetres: days_back\n",
            encoding="utf-8",
        )
        self.expl_path.write_text(
            """# Catàleg

## CHECK_01 — Taules recents sense primary key
### Què detecta
Detecta taules recents sense clau primària.
### Per què és important
És important per la integritat.
### Impacte sobre el lot
Pot provocar duplicats.
### Com s'ha de revisar
Revisar el model i les constraints.
### Com es pot corregir
Crear la primary key adequada.
### Limitacions o falsos positius
Pot afectar taules temporals.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Taula
### Validació posterior
Reexecutar el check.
""",
            encoding="utf-8",
        )

    def test_backfill_marks_existing_documents_as_vigent_and_ok(self):
        stats = backfill_check_states_from_documents(
            db_path=str(self.db_path),
            markdown_path=str(self.md_path),
            txt_path=str(self.txt_path),
            explanation_path=str(self.expl_path),
        )

        self.assertEqual(stats["checks_seen"], 1)
        self.assertEqual(stats["explanations_upserted"], 1)
        self.assertEqual(stats["sync_rows_updated"], 3)
        self.assertEqual(stats["txt_lines_repaired"], 0)

        with sqlite3.connect(self.db_path) as conn:
            explanation = conn.execute(
                "SELECT estat, model_utilitzat, explicacio_funcional, impacte FROM explicacions WHERE check_id = ? ORDER BY id DESC LIMIT 1",
                ("CHECK_01",),
            ).fetchone()
            sync_rows = conn.execute(
                "SELECT fitxer, estat FROM sincronitzacio_fitxers WHERE check_id = ? ORDER BY fitxer",
                ("CHECK_01",),
            ).fetchall()

        self.assertEqual(explanation[0], "VIGENT")
        self.assertEqual(explanation[1], "backfill-existing-docs")
        self.assertIn("Detecta taules recents", explanation[2])
        self.assertIn("duplicats", explanation[3])
        self.assertEqual(
            sync_rows,
            [
                ("EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md", "OK"),
                ("auditoria_post_crq.md", "OK"),
                ("consultes_post_crq.txt", "OK"),
            ],
        )

    def test_backfill_repairs_missing_txt_line(self):
        self.txt_path.write_text("", encoding="utf-8")

        stats = backfill_check_states_from_documents(
            db_path=str(self.db_path),
            markdown_path=str(self.md_path),
            txt_path=str(self.txt_path),
            explanation_path=str(self.expl_path),
        )

        self.assertEqual(stats["txt_lines_repaired"], 1)
        self.assertIn("CHECK_01 | TAULES RECENTS SENSE PRIMARY KEY", self.txt_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
