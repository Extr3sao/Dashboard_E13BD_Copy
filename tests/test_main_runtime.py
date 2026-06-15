import unittest
import tempfile
from pathlib import Path
from unittest.mock import mock_open
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
import pandas as pd

from src.api import main


class TestMainRuntime(unittest.IsolatedAsyncioTestCase):
    def test_run_with_internal_http_error_preserves_http_exception(self):
        expected = HTTPException(status_code=404, detail="missing")

        with self.assertRaises(HTTPException) as ctx:
            main._run_with_internal_http_error("demo", lambda: (_ for _ in ()).throw(expected))

        self.assertIs(ctx.exception, expected)

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.config_loader.load_connections", side_effect=RuntimeError("profiles boom"))
    async def test_get_profiles_uses_correct_error_stage(self, _load_connections, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.get_profiles()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "get_profiles")

    @patch("src.api.main.config_loader.get_env_var", return_value=None)
    @patch("src.api.main.OpenRouterClient", side_effect=RuntimeError("boom"))
    async def test_get_config_returns_fallback_when_openrouter_fails(self, _client, _get_env_var):
        result = await main.get_config()
        self.assertEqual(result["current_model"], "openrouter/free")
        self.assertEqual(result["available_models"], ["openrouter/free"])

    @patch("src.api.main.config_loader.get_env_var", return_value=None)
    @patch("src.api.main.OpenRouterClient")
    async def test_get_config_uses_model_list_fallback_when_catalog_fails(self, client_cls, _get_env_var):
        client = client_cls.return_value
        client.list_models.side_effect = ValueError("bad catalog")
        client.select_model.return_value = ("google/gemini-2.0-flash-exp:free", {})

        result = await main.get_config()

        self.assertEqual(result["current_model"], "google/gemini-2.0-flash-exp:free")
        self.assertEqual(result["available_models"], ["openrouter/free"])

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.AuditEngine")
    async def test_deep_scan_handler_closes_db_and_returns_failed_schema_rows(
        self,
        audit_engine_cls,
        oracle_cls,
        _load_connections,
        _resolve_profile,
    ):
        dbm = Mock()
        oracle_cls.return_value = dbm
        engine = Mock()

        async def audit(schema):
            if schema == "BAD":
                raise RuntimeError("oracle timeout")
            return {"username": schema, "obsolescence_score": 42, "summary": {"STATUS": "OK"}}

        engine.get_deep_schema_audit = AsyncMock(side_effect=audit)
        audit_engine_cls.return_value = engine

        result = await main.deep_scan_handler("ok,bad", "E13DB")

        self.assertEqual(result[0]["username"], "OK")
        self.assertEqual(result[1]["username"], "BAD")
        self.assertEqual(result[1]["summary"]["STATUS"], "FAILED")
        self.assertIn("oracle timeout", result[1]["error"])
        dbm.close.assert_called_once()

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager", side_effect=RuntimeError("connect boom"))
    @patch("src.api.main.AuditEngine")
    async def test_deep_scan_handler_keeps_running_when_oracle_manager_fails(
        self,
        audit_engine_cls,
        _oracle_cls,
        _load_connections,
        _resolve_profile,
    ):
        engine = Mock()
        engine.get_deep_schema_audit = AsyncMock(return_value={"username": "APP_A", "obsolescence_score": 1, "summary": {"STATUS": "OK"}})
        audit_engine_cls.return_value = engine

        result = await main.deep_scan_handler("APP_A", "E13DB")

        self.assertEqual(result[0]["username"], "APP_A")
        self.assertEqual(result[0]["summary"]["STATUS"], "OK")

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.AuditEngine")
    async def test_dashboard_stats_closes_db_when_gather_fails(
        self,
        audit_engine_cls,
        oracle_cls,
        _load_connections,
        _resolve_profile,
    ):
        dbm = Mock()
        oracle_cls.return_value = dbm
        engine = Mock()
        engine.get_deep_schema_audit = AsyncMock(side_effect=RuntimeError("audit failed"))
        audit_engine_cls.return_value = engine

        with self.assertRaises(HTTPException) as ctx:
            await main.get_dashboard_stats(["APP_A"], "E13DB")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("audit failed", ctx.exception.detail)
        dbm.close.assert_called_once()

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager", side_effect=RuntimeError("connect boom"))
    @patch("src.api.main.AuditEngine")
    async def test_dashboard_stats_uses_none_dbm_when_oracle_manager_fails(
        self,
        audit_engine_cls,
        _oracle_cls,
        _load_connections,
        _resolve_profile,
    ):
        engine = Mock()
        engine.get_deep_schema_audit = AsyncMock(return_value={"username": "APP_A", "obsolescence_score": 10, "summary": {"SIZE_GB": 2}})
        audit_engine_cls.return_value = engine

        result = await main.get_dashboard_stats(["APP_A"], "E13DB")

        self.assertEqual(result["total_gb"], 2)
        audit_engine_cls.assert_called_once_with(None)

    def test_apply_snapshot_filters_ignores_invalid_min_score(self):
        df = pd.DataFrame(
            [
                {"schema": "APP_A", "recommendation": "KEEP", "score": 10},
                {"schema": "APP_B", "recommendation": "DROP", "score": 90},
            ]
        )

        result = main._apply_snapshot_filters(df, ["APP_A", "APP_B"], ["KEEP", "DROP"], "bad-value")

        self.assertEqual(len(result), 2)

    def test_ctime_to_utc_iso_returns_utc_timestamp(self):
        self.assertEqual(main._ctime_to_utc_iso(0), "1970-01-01T00:00:00Z")

    def test_resolve_snapshot_path_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snap = root / "latest.parquet"
            snap.write_text("x", encoding="utf-8")

            with self.assertRaises(HTTPException) as ctx:
                main._resolve_snapshot_path(str(root), "..\\outside.parquet", [str(snap)])

            self.assertEqual(ctx.exception.status_code, 404)

    def test_resolve_snapshot_path_uses_latest_file_when_snapshot_id_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.parquet"
            newer = root / "newer.parquet"
            older.write_text("a", encoding="utf-8")
            newer.write_text("b", encoding="utf-8")

            with patch("os.path.getctime", side_effect=lambda p: 1 if str(p).endswith("older.parquet") else 2):
                resolved = main._resolve_snapshot_path(str(root), "", [str(older), str(newer)])

            self.assertEqual(resolved, str(newer))

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleQueries.get_summary_query", return_value="SELECT 1")
    @patch("src.api.main.OracleDBManager")
    async def test_run_audit_closes_db_when_execute_query_fails(
        self,
        oracle_cls,
        _get_summary_query,
        _load_connections,
        _resolve_profile,
    ):
        dbm = Mock()
        dbm.execute_query.side_effect = RuntimeError("query failed")
        oracle_cls.return_value = dbm

        with self.assertRaises(HTTPException) as ctx:
            await main.run_audit(["APP_A"], "E13DB")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("query failed", ctx.exception.detail)
        dbm.close.assert_called_once()

    @patch("src.api.main.internal_db.get_queries")
    async def test_get_knowledge_search_handles_none_explanation(self, get_queries):
        get_queries.return_value = [
            (1, "SELECT 1 FROM dual", None, "USER", "2026-03-26T10:00:00Z"),
            (2, "SELECT * FROM apps", "Aplicacions", "USER", "2026-03-26T10:01:00Z"),
        ]

        result = await main.get_knowledge("dual")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 1)

    @patch("src.core.ai_assistant.AIAssistant")
    def test_get_api_insights_returns_fallback_when_ai_raises(self, assistant_cls):
        assistant_cls.return_value.generate_response.side_effect = RuntimeError("ai down")

        result = main._get_api_insights(
            "E13DB",
            [
                {
                    "username": "APP_A",
                    "audit_result": "PRECAUCIO",
                    "obsolescence_score": 25,
                    "summary": {},
                }
            ],
        )

        self.assertEqual(result, "IA no disponible.")

    def test_read_repo_text_file_returns_content(self):
        with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data="doc content")):
            result = main._read_repo_text_file("doc.md", "not found")

        self.assertEqual(result, {"content": "doc content"})

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.list_jobs", side_effect=RuntimeError("jobs boom"))
    async def test_list_automation_jobs_uses_correct_error_stage(self, _list_jobs, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_automation_jobs()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "list_automation_jobs")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.get_delivery_routes", return_value={"providers": []})
    @patch("src.api.main.automation_store.update_delivery_routes", side_effect=RuntimeError("routes boom"))
    async def test_update_automation_delivery_routes_uses_correct_error_stage(
        self,
        _update_routes,
        _get_routes,
        raise_internal,
    ):
        with self.assertRaises(HTTPException) as ctx:
            await main.update_automation_delivery_routes({"providers": []})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "update_automation_delivery_routes")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.list_delivery_templates", side_effect=RuntimeError("templates boom"))
    async def test_list_automation_delivery_templates_uses_correct_error_stage(self, _list_templates, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_automation_delivery_templates()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "list_automation_delivery_templates")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.get_post_crq_analytics_overview", side_effect=RuntimeError("analytics boom"))
    async def test_get_automation_analytics_overview_uses_correct_error_stage(self, _overview, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.get_automation_analytics_overview()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "get_automation_analytics_overview")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.update_delivery_config", side_effect=RuntimeError("smtp boom"))
    async def test_test_automation_email_uses_correct_error_stage(self, _update_config, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.test_automation_email({"recipient": "ops@example.com", "smtp_host": "smtp.local"})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "test_automation_email")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.list_retry_queue", side_effect=RuntimeError("boom"))
    async def test_list_automation_retry_queue_uses_correct_error_stage(self, _list_retry_queue, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_automation_retry_queue()

        self.assertEqual(ctx.exception.detail, "wrapped")
        raise_internal.assert_called_once()
        self.assertEqual(raise_internal.call_args.args[0], "list_automation_retry_queue")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.internal_db.list_schema_lots", side_effect=RuntimeError("schema lots boom"))
    async def test_update_automation_schema_lots_uses_correct_error_stage(self, _list_schema_lots, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.update_automation_schema_lots({"items": []})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "update_automation_schema_lots")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.pd.read_parquet", side_effect=RuntimeError("parquet boom"))
    @patch("src.api.main._resolve_snapshot_path", return_value="C:/tmp/latest.parquet")
    @patch("src.api.main._list_parquet_files", return_value=["C:/tmp/latest.parquet"])
    @patch("src.api.main._snapshots_dir", return_value="C:/tmp")
    async def test_export_snapshot_csv_uses_correct_error_stage(
        self,
        _snapshots_dir,
        _list_files,
        _resolve_snapshot_path,
        _read_parquet,
        raise_internal,
    ):
        with self.assertRaises(HTTPException) as ctx:
            await main.export_snapshot_csv({})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "export_snapshot_csv")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main._list_parquet_files", side_effect=RuntimeError("snapshots boom"))
    async def test_list_snapshots_uses_correct_error_stage(self, _list_files, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_snapshots()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "list_snapshots")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main._list_parquet_files", side_effect=RuntimeError("latest boom"))
    async def test_latest_snapshot_uses_correct_error_stage(self, _list_files, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.latest_snapshot()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "latest_snapshot")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.internal_db.list_meta_objects", side_effect=RuntimeError("db failed"))
    async def test_list_obsolets_uses_correct_error_stage(self, _list_meta_objects, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_obsolets()

        self.assertEqual(ctx.exception.detail, "wrapped")
        raise_internal.assert_called_once()
        self.assertEqual(raise_internal.call_args.args[0], "list_obsolets")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager")
    async def test_run_post_crq_uses_correct_error_stage(
        self,
        oracle_cls,
        _load_connections,
        _resolve_profile,
        raise_internal,
    ):
        dbm = Mock()
        oracle_cls.return_value = dbm
        with patch("src.api.main.run_post_crq_audit", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                await main.run_post_crq({"profile": "E13DB", "schemas": ["APP_A"]})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "run_post_crq")
        dbm.close.assert_called_once()

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.parse_post_crq_checks", side_effect=RuntimeError("checks boom"))
    async def test_list_post_crq_checks_uses_correct_error_stage(self, _parse_checks, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_post_crq_checks()

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "list_post_crq_checks")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.AuditEngine")
    async def test_run_plan_execution_closes_db_and_uses_correct_error_stage(
        self,
        audit_engine_cls,
        oracle_cls,
        _load_connections,
        _resolve_profile,
        raise_internal,
    ):
        dbm = Mock()
        oracle_cls.return_value = dbm
        engine = Mock()
        engine.run_plan_audit = AsyncMock(side_effect=RuntimeError("plan boom"))
        audit_engine_cls.return_value = engine

        with self.assertRaises(HTTPException) as ctx:
            await main.run_plan_execution(["APP_A"], "E13DB", False)

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "run_plan_execution")
        dbm.close.assert_called_once()

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main._resolve_post_crq_report_payload", side_effect=RuntimeError("reports boom"))
    async def test_generate_post_crq_reports_uses_correct_error_stage(self, _resolve_payload, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.generate_post_crq_reports({"profile": "E13DB", "variant": "general"})

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "generate_post_crq_reports")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.build_post_crq_experimental_pdf", side_effect=RuntimeError("experimental boom"))
    async def test_generate_experimental_report_uses_correct_error_stage(self, _build_pdf, raise_internal):
        payload = {
            "profile": "E13DB",
            "data": {
                "audit_type": "post_crq",
                "report_model": {"execution_parameters": {}},
            },
        }

        with self.assertRaises(HTTPException) as ctx:
            await main.generate_experimental_report(payload)

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "generate_experimental_report")

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.report_builder.build_standard_markdown", side_effect=RuntimeError("report boom"))
    async def test_generate_report_uses_correct_error_stage(self, _build_markdown, raise_internal):
        payload = {
            "profile": "E13DB",
            "format": "markdown",
            "data": [
                {
                    "username": "APP_A",
                    "audit_result": "PRECAUCIO",
                    "obsolescence_score": 90,
                    "summary": {
                        "SIZE_GB": 1.5,
                        "INBOUND_REFERENCES": 2,
                        "ACTIVE_JOBS": 0,
                        "APEX_APPLICATIONS": 1,
                        "ENABLED_TRIGGERS": 0,
                    },
                    "reason": "demo",
                }
            ],
        }

        with self.assertRaises(HTTPException) as ctx:
            await main.generate_report(payload)

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "generate_report")

    @patch("src.api.main.build_post_crq_pdf_report", side_effect=RuntimeError("pdf boom"))
    async def test_generate_report_post_crq_pdf_includes_classic_stage_detail(self, _build_pdf):
        payload = {
            "profile": "E13DB",
            "format": "pdf",
            "data": {"audit_type": "post_crq", "results_by_check": []},
        }

        with self.assertRaises(HTTPException) as ctx:
            await main.generate_report(payload)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("report_generation_stage=classic_post_crq_pdf", ctx.exception.detail)

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.AIAssistant", side_effect=RuntimeError("ai import boom"))
    async def test_import_queries_uses_correct_error_stage(self, _assistant, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.import_queries("SELECT 1 FROM dual;", None)

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "import_queries")

    @patch("src.api.main._resolve_profile_key", return_value="E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    @patch("src.api.main.OracleDBManager")
    async def test_execute_query_closes_db_when_query_fails(
        self,
        oracle_cls,
        _load_connections,
        _resolve_profile,
    ):
        dbm = Mock()
        dbm.execute_query.side_effect = RuntimeError("sql boom")
        oracle_cls.return_value = dbm

        with self.assertRaises(HTTPException) as ctx:
            await main.execute_query("SELECT 1 FROM dual", "E13DB")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("sql boom", ctx.exception.detail)
        dbm.close.assert_called_once()

    @patch("src.api.main.OracleDBManager")
    async def test_test_db_returns_error_and_closes_db_when_query_fails(self, oracle_cls):
        dbm = Mock()
        dbm.execute_query.side_effect = RuntimeError("oracle down")
        oracle_cls.return_value = dbm

        result = await main.test_db(user="u", password="p", dsn="db", profile="")

        self.assertEqual(result["status"], "error")
        self.assertIn("oracle down", result["message"])
        dbm.close.assert_called_once()

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.pd.DataFrame", side_effect=RuntimeError("excel boom"))
    async def test_export_query_results_uses_correct_error_stage(self, _dataframe, raise_internal):
        with self.assertRaises(HTTPException) as ctx:
            await main.export_query_results([{"id": 1}])

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "export_query_results")

    def test_normalize_report_rows_handles_frontend_and_deep_rows(self):
        frontend = main._normalize_report_rows([{"schema": "APP_A", "decision": "PRECAUCIO", "score": "90", "size_gb": "1.5", "inbound_refs": "2", "active_jobs": "0", "apex_apps": "1", "enabled_triggers": "0", "reason": "demo"}])
        deep = main._normalize_report_rows({"username": "APP_B", "audit_result": "NO ELIMINAR", "obsolescence_score": "10", "summary": {"SIZE_GB": "3.0", "INBOUND_REFERENCES": "4", "ACTIVE_JOBS": "1", "APEX_APPLICATIONS": "0", "ENABLED_TRIGGERS": "2"}})

        self.assertEqual(frontend[0]["schema"], "APP_A")
        self.assertEqual(frontend[0]["inbound_refs"], 2)
        self.assertEqual(deep[0]["schema"], "APP_B")
        self.assertEqual(deep[0]["active_jobs"], 1)

    @patch("src.api.main._raise_internal_http_error", side_effect=HTTPException(status_code=500, detail="wrapped"))
    @patch("src.api.main.automation_store.get_run", return_value={"id": 7})
    @patch("src.api.main.automation_store.list_run_lot_statuses", side_effect=RuntimeError("csv boom"))
    async def test_export_automation_run_lots_csv_uses_correct_error_stage(
        self,
        _list_run_lot_statuses,
        _get_run,
        raise_internal,
    ):
        with self.assertRaises(HTTPException) as ctx:
            await main.export_automation_run_lots_csv(7)

        self.assertEqual(ctx.exception.detail, "wrapped")
        self.assertEqual(raise_internal.call_args.args[0], "export_automation_run_lots_csv")


if __name__ == "__main__":
    unittest.main()
