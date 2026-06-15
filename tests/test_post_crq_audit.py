import io
import sqlite3
import tempfile
import unittest
from pypdf import PdfReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

from src.api.post_crq_audit import (
    _build_wrapped_sql,
    _days_back_from_filter,
    _display_period_label,
    _display_period_window,
    _parse_iso_dt,
    _sql_with_binds,
    _check_number_from_id,
    build_post_crq_pdf_report,
    _report_model_parameters_rows_v2,
    _sort_check_dicts,
    _build_incident_objects_table_rows_v6,
    safe_pdf_markup_paragraph,
    build_post_crq_markdown_report,
    parse_post_crq_checks,
    run_post_crq_audit,
)


class MockPostCrqDBManager:
    def __init__(self):
        self.last_error = None

    def execute_query(self, query, params=None):
        params = params or {}
        if "BETWEEN :START_DATE AND :END_DATE" in query:
            self.last_error = "ORA-00932: inconsistent datatypes: expected DATE got NUMBER"
            return None, None
        uses_days_back = ":days_back" in query
        uses_date_window = (
            ":start_date" in query
            and ":end_date" in query
            and bool(params.get("start_date"))
            and bool(params.get("end_date"))
        )
        if not uses_days_back and not uses_date_window:
            self.last_error = "missing_days_back_bind"
            return None, None

        columns = ["ESQUEMA", "TAULA", "DATA_MODIFICACIO_OBJECTE"]
        rows = [
            ("APP_USER", "TMP_ALPHA", "2026-03-06 10:00"),
            ("CORE_DB", "TMP_BETA", "2026-02-01 08:00"),
        ]
        return rows, columns


class FailingPostCrqDBManager:
    def __init__(self):
        self.last_error = "simulated_post_crq_failure"

    def execute_query(self, query, params=None):
        self.last_error = "simulated_post_crq_failure"
        return None, None


class NoSchemaPostCrqDBManager:
    def __init__(self):
        self.last_error = None

    def execute_query(self, query, params=None):
        columns = ["TAULA", "DATA_MODIFICACIO_OBJECTE"]
        rows = [
            ("TMP_ALPHA", "2026-03-06 10:00"),
        ]
        return rows, columns


class TestPostCrqAudit(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        self.ownership_db_path = handle.name
        with sqlite3.connect(self.ownership_db_path) as connection:
            connection.execute("CREATE TABLE schema_lots (schema_name TEXT PRIMARY KEY, lot_name TEXT NOT NULL)")
            connection.execute("INSERT INTO schema_lots(schema_name, lot_name) VALUES ('APP_USER', 'LOT_APP')")
            connection.commit()

    def test_parse_checks_from_markdown(self):
        checks = parse_post_crq_checks()

        self.assertGreaterEqual(len(checks), 11)
        self.assertEqual(checks[0]["check_id"], "CHECK_01")
        self.assertIn("PRIMARY KEY", checks[0]["title"])
        self.assertTrue(checks[0]["sql"].startswith("--"))
        self.assertIn("AS num_rows", checks[0]["sql"])
        self.assertNotIn("AS num_files", checks[0]["sql"])
        check_03 = next(item for item in checks if item["check_id"] == "CHECK_03")
        self.assertIn("increment_by_value", check_03["sql"])
        self.assertNotIn(" AS increment,", check_03["sql"])
        check_11 = next(item for item in checks if item["check_id"] == "CHECK_11")
        self.assertEqual(check_11["id"], "CHECK_11")
        self.assertEqual(check_11["name"], check_11["title"])
        self.assertEqual(check_11["severitat_base"], "ALT / BAIX (segons patró)")
        self.assertIn("days_back", check_11["parametres_admesos"])

    def test_run_post_crq_filters_by_schema_and_range(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01", "CHECK_02"],
            schemas=["APP_USER"],
            time_filter={"mode": "range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        self.assertEqual(report["audit_type"], "post_crq")
        self.assertEqual(report["summary"]["selected_checks"], 2)
        self.assertEqual(report["summary"]["total_findings"], 2)
        self.assertEqual(report["context"]["schemas"], ["APP_USER"])
        self.assertEqual(report["results_by_check"][0]["row_count"], 1)
        self.assertEqual(report["results_by_check"][0]["rows"][0]["ESQUEMA"], "APP_USER")
        self.assertEqual(report["results_by_check"][0]["rows"][0]["Lot"], "LOT_APP")
        self.assertEqual(report["summary"]["schemas_with_detected_changes"], 1)
        self.assertEqual(report["summary"]["latest_change_at"], "2026-03-06 10:00")
        self.assertEqual(report["summary"]["detected_time_range"]["start_at"], "2026-03-06 10:00")
        self.assertEqual(report["summary"]["detected_time_range"]["end_at"], "2026-03-06 10:00")
        self.assertEqual(report["results_by_check"][0]["criticitat"], "Mitjà")
        self.assertEqual(report["schema_last_modifications"][0]["schema"], "APP_USER")
        self.assertEqual(report["schema_last_modifications"][0]["source_check"], "CHECK_02")
        self.assertIn("query_export", report)
        self.assertIn("CHECK_01", report["query_export"]["content"])
        self.assertIn("Font de consultes", report["query_export"]["content"])
        self.assertIn("duration_ms", report["executed_checks"][0])
        self.assertIn("source_path", report["context"])
        self.assertTrue(str(report["context"]["generated_at"]).endswith("Z"))
        self.assertTrue(str(report["context"]["time_filter"]["resolved_at"]).endswith("Z"))
        self.assertIn("report_model", report)
        self.assertIn("agent_runtime", report)
        self.assertEqual(report["finding_envelopes"][0]["lot_assignment"]["lot"], "LOT_APP")
        self.assertIn("scheduler", report["summary"])
        self.assertIn("scheduler", report["context"])
        self.assertEqual(report["executed_checks"][0]["query_category"], "light")
        self.assertFalse(report["executed_checks"][0]["time_filter_pushed"])
        self.assertNotIn('post_crq_result."DATA_MODIFICACIO_OBJECTE" BETWEEN TO_DATE(:start_date', report["results_by_check"][0]["executed_sql"])
        self.assertIn("lot_incident_groups", report["report_model"])
        first_object = report["report_model"]["lot_incident_groups"][0]["schemas"][0]["objectes"][0]
        self.assertIn("OBJECTE", first_object)
        self.assertIn("TIPUS", first_object)
        self.assertIn("DADA TÈCNICA", first_object)
        self.assertNotIn("severitat", first_object)

    def test_range_time_filter_preserves_explicit_hours_for_window_display(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01"],
            schemas=["APP_USER"],
            time_filter={"mode": "range", "start_date": "2026-03-24T09:30", "end_date": "2026-03-25T08:30"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        normalized = report["context"]["time_filter"]
        self.assertEqual(normalized["start_date"], "2026-03-24")
        self.assertEqual(normalized["end_date"], "2026-03-25")
        self.assertEqual(normalized["range_start_at"], "2026-03-24T09:30")
        self.assertEqual(normalized["range_end_at"], "2026-03-25T08:30")
        self.assertEqual(_display_period_label(normalized), "24/03/2026 09:30 - 25/03/2026 08:30")
        self.assertEqual(_display_period_window(normalized), "24/03/2026 09:30 - 25/03/2026 08:30")

    def test_build_post_crq_pdf_report_preserves_explicit_hours_in_cover(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01"],
            schemas=["APP_USER"],
            time_filter={"mode": "range", "start_date": "2026-04-07T17:30", "end_date": "2026-04-08T17:30"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        pdf_bytes = build_post_crq_pdf_report("E13DB", report)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_text = reader.pages[0].extract_text() or ""

        self.assertIn("07/04/2026 17:30 - 08/04/2026 17:30", cover_text)
        self.assertNotIn("00:00h - 23:59h", cover_text)

    def test_run_post_crq_uses_internal_db_path_by_default_for_schema_lots(self):
        from unittest.mock import patch

        with patch("src.api.post_crq_audit.resolve_sqlite_path", return_value=self.ownership_db_path):
            report = run_post_crq_audit(
                db_manager=MockPostCrqDBManager(),
                selected_checks=["CHECK_01"],
                schemas=["APP_USER"],
                time_filter={"mode": "preset", "preset": "weekly"},
                profile="E13DB",
            )

        self.assertEqual(report["results_by_check"][0]["rows"][0]["Lot"], "LOT_APP")
        self.assertEqual(report["finding_envelopes"][0]["lot_assignment"]["lot"], "LOT_APP")

    def test_run_post_crq_collects_partial_errors(self):
        report = run_post_crq_audit(
            db_manager=FailingPostCrqDBManager(),
            selected_checks=["CHECK_01"],
            schemas=[],
            time_filter={"mode": "preset", "preset": "weekly"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        self.assertEqual(report["summary"]["checks_with_errors"], 1)
        self.assertEqual(report["executed_checks"][0]["status"], "error")
        self.assertTrue(report["errors"])
        self.assertEqual(report["summary"]["environment_message"], "Corregir urgentment!!!")
        self.assertTrue(report["finding_envelopes"])
        self.assertEqual(report["summary"]["scheduler"]["configured_max_concurrency"], 1)

    def test_run_post_crq_logs_warning_when_check_execution_fails(self):
        from unittest.mock import patch

        with patch("src.api.post_crq_audit.logger.warning") as warning:
            report = run_post_crq_audit(
                db_manager=FailingPostCrqDBManager(),
                selected_checks=["CHECK_01"],
                schemas=[],
                time_filter={"mode": "preset", "preset": "weekly"},
                profile="E13DB",
                ownership_db_path=self.ownership_db_path,
            )

        self.assertEqual(report["results_by_check"][0]["status"], "error")
        self.assertTrue(any(call.args and call.args[0] == "Post-CRQ check execution failed" for call in warning.call_args_list))

    def test_run_post_crq_applies_criticality_overrides_to_any_selected_check(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01", "CHECK_03", "CHECK_04"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "daily"},
            profile="E13BDA",
            criticality_overrides={"CHECK_01": "CRITIC", "CHECK_03": "BAIX", "CHECK_04": "MITJA"},
            ownership_db_path=self.ownership_db_path,
        )

        by_id = {item["check_id"]: item for item in report["executed_checks"]}
        self.assertEqual(by_id["CHECK_01"]["criticitat"], "Crític")
        self.assertEqual(by_id["CHECK_03"]["criticitat"], "Baix")
        self.assertEqual(by_id["CHECK_04"]["criticitat"], "Mitjà")
        self.assertEqual(report["summary"]["environment_message"], "No es pot pujar aquest canvi a PRO.")
        self.assertEqual(report["criticality_overrides"]["CHECK_01"], "Crític")
        self.assertEqual(report["criticality_overrides"]["CHECK_03"], "Baix")
        self.assertEqual(report["criticality_overrides"]["CHECK_04"], "Mitjà")

    def test_run_post_crq_orders_results_by_criticality(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_02", "CHECK_01"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "daily"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        ordered_ids = [item["check_id"] for item in report["results_by_check"]]
        self.assertEqual(ordered_ids, ["CHECK_02", "CHECK_01"])
        section_keys = [item["criticality_key"] for item in report["summary"]["criticality_sections"]]
        self.assertEqual(section_keys, ["CRITIC", "MITJA", "BAIX"])
        self.assertIn("critical_incident_cards", report["report_model"])
        self.assertIn("execution_parameters", report["report_model"])
        self.assertIn("enabled_checks", report["report_model"])
        self.assertIn("lot_summary", report["report_model"])
        self.assertIn("critical_checks_grouped", report["report_model"])
        self.assertIn("detail_sections", report["report_model"])
        self.assertIn("final_observations", report["report_model"])

    def test_failed_check_generates_dba_diagnostic_for_ora_00923(self):
        class Ora923DBManager:
            def __init__(self):
                self.last_error = "ORA-00923: FROM keyword not found where expected"

            def execute_query(self, query, params=None):
                self.last_error = "ORA-00923: FROM keyword not found where expected"
                return None, None

        report = run_post_crq_audit(
            db_manager=Ora923DBManager(),
            selected_checks=["CHECK_11"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "daily"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        finding = report["finding_envelopes"][0]
        diagnostic = finding["dba_enrichment"]["sql_diagnostic"]
        self.assertEqual(diagnostic["oracle_error_code"], "ORA-00923")
        self.assertIn("FROM", diagnostic["oracle_error_summary"])
        self.assertEqual(diagnostic["patch_proposal"]["target_file"], "auditoria_post_crq.md")

    def test_build_markdown_report_for_post_crq(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "weekly"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        text = build_post_crq_markdown_report("E13DB", report)
        self.assertIn("Informe d'auditoria post-CRQ", text)
        self.assertIn("## 1. Índex", text)
        self.assertIn("## 2. Context de l'auditoria", text)
        self.assertIn("## 3. Resum executiu post-CRQ", text)
        self.assertIn("## 4. Incidències prioritzades per criticitat i lot", text)
        self.assertIn("## 5. Resultat detallat per check", text)
        self.assertIn("Annex A", text)
        self.assertTrue(report["report_options"]["include_annex"])
        self.assertIn("Checks inclosos en l'informe", text)
        self.assertIn("LOT_APP", text)
        self.assertIn("APP_USER", text)
        self.assertNotIn("Mostrant", text)
        self.assertNotIn("Responsable No informat", text)

    def test_wrapped_sql_uses_date_only_binds_for_time_pushdown(self):
        _days_back, normalized = _days_back_from_filter(
            {"mode": "range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        sql, binds, _schema_alias, temporal_alias, _schema_pushed, time_pushed = _build_wrapped_sql(
            'SELECT OWNER AS ESQUEMA, LAST_DDL_TIME AS DATA_MODIFICACIO_OBJECTE FROM DBA_OBJECTS',
            normalized,
            ["APP_USER"],
            {"days_back": 7},
        )

        self.assertTrue(time_pushed)
        self.assertEqual(temporal_alias, "DATA_MODIFICACIO_OBJECTE")
        self.assertEqual(binds["start_date"], "2026-03-01")
        self.assertEqual(binds["end_date"], "2026-03-07")
        self.assertIn("TO_DATE(:start_date, 'YYYY-MM-DD')", sql)
        self.assertIn("TO_DATE(:end_date, 'YYYY-MM-DD')", sql)

    def test_sql_with_binds_preserves_to_date_contract_for_check_01(self):
        checks = parse_post_crq_checks()
        check_01 = next(item for item in checks if item["check_id"] == "CHECK_01")

        sql = _sql_with_binds(check_01["sql"])

        self.assertIn("TO_DATE(:start_date, 'YYYY-MM-DD')", sql)
        self.assertIn("TO_DATE(:end_date", sql)
        self.assertIn("'YYYY-MM-DD') + 1", sql)
        self.assertNotIn("BETWEEN :START_DATE AND :END_DATE", sql)

    def test_parsed_checks_do_not_leave_dangling_select_comma_before_from(self):
        checks = parse_post_crq_checks()

        for check in checks:
            sql = _sql_with_binds(check["sql"])
            self.assertNotRegex(
                sql,
                r",\s*\nFROM\b",
                msg=f"{check['check_id']} still leaves a dangling comma before FROM",
            )

    def test_check_number_from_id_orders_numeric_suffix(self):
        self.assertLess(_check_number_from_id("CHECK_02"), _check_number_from_id("CHECK_10"))
        self.assertEqual(_check_number_from_id("CHECK_X"), 999)

    def test_sort_check_dicts_orders_numeric_suffix(self):
        records = [{"check_id": "CHECK_10"}, {"check_id": "CHECK_02"}, {"check_id": None}]
        sorted_records = _sort_check_dicts(records)
        self.assertEqual([item["check_id"] for item in sorted_records], ["CHECK_02", "CHECK_10", None])

    def test_parse_iso_dt_returns_none_for_invalid_values(self):
        self.assertIsNone(_parse_iso_dt("not-a-date"))
        self.assertIsNone(_parse_iso_dt("2026-99-99"))

    def test_safe_pdf_markup_paragraph_falls_back_on_invalid_markup(self):
        style = getSampleStyleSheet()["BodyText"]

        paragraph = safe_pdf_markup_paragraph("<para><b>broken", style, fallback_text="fallback")

        self.assertIsInstance(paragraph, Paragraph)

    def test_report_model_parameters_rows_v2_keeps_active_runtime_shape(self):
        report = {
            "context": {"profile": "E13DB", "source_file": "auditoria_post_crq.md", "schemas": ["APP_USER"]},
            "report_model": {
                "execution_parameters": {
                    "generated_at": "2026-03-26T12:00:00Z",
                    "time_window": {"start_at": "2026-03-01T00:00:00Z", "end_at": "2026-03-07T23:59:59Z"},
                },
                "enabled_checks": [{"check_id": "CHECK_02", "criticality": "Mitjà"}],
            },
        }

        rows = _report_model_parameters_rows_v2(report)
        labels = [label for label, _value in rows]

        self.assertEqual(labels[:4], ["Perfil", "Data i hora", "Finestra consultada", "Idioma"])
        self.assertTrue(labels[4].startswith("Codificaci"))
        self.assertEqual(labels[5:], ["Fitxer de checks", "Checks activats", "Esquemes o lots filtrats"])
        self.assertEqual(dict(rows)["Checks activats"], "CHECK_02 (Mitjà)")
        self.assertEqual(dict(rows)["Finestra consultada"], "01/03/2026 00:00 - 07/03/2026 23:59")
        self.assertEqual(dict(rows).get("No existeix", "fallback"), "fallback")

    def test_build_markdown_report_with_annex(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01", "CHECK_10"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "weekly"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )
        report["report_options"] = {"include_annex": True}

        text = build_post_crq_markdown_report("E13DB", report)
        self.assertIn("Annex A — anàlisi funcional de cada check", text)

    def test_build_markdown_report_keeps_visible_accents_in_current_report_path(self):
        report = run_post_crq_audit(
            db_manager=MockPostCrqDBManager(),
            selected_checks=["CHECK_01", "CHECK_10"],
            schemas=["APP_USER"],
            time_filter={"mode": "preset", "preset": "weekly"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        text = build_post_crq_markdown_report("E13DB", report)

        self.assertIn("Codificació", text)
        self.assertIn("Incidències crítiques", text)
        self.assertIn("Següents passos", text)
        self.assertNotIn("Codificaci?", text)
        self.assertNotIn("incidã", text.lower())
        self.assertIn("Què detecta", text)
        self.assertIn("Com corregir", text)
        self.assertIn("Validació posterior", text)

    def test_findings_without_schema_are_excluded_from_lot_views(self):
        report = run_post_crq_audit(
            db_manager=NoSchemaPostCrqDBManager(),
            selected_checks=["CHECK_01"],
            schemas=[],
            time_filter={"mode": "preset", "preset": "weekly"},
            profile="E13DB",
            ownership_db_path=self.ownership_db_path,
        )

        self.assertEqual(report["report_model"]["lot_summary"], [])
        self.assertEqual(report["report_model"]["lot_incident_groups"], [])
        self.assertGreater(report["report_model"]["quality_gate"]["findings_without_schema"], 0)
        self.assertTrue(any("sense esquema identificable" in warning for warning in report["report_model"]["final_observations"]["warnings"]))

    def test_incident_object_rows_match_react_columns(self):
        group = {
            "lot": "LOT_APP",
            "accio_recomanada": "No s'hauria d'usar a la taula",
            "schemas": [
                {
                    "nom": "APP_USER",
                    "object_count": 2,
                    "objectes": [
                        {
                            "OBJECTE": "TMP_ALPHA",
                            "TIPUS": "TABLE",
                            "DADA TÈCNICA": "Sense clau primària activa",
                        },
                        {
                            "nom": "TMP_BETA",
                            "tipus": "VIEW",
                            "dada_tecnica": "Sense índex actiu",
                            "accio_recomanada": "Legacy",
                        },
                    ],
                }
            ],
        }

        rows = _build_incident_objects_table_rows_v6(group)

        self.assertEqual(
            rows,
            [
                {"OBJECTE": "TMP_ALPHA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense clau primària activa"},
                {"OBJECTE": "TMP_BETA", "TIPUS": "VIEW", "DADA TÈCNICA": "Sense índex actiu"},
            ],
        )
        self.assertNotIn("Esquema", rows[0])
        self.assertNotIn("Acció recomanada", rows[0])


if __name__ == "__main__":
    unittest.main()
