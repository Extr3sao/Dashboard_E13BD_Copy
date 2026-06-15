import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests

from fastapi.testclient import TestClient

from src.api import checks_admin_router
from src.api.main import app


class TestChecksAdminRouter(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "internal.db"
        self.previous_internal_db = os.environ.get("INTERNAL_DB_PATH")
        os.environ["INTERNAL_DB_PATH"] = str(self.db_path)
        self._create_legacy_db()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        if self.previous_internal_db is None:
            os.environ.pop("INTERNAL_DB_PATH", None)
        else:
            os.environ["INTERNAL_DB_PATH"] = self.previous_internal_db
        try:
            self.tmpdir.cleanup()
        except PermissionError:
            pass

    def _create_legacy_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE audit_checks (
                check_id TEXT PRIMARY KEY,
                titol TEXT NOT NULL,
                severitat_base TEXT NOT NULL,
                parametres TEXT,
                tipus TEXT NOT NULL DEFAULT 'SQL',
                ordre INTEGER NOT NULL DEFAULT 0,
                actiu INTEGER NOT NULL DEFAULT 1,
                context_check TEXT,
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
                es_vigent INTEGER NOT NULL DEFAULT 1
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
            "CREATE TABLE sincronitzacio_fitxers (id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT NOT NULL, fitxer TEXT NOT NULL, estat TEXT)"
        )
        conn.execute(
            """
            INSERT INTO audit_checks (
                check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, creat_en, actualitzat_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "2026-03-12T09:00:00",
                "2026-03-12T09:00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO consulta_versions (check_id, versio, sql_text, es_vigent)
            VALUES (?, ?, ?, ?)
            """,
            ("CHECK_01", 1, "SELECT 1 FROM dual", 1),
        )
        conn.commit()
        conn.close()

    def test_list_checks_autoupgrades_legacy_schema(self):
        response = self.client.get("/api/checks")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["check_id"], "CHECK_01")
        self.assertEqual(data[0]["ai_enabled"], 0)

        conn = sqlite3.connect(self.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_checks)").fetchall()}
        conn.close()
        self.assertIn("ai_enabled", columns)

    def test_list_checks_syncs_sqlite_catalog_from_markdown(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO audit_checks (
                check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, creat_en, actualitzat_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CHECK_13",
                "CHECK 13 SQLITE",
                "Mitjà",
                "days_back",
                "SQL",
                13,
                1,
                "sqlite only",
                "2026-03-12T09:00:00",
                "2026-03-12T09:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO consulta_versions (check_id, versio, sql_text, es_vigent) VALUES (?, ?, ?, ?)",
            ("CHECK_13", 1, "SELECT 13 FROM dual", 1),
        )
        conn.commit()
        conn.close()

        markdown_checks = [
            {
                "check_id": "CHECK_01",
                "check_number": 1,
                "title": "CHECK 01 DES DEL MD",
                "criteri": "context md 01",
                "severitat_base": "N/A",
                "sql": "SELECT 101 FROM dual",
            },
            {
                "check_id": "CHECK_11",
                "check_number": 11,
                "title": "CHECK 11 DES DEL MD",
                "criteri": "context md 11",
                "severitat_base": "Crític",
                "sql": "SELECT 111 FROM dual",
            },
        ]

        with patch("src.api.checks_admin_router.parse_post_crq_checks", return_value=markdown_checks):
            response = self.client.get("/api/checks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["check_id"] for item in data], ["CHECK_01", "CHECK_11"])
        self.assertEqual(data[0]["titol"], "CHECK 01 DES DEL MD")
        self.assertEqual(data[0]["severitat_base"], "Mitjà")
        self.assertEqual(data[0]["sql_vigent"], "SELECT 101 FROM dual")
        self.assertEqual(data[1]["titol"], "CHECK 11 DES DEL MD")

        conn = sqlite3.connect(self.db_path)
        self.assertEqual(
            conn.execute("SELECT actiu FROM audit_checks WHERE check_id = ?", ("CHECK_13",)).fetchone(),
            (0,),
        )
        self.assertEqual(
            conn.execute(
                "SELECT titol, context_check FROM audit_checks WHERE check_id = ?",
                ("CHECK_11",),
            ).fetchone(),
            ("CHECK 11 DES DEL MD", "context md 11"),
        )
        versions = conn.execute(
            "SELECT versio, sql_text, es_vigent FROM consulta_versions WHERE check_id = ? ORDER BY versio ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()
        self.assertEqual(versions[-1], (2, "SELECT 101 FROM dual", 1))

    def test_list_checks_preserves_unsynced_user_sql_override(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE audit_checks ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN checksum TEXT")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_per TEXT")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_en TEXT")
        conn.execute(
            "UPDATE consulta_versions SET checksum = ?, creat_per = 'markdown_sync', creat_en = ? WHERE check_id = ? AND versio = 1",
            ("old-checksum", "2026-03-12T09:00:00Z", "CHECK_01"),
        )
        conn.execute("UPDATE consulta_versions SET es_vigent = 0 WHERE check_id = ?", ("CHECK_01",))
        conn.execute(
            """INSERT INTO consulta_versions (check_id, versio, sql_text, checksum, creat_per, creat_en, es_vigent)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "CHECK_01",
                2,
                "SELECT changed FROM dual",
                "new-checksum",
                "usuari",
                "2026-04-09T12:01:35Z",
                1,
            ),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "auditoria_post_crq.md", "PENDENT"),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "consultes_post_crq.txt", "PENDENT"),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md", "PENDENT"),
        )
        conn.commit()
        conn.close()

        markdown_checks = [
            {
                "check_id": "CHECK_01",
                "check_number": 1,
                "title": "TAULES RECENTS SENSE PRIMARY KEY",
                "criteri": "context",
                "severitat_base": "Mitjà",
                "sql": "SELECT 1 FROM dual",
            }
        ]

        with patch("src.api.checks_admin_router.parse_post_crq_checks", return_value=markdown_checks):
            response = self.client.get("/api/checks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["versio_vigent"], 2)
        self.assertEqual(data[0]["sql_vigent"], "SELECT changed FROM dual")

        conn = sqlite3.connect(self.db_path)
        versions = conn.execute(
            "SELECT versio, creat_per, sql_text, es_vigent FROM consulta_versions WHERE check_id = ? ORDER BY versio ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()
        self.assertEqual(
            versions,
            [
                (1, "markdown_sync", "SELECT 1 FROM dual", 0),
                (2, "usuari", "SELECT changed FROM dual", 1),
            ],
        )

    def test_list_checks_returns_pending_for_current_version_without_explanation(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE audit_checks ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "INSERT INTO explicacions (check_id, consulta_version_id, estat, creat_en) VALUES (?, ?, ?, ?)",
            ("CHECK_01", 1, "OBSOLETA", "2026-04-10T09:00:00Z"),
        )
        conn.execute("UPDATE consulta_versions SET es_vigent = 0 WHERE check_id = ? AND versio = 1", ("CHECK_01",))
        conn.execute(
            "INSERT INTO consulta_versions (check_id, versio, sql_text, es_vigent) VALUES (?, ?, ?, ?)",
            ("CHECK_01", 2, "SELECT changed FROM dual", 1),
        )
        conn.commit()
        conn.close()

        with patch(
            "src.api.checks_admin_router.parse_post_crq_checks",
            return_value=[
                {
                    "check_id": "CHECK_01",
                    "check_number": 1,
                    "title": "TAULES RECENTS SENSE PRIMARY KEY",
                    "criteri": "context",
                    "severitat_base": "Mitjà",
                    "sql": "SELECT changed FROM dual",
                }
            ],
        ):
            response = self.client.get("/api/checks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["versio_vigent"], 2)
        self.assertEqual(data[0]["estat_explicacio"], "PENDENT")

    def test_list_checks_does_not_create_markdown_version_when_only_header_changes(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE audit_checks ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN checksum TEXT")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_per TEXT")
        conn.execute("ALTER TABLE consulta_versions ADD COLUMN creat_en TEXT")
        conn.execute(
            "UPDATE consulta_versions SET checksum = ?, creat_per = 'usuari', creat_en = ? WHERE check_id = ? AND versio = 1",
            (checks_admin_router._sql_version_checksum("SELECT 1 FROM dual"), "2026-04-09T12:01:35Z", "CHECK_01"),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "auditoria_post_crq.md", "OK"),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "consultes_post_crq.txt", "OK"),
        )
        conn.execute(
            "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)",
            ("CHECK_01", "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md", "OK"),
        )
        conn.commit()
        conn.close()

        markdown_checks = [
            {
                "check_id": "CHECK_01",
                "check_number": 1,
                "title": "TAULES RECENTS SENSE PRIMARY KEY",
                "criteri": "context",
                "severitat_base": "Mitjà",
                "sql": (
                    "-- ======================================\n"
                    "-- CHECK 01: TAULES RECENTS SENSE PRIMARY KEY\n"
                    "-- Criteri:\n"
                    "--   Context actualitzat\n"
                    "-- ======================================\n"
                    "SELECT 1 FROM dual"
                ),
            }
        ]

        with patch("src.api.checks_admin_router.parse_post_crq_checks", return_value=markdown_checks):
            response = self.client.get("/api/checks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["versio_vigent"], 1)

        conn = sqlite3.connect(self.db_path)
        versions = conn.execute(
            "SELECT versio, creat_per, es_vigent FROM consulta_versions WHERE check_id = ? ORDER BY versio ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()
        self.assertEqual(versions, [(1, "usuari", 1)])

    def test_delete_check_reorders_auxiliary_tables_and_files(self):
        root = Path(self.tmpdir.name)
        md_file = root / "auditoria_post_crq.md"
        txt_file = root / "consultes_post_crq.txt"
        md_file.write_text("### CHECK_01\nA\n### CHECK_02\nB\n### CHECK_03\nC\n", encoding="utf-8")
        txt_file.write_text("CHECK_01 | A\nCHECK_02 | B\nCHECK_03 | C\n", encoding="utf-8")

        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE audit_checks ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE TABLE regeneracio_log (id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT NOT NULL)")
        for idx in (2, 3):
            check_id = f"CHECK_{idx:02d}"
            conn.execute(
                """
                INSERT INTO audit_checks (
                    check_id, titol, severitat_base, parametres, tipus, ordre, actiu, context_check, creat_en, actualitzat_en, ai_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check_id,
                    check_id,
                    "Mitjà",
                    None,
                    "SQL",
                    idx,
                    1,
                    None,
                    "2026-03-12T09:00:00",
                    "2026-03-12T09:00:00",
                    0,
                ),
            )
            conn.execute("INSERT INTO consulta_versions (check_id, versio, sql_text, es_vigent) VALUES (?, ?, ?, ?)", (check_id, 1, f"SELECT {idx} FROM dual", 1))
            conn.execute("INSERT INTO explicacions (check_id, estat) VALUES (?, ?)", (check_id, "VIGENT"))
            conn.execute("INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat) VALUES (?, ?, ?)", (check_id, "auditoria_post_crq.md", "OK"))
            conn.execute("INSERT INTO regeneracio_log (check_id) VALUES (?)", (check_id,))
        conn.commit()
        conn.close()

        with patch("src.api.checks_admin_router._get_projecte_root", return_value=str(root)):
            response = self.client.delete("/api/checks/CHECK_01")

        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT check_id FROM audit_checks ORDER BY check_id").fetchall(), [("CHECK_01",), ("CHECK_02",)])
        self.assertEqual(conn.execute("SELECT check_id FROM consulta_versions ORDER BY check_id").fetchall(), [("CHECK_01",), ("CHECK_02",)])
        self.assertEqual(conn.execute("SELECT check_id FROM explicacions ORDER BY check_id").fetchall(), [("CHECK_01",), ("CHECK_02",)])
        self.assertEqual(conn.execute("SELECT check_id FROM sincronitzacio_fitxers ORDER BY check_id").fetchall(), [("CHECK_01",), ("CHECK_02",)])
        self.assertEqual(conn.execute("SELECT check_id FROM regeneracio_log ORDER BY check_id").fetchall(), [("CHECK_01",), ("CHECK_02",)])
        conn.close()
        self.assertNotIn("CHECK_03", md_file.read_text(encoding="utf-8"))
        self.assertNotIn("CHECK_03", txt_file.read_text(encoding="utf-8"))

    def test_delete_check_rolls_back_database_if_file_write_fails(self):
        root = Path(self.tmpdir.name)
        md_file = root / "auditoria_post_crq.md"
        txt_file = root / "consultes_post_crq.txt"
        md_file.write_text("### CHECK_01\nA\n", encoding="utf-8")
        txt_file.write_text("CHECK_01 | A\n", encoding="utf-8")

        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("src.api.checks_admin_router._get_projecte_root", return_value=str(root)), patch("os.replace", side_effect=OSError("disk full")):
                response = client.delete("/api/checks/CHECK_01")

        self.assertEqual(response.status_code, 500)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT check_id FROM audit_checks").fetchall(), [("CHECK_01",)])
        self.assertEqual(conn.execute("SELECT check_id FROM consulta_versions").fetchall(), [("CHECK_01",)])
        conn.close()

    def test_regenerate_explanation_marks_same_version_as_error_if_sync_fails(self):
        fake_response = SimpleNamespace(
            resum_executiu="Resum",
            explicacio_funcional="Funcional",
            explicacio_tecnica="Tècnica",
            impacte="Impacte",
            riscos="Riscos",
            canvis_respecte_anterior="Canvis",
            recomanacio_revisio="Revisió",
            nivell_confianca=0.8,
            advertiments="Cap",
            model_utilitzat="fake-model",
            bloc_auditoria_md="### CHECK_01\nbloc",
            linia_consultes_txt="CHECK_01 | bloc",
        )

        with patch("src.api.checks_admin_router.DBAQueryExplainer") as explainer_cls, patch(
            "src.api.checks_admin_router.QuerySyncService.sync_check",
            side_effect=RuntimeError("sync_failed"),
        ):
            explainer_cls.return_value.explain.return_value = fake_response
            checks_admin_router._regenerate_explanation("CHECK_01", 1)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT consulta_version_id, estat, error_missatge FROM explicacions WHERE check_id = ? ORDER BY id ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], (1, "ERROR", "sync_failed"))

    def test_regenerate_explanation_marks_error_when_sync_returns_errors(self):
        fake_response = SimpleNamespace(
            resum_executiu="Resum",
            explicacio_funcional="Funcional",
            explicacio_tecnica="Tècnica",
            impacte="Impacte",
            riscos="Riscos",
            canvis_respecte_anterior="Canvis",
            recomanacio_revisio="Revisió",
            nivell_confianca=0.8,
            advertiments="Cap",
            model_utilitzat="fake-model",
            bloc_auditoria_md="### CHECK_01\nbloc",
            linia_consultes_txt="CHECK_01 | bloc",
            explicacio_check_text="## CHECK_01 — Prova\n### Què detecta\nBloc",
        )

        with patch("src.api.checks_admin_router.DBAQueryExplainer") as explainer_cls, patch(
            "src.api.checks_admin_router.QuerySyncService.sync_check",
            return_value={"md": "OK", "txt": "OK", "expl": "ERROR", "errors": ["EXPL: write failed"]},
        ):
            explainer_cls.return_value.explain.return_value = fake_response
            checks_admin_router._regenerate_explanation("CHECK_01", 1)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT consulta_version_id, estat, error_missatge FROM explicacions WHERE check_id = ? ORDER BY id ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], (1, "ERROR", "EXPL: write failed"))

    def test_regenerate_explanation_persists_error_when_version_is_missing(self):
        checks_admin_router._regenerate_explanation("CHECK_01", 999)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT consulta_version_id, estat, error_missatge FROM explicacions WHERE check_id = ? ORDER BY id ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 999)
        self.assertEqual(rows[0][1], "ERROR")
        self.assertIn("CHECK_01 / 999", rows[0][2])

    def test_regenerate_explanation_persists_error_when_explainer_fails(self):
        with patch("src.api.checks_admin_router.DBAQueryExplainer") as explainer_cls:
            explainer_cls.return_value.explain.side_effect = RuntimeError("ai_failed")
            checks_admin_router._regenerate_explanation("CHECK_01", 1)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT consulta_version_id, estat, error_missatge FROM explicacions WHERE check_id = ? ORDER BY id ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], (1, "ERROR", "ai_failed"))

    def test_regenerate_explanation_marks_sync_status_error_when_request_fails(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE sincronitzacio_fitxers ADD COLUMN darrera_sync TEXT")
        conn.execute("ALTER TABLE sincronitzacio_fitxers ADD COLUMN error_missatge TEXT")
        conn.commit()
        conn.close()

        with patch("src.api.checks_admin_router.DBAQueryExplainer") as explainer_cls:
            explainer_cls.return_value.explain.side_effect = requests.exceptions.ChunkedEncodingError("Response ended prematurely")
            checks_admin_router._regenerate_explanation("CHECK_01", 1)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT fitxer, estat, error_missatge FROM sincronitzacio_fitxers WHERE check_id = ? ORDER BY fitxer ASC",
            ("CHECK_01",),
        ).fetchall()
        conn.close()

        self.assertEqual(
            rows,
            [
                ("EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md", "ERROR", "Response ended prematurely"),
                ("auditoria_post_crq.md", "ERROR", "Response ended prematurely"),
                ("consultes_post_crq.txt", "ERROR", "Response ended prematurely"),
            ],
        )

    def test_validate_preview_executes_check_and_returns_ai_preview(self):
        validation_payload = {
            "status": "ok",
            "row_count": 2,
            "columns": ["ESQUEMA", "FECHA_MODIF"],
            "rows": [
                {"ESQUEMA": "APP", "FECHA_MODIF": "2026-04-09 10:00"},
                {"ESQUEMA": "APP_AUX", "FECHA_MODIF": "2026-04-09 11:00"},
            ],
            "duration_ms": 42,
            "rendered_sql": "SELECT * FROM demo",
            "time_filter_pushed": True,
        }
        ai_preview = {
            "status": "ok",
            "model_utilitzat": "fake-model",
            "resum_executiu": "Resum extens de prova.",
            "explicacio_funcional": "Explicació funcional de prova.",
            "explicacio_tecnica": "Explicació tècnica de prova prou llarga.",
            "impacte": "Impacte",
            "riscos": "Riscos",
            "canvis_respecte_anterior": None,
            "recomanacio_revisio": "Revisió",
            "nivell_confianca": 0.81,
            "advertiments": None,
            "bloc_auditoria_md": "-- CHECK 01",
            "linia_consultes_txt": "CHECK_01 | prova",
            "explicacio_check_text": "## CHECK_01",
        }

        with patch("src.api.checks_admin_router._resolve_oracle_profile", return_value=("E13DB", {"USER": "u"})), patch(
            "src.api.checks_admin_router._run_single_post_crq_check",
            return_value=validation_payload,
        ), patch(
            "src.api.checks_admin_router._preview_ai_explanation",
            return_value=ai_preview,
        ):
            response = self.client.post(
                "/api/checks/validate-preview",
                json={
                    "check_id": "CHECK_01",
                    "titol": "TAULES RECENTS SENSE PRIMARY KEY",
                    "severitat_base": "Mitjà",
                    "sql_text": "SELECT 1 FROM dual",
                    "parametres": "days_back",
                    "tipus": "SQL",
                    "context_check": "context",
                    "profile": "E13DB",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["profile"], "E13DB")
        self.assertEqual(body["validation"]["row_count"], 2)
        self.assertEqual(body["validation"]["preview_row_count"], 2)
        self.assertEqual(body["ai_preview"]["model_utilitzat"], "fake-model")

    def test_validate_preview_accepts_explicit_validation_window(self):
        validation_payload = {
            "status": "ok",
            "row_count": 0,
            "columns": ["ESQUEMA"],
            "rows": [],
            "duration_ms": 5,
            "rendered_sql": "SELECT 1 FROM dual",
            "time_filter_pushed": True,
        }

        with patch("src.api.checks_admin_router._resolve_oracle_profile", return_value=("E13DB", {"USER": "u"})), patch(
            "src.api.checks_admin_router._preview_ai_explanation",
            return_value={"status": "ok", "model_utilitzat": "fake-model"},
        ), patch(
            "src.api.checks_admin_router._run_single_post_crq_check",
            return_value=validation_payload,
        ) as run_single:
            response = self.client.post(
                "/api/checks/validate-preview",
                json={
                    "check_id": "CHECK_01",
                    "titol": "TAULES RECENTS SENSE PRIMARY KEY",
                    "severitat_base": "MitjÃ ",
                    "sql_text": "SELECT 1 FROM dual",
                    "parametres": "START_AT, END_AT",
                    "tipus": "SQL",
                    "context_check": "context",
                    "profile": "E13DB",
                    "validation_start_at": "2026-04-10T08:15",
                    "validation_end_at": "2026-04-11T09:45",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["time_filter"]["range_start_at"], "2026-04-10T08:15")
        self.assertEqual(response.json()["time_filter"]["range_end_at"], "2026-04-11T09:45")
        self.assertEqual(run_single.call_args.kwargs["days_back"], 2)
        self.assertEqual(run_single.call_args.kwargs["normalized_filter"]["range_start_at"], "2026-04-10T08:15")
        self.assertEqual(run_single.call_args.kwargs["normalized_filter"]["range_end_at"], "2026-04-11T09:45")

    def test_validate_preview_returns_error_without_ai_when_oracle_validation_fails(self):
        with patch("src.api.checks_admin_router._resolve_oracle_profile", return_value=("E13DB", {"USER": "u"})), patch(
            "src.api.checks_admin_router._run_single_post_crq_check",
            return_value={
                "status": "error",
                "error": 'ORA-00904: "POST_CRQ_RESULT"."START_DATE": invalid identifier',
                "rows": [],
                "columns": [],
                "rendered_sql": "SELECT * FROM broken",
            },
        ), patch("src.api.checks_admin_router._preview_ai_explanation") as ai_preview:
            response = self.client.post(
                "/api/checks/validate-preview",
                json={
                    "check_id": "CHECK_01",
                    "titol": "TAULES RECENTS SENSE PRIMARY KEY",
                    "severitat_base": "Mitjà",
                    "sql_text": "SELECT broken FROM dual",
                    "parametres": "days_back",
                    "tipus": "SQL",
                    "context_check": "context",
                    "profile": "E13DB",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["ai_preview"]["status"], "skipped")
        ai_preview.assert_not_called()

    def test_record_regeneration_error_logs_when_persistence_fails(self):
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("db locked")):
            with self.assertLogs("src.api.checks_admin_router", level="WARNING") as captured:
                checks_admin_router._record_regeneration_error(
                    str(self.db_path),
                    check_id="CHECK_01",
                    version_id=1,
                    error_message="boom",
                )

        self.assertTrue(any("persistir l'error de regener" in message for message in captured.output))

    def test_codex_engine_execute_left_prepares_sql_developer_query_and_binds_variables(self):
        executed = {}

        class FakeOracleDBManager:
            def __init__(self, _config):
                self.last_error = None

            def execute_query(self, query, params=None):
                executed["query"] = query
                executed["params"] = params or {}
                return [("APP",)], ["ESQUEMA"]

            def close(self):
                return None

        sql = """
DEFINE START_AT = '2026-04-09 11:42:00'

SELECT owner AS ESQUEMA
FROM dba_objects
WHERE last_ddl_time > TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')
"""

        with patch("src.api.checks_admin_router._resolve_oracle_profile", return_value=("E13DB", {"USER": "u"})), patch(
            "src.api.checks_admin_router.OracleDBManager",
            FakeOracleDBManager,
        ):
            response = self.client.post(
                "/api/checks/codex-engine/execute",
                json={
                    "sql_text": sql,
                    "side": "left",
                    "profile": "E13DB",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["result"]
        self.assertTrue(body["success"])
        self.assertEqual(body["row_count"], 1)
        self.assertEqual(body["variables_used"]["START_AT"], "2026-04-09 11:42:00")
        self.assertNotIn("DEFINE START_AT", body["prepared_sql"])
        self.assertIn("TO_DATE(:START_AT", body["executed_sql"])
        self.assertEqual(executed["params"]["START_AT"], "2026-04-09 11:42:00")

    def test_codex_engine_compare_detects_same_content_with_different_order(self):
        class FakeOracleDBManager:
            def __init__(self, _config):
                self.last_error = None

            def execute_query(self, query, params=None):
                if "LEFT_QUERY" in query:
                    return [(1,), (2,)], ["ID"]
                return [(2,), (1,)], ["ID"]

            def close(self):
                return None

        with patch("src.api.checks_admin_router._resolve_oracle_profile", return_value=("E13DB", {"USER": "u"})), patch(
            "src.api.checks_admin_router.OracleDBManager",
            FakeOracleDBManager,
        ):
            response = self.client.post(
                "/api/checks/codex-engine/compare",
                json={
                    "left_sql": "SELECT 1 AS LEFT_QUERY FROM dual",
                    "right_sql": "SELECT 1 AS RIGHT_QUERY FROM dual",
                    "profile": "E13DB",
                    "options": {
                        "ignore_row_order": False,
                        "preview_limit": 100,
                        "sample_limit": 10,
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["comparison"]["content_match"])
        self.assertFalse(body["comparison"]["order_match"])
        self.assertEqual(body["comparison"]["status"], "warning")
        self.assertFalse(body["comparison"]["match"])

    def test_codex_engine_analyze_returns_structured_ai_payload(self):
        with patch(
            "src.api.checks_admin_router.AIAssistant.generate_response",
            return_value='{"summary":"El orden cambia","possible_causes":["ORDER BY distinto"],"recommendation":"Ignorar orden o alinearlo"}',
        ):
            response = self.client.post(
                "/api/checks/codex-engine/analyze",
                json={
                    "left_sql": "SELECT * FROM dual",
                    "right_sql": "SELECT * FROM dual",
                    "left": {
                        "success": True,
                        "row_count": 1,
                        "columns": ["ID"],
                        "rows": [{"ID": 1}],
                    },
                    "right": {
                        "success": True,
                        "row_count": 1,
                        "columns": ["ID"],
                        "rows": [{"ID": 1}],
                    },
                    "comparison": {
                        "status": "warning",
                        "summary": "Los resultados contienen los mismos datos pero en distinto orden.",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["ai_analysis"]
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["summary"], "El orden cambia")
        self.assertEqual(body["possible_causes"], ["ORDER BY distinto"])
