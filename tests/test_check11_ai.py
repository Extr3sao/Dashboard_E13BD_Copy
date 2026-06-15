import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.post_crq_audit import parse_post_crq_checks, run_post_crq_audit
from src.api.post_crq_check11_ai import (
    analyze_check11_results,
    merge_check11_ai_results,
    validate_check11_ai_response,
)
from src.core.openrouter_client import OpenRouterClient, OpenRouterSettings


class MockCheck11DBManager:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.last_error = None
        self.executed_queries = []

    def execute_query(self, query, params=None):
        self.executed_queries.append((query, params or {}))
        columns = [
            "ESQUEMA",
            "OBJECTE_PLSQL",
            "TIPUS_OBJECTE",
            "DATA_MODIFICACIO_OBJECTE",
            "LINIES_SOSPITOSES_EN_LOOP",
            "TOTAL_LINIES_CODI",
            "SEVERITAT_SQL",
            "OBSERVACIO",
            "LINIES_DETALL",
        ]
        return self.rows, columns


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout=None):
        self.get_calls.append({"url": url, "timeout": timeout})
        response = self.get_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, headers=None, json=None, timeout=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        response = self.post_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class TestCheck11AI(unittest.TestCase):
    def test_check11_is_documented_in_markdown_and_txt(self):
        checks = parse_post_crq_checks()
        check_11 = next(item for item in checks if item["check_id"] == "CHECK_11")
        self.assertIn("PROBLEMES DE CODI", check_11["title"].upper())

        txt_path = Path("consultes_post_crq.txt")
        self.assertTrue(txt_path.exists())
        txt_content = txt_path.read_text(encoding="utf-8")
        self.assertIn("CHECK_11", txt_content)
        self.assertIn("PROBLEMES DE CODI EN PAQUETS/PROCEDURES/FUNCIONS", txt_content)

    def test_check12_runs_with_days_back_and_no_ai_call_when_no_rows(self):
        dbm = MockCheck11DBManager(rows=[])
        with patch("src.api.post_crq_audit.analyze_check11_results") as analyze_mock:
            report = run_post_crq_audit(
                db_manager=dbm,
                selected_checks=["CHECK_12"],
                schemas=[],
                time_filter={"mode": "preset", "preset": "daily"},
                profile="E13DB",
            )

        self.assertFalse(analyze_mock.called)
        self.assertEqual(report["results_by_check"][0]["check_id"], "CHECK_12")
        self.assertEqual(dbm.executed_queries[0][1]["days_back"], 1)
        self.assertIn(":start_date", dbm.executed_queries[0][0])
        self.assertIn(":end_date", dbm.executed_queries[0][0])
        self.assertEqual(report["executed_checks"][0]["ai_analysis"]["status"], "skipped_no_rows")

    def test_check12_calls_ai_and_merges_structured_result(self):
        db_rows = [
            (
                "APP_USER",
                "PKG_BATCH",
                "PACKAGE BODY",
                "2026-03-09 12:00",
                4,
                180,
                "ALT",
                "Patró amb múltiples operacions SQL/DML dins de loop i sense pistes de bulk.",
                "10: SELECT ... || 25: UPDATE ...",
            )
        ]
        dbm = MockCheck11DBManager(rows=db_rows)
        ai_payload = {
            "status": "ok",
            "summary": {
                "total_findings": 1,
                "mala_praxis": 1,
                "falso_positivo": 0,
                "revision_manual": 0,
            },
            "items": [
                {
                    "esquema": "APP_USER",
                    "objecte_plsql": "PKG_BATCH",
                    "tipus_objecte": "PACKAGE BODY",
                    "severitat_sql": "ALT",
                    "classificacio_ia": "mala_praxis",
                    "confianca_ia": 92,
                    "explicacio_ia": "Hi ha DML dins de loop amb múltiples línies sospitoses.",
                    "recomanacio_ia": "Revisar refactor a BULK COLLECT/FORALL.",
                }
            ],
        }
        with patch("src.api.post_crq_audit.analyze_check11_results", return_value=ai_payload) as analyze_mock:
            report = run_post_crq_audit(
                db_manager=dbm,
                selected_checks=["CHECK_12"],
                schemas=[],
                time_filter={"mode": "range", "start_date": "2026-03-09T00:00", "end_date": "2026-03-09T23:59"},
                profile="E13DB",
            )

        self.assertTrue(analyze_mock.called)
        result = report["results_by_check"][0]
        self.assertIn("CLASSIFICACIO_IA", result["columns"])
        self.assertEqual(result["rows"][0]["SEVERITAT_SQL"], "ALT")
        self.assertEqual(result["rows"][0]["CLASSIFICACIO_IA"], "mala_praxis")
        self.assertEqual(result["rows"][0]["ESTAT_ANALISI_IA"], "ok")
        self.assertEqual(report["summary"]["check11_ai_summary"]["mala_praxis"], 1)

    def test_validate_check11_ai_response_accepts_valid_json(self):
        payload = {
            "check_id": "CHECK_11",
            "summary": {
                "total_findings": 1,
                "mala_praxis": 1,
                "falso_positivo": 0,
                "revision_manual": 0,
            },
            "items": [
                {
                    "esquema": "APP_USER",
                    "objecte_plsql": "PKG_BATCH",
                    "tipus_objecte": "PACKAGE BODY",
                    "severitat_sql": "ALT",
                    "classificacio_ia": "mala_praxis",
                    "confianca_ia": 90,
                    "explicacio_ia": "ok",
                    "recomanacio_ia": "ok",
                }
            ],
        }
        validated = validate_check11_ai_response(payload)
        self.assertEqual(validated["check_id"], "CHECK_11")

    def test_validate_check11_ai_response_rejects_invalid_json_shape(self):
        with self.assertRaises(ValueError):
            validate_check11_ai_response({"check_id": "CHECK_11", "summary": {}, "items": [{}]})

    def test_analyze_check11_results_uses_configured_model(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="custom/model-free",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=False,
        )
        session = FakeSession(
            post_responses=[
                FakeResponse(
                    payload={
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "check_id": "CHECK_11",
                                            "summary": {
                                                "total_findings": 1,
                                                "mala_praxis": 0,
                                                "falso_positivo": 1,
                                                "revision_manual": 0,
                                            },
                                            "items": [
                                                {
                                                    "esquema": "APP_USER",
                                                    "objecte_plsql": "PKG_BATCH",
                                                    "tipus_objecte": "PACKAGE BODY",
                                                    "severitat_sql": "ALT",
                                                    "classificacio_ia": "falso_positivo",
                                                    "confianca_ia": 55,
                                                    "explicacio_ia": "Cas de baixa cardinalitat.",
                                                    "recomanacio_ia": "Validar abans d'actuar.",
                                                }
                                            ],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                )
            ]
        )
        client = OpenRouterClient(settings=settings, session=session)
        rows = [
            {
                "ESQUEMA": "APP_USER",
                "OBJECTE_PLSQL": "PKG_BATCH",
                "TIPUS_OBJECTE": "PACKAGE BODY",
                "SEVERITAT_SQL": "ALT",
            }
        ]
        result = analyze_check11_results(rows, client=client)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(session.post_calls[0]["json"]["model"], "custom/model-free")

    def test_openrouter_selects_dynamic_free_model_when_not_configured(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=True,
        )
        session = FakeSession(
            get_responses=[
                FakeResponse(
                    payload={
                        "data": [
                            {"id": "vision/model:free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"modality": "image"}},
                            {"id": "provider/strong-instruct:free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"modality": "text"}, "context_length": 64000},
                        ]
                    }
                )
            ],
            post_responses=[
                FakeResponse(payload={"choices": [{"message": {"content": json.dumps({"check_id": "CHECK_11", "summary": {"total_findings": 0, "mala_praxis": 0, "falso_positivo": 0, "revision_manual": 0}, "items": []})}}]})
            ],
        )
        client = OpenRouterClient(settings=settings, session=session)
        model, meta = client.select_model()
        self.assertEqual(model, "provider/strong-instruct:free")
        self.assertEqual(meta["source"], "discovered")

    def test_openrouter_falls_back_to_openrouter_free_on_selection_failure(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=True,
        )
        client = OpenRouterClient(settings=settings, session=FakeSession(get_responses=[RuntimeError("catalog_down")]))
        model, meta = client.select_model()
        self.assertEqual(model, "openrouter/free")
        self.assertEqual(meta["source"], "fallback")

    def test_openrouter_falls_back_to_openrouter_free_when_primary_model_fails(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="provider/primary-free",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=False,
        )
        session = FakeSession(
            post_responses=[
                RuntimeError("timeout"),
                RuntimeError("timeout"),
                FakeResponse(payload={"choices": [{"message": {"content": json.dumps({"check_id": "CHECK_11", "summary": {"total_findings": 0, "mala_praxis": 0, "falso_positivo": 0, "revision_manual": 0}, "items": []})}}]}),
            ]
        )
        client = OpenRouterClient(settings=settings, session=session)
        response = client.chat_completion("system", {"check_id": "CHECK_11", "items": []})
        self.assertTrue(response["ok"])
        self.assertEqual(response["model"], "openrouter/free")
        self.assertEqual(response["status"], "fallback")

    def test_openrouter_failure_does_not_break_analysis(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="provider/primary-free",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=False,
        )
        session = FakeSession(
            post_responses=[RuntimeError("timeout"), RuntimeError("timeout"), RuntimeError("timeout"), RuntimeError("timeout")]
        )
        client = OpenRouterClient(settings=settings, session=session)
        rows = [{"ESQUEMA": "APP_USER", "OBJECTE_PLSQL": "PKG_BATCH", "TIPUS_OBJECTE": "PACKAGE BODY", "SEVERITAT_SQL": "ALT"}]
        result = analyze_check11_results(rows, client=client)
        self.assertEqual(result["status"], "no disponible")
        self.assertTrue(result["called"])

    def test_check11_invalid_json_response_falls_back_to_no_disponible(self):
        settings = OpenRouterSettings(
            enabled=True,
            api_key="secret",
            model="provider/primary-free",
            timeout_ms=5000,
            base_url="https://openrouter.example/api/v1",
            discover_free_model=False,
        )
        session = FakeSession(
            post_responses=[
                FakeResponse(payload={"choices": [{"message": {"content": "{invalid-json"}}]}),
            ]
        )
        client = OpenRouterClient(settings=settings, session=session)
        rows = [{"ESQUEMA": "APP_USER", "OBJECTE_PLSQL": "PKG_BATCH", "TIPUS_OBJECTE": "PACKAGE BODY", "SEVERITAT_SQL": "ALT"}]

        result = analyze_check11_results(rows, client=client)

        self.assertEqual(result["status"], "no disponible")
        self.assertTrue(result["called"])
        self.assertIn("Expecting property name enclosed in double quotes", result["error"])

    def test_merge_check11_ai_results_keeps_sql_severity_separate(self):
        rows = [
            {
                "ESQUEMA": "APP_USER",
                "OBJECTE_PLSQL": "PKG_BATCH",
                "TIPUS_OBJECTE": "PACKAGE BODY",
                "SEVERITAT_SQL": "ALT",
                "OBSERVACIO": "Patró heurístic",
            }
        ]
        ai_result = {
            "status": "ok",
            "items": [
                {
                    "esquema": "APP_USER",
                    "objecte_plsql": "PKG_BATCH",
                    "tipus_objecte": "PACKAGE BODY",
                    "classificacio_ia": "revision_manual",
                    "confianca_ia": 61,
                    "explicacio_ia": "Falten dades de cardinalitat.",
                    "recomanacio_ia": "Revisar manualment.",
                }
            ],
        }
        merged = merge_check11_ai_results(rows, ai_result)
        self.assertEqual(merged[0]["SEVERITAT_SQL"], "ALT")
        self.assertEqual(merged[0]["CLASSIFICACIO_IA"], "revision_manual")
        self.assertEqual(merged[0]["ESTAT_ANALISI_IA"], "ok")


if __name__ == "__main__":
    unittest.main()
