import unittest
from unittest.mock import patch

import requests

from src.core.dba_query_explainer import DBAExplainRequest, DBAQueryExplainer


class _DummyResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _http_error(status_code, payload):
    response = _DummyResponse(status_code, payload)
    return requests.HTTPError(f"{status_code} error", response=response)


class TestDBAQueryExplainer(unittest.TestCase):
    def setUp(self):
        self.req = DBAExplainRequest(
            check_id="CHECK_01",
            titol="TAULES RECENTS SENSE PRIMARY KEY",
            severitat="Mitjà",
            sql_nou="SELECT 1 FROM dual",
            versio_nova=1,
            parametres=["days_back"],
            context_check="Prova",
            tipus="SQL",
        )

    def test_parse_openrouter_error_detects_global_free_quota(self):
        payload = {
            "error": {
                "message": "Rate limit exceeded: free-models-per-day",
                "code": 429,
                "metadata": {"headers": {"X-RateLimit-Remaining": "0"}},
            }
        }
        info = DBAQueryExplainer._parse_openrouter_error(_DummyResponse(429, payload))
        self.assertTrue(DBAQueryExplainer._is_global_free_quota_exhausted(info))

    def test_explain_stops_when_global_free_quota_is_exhausted(self):
        explainer = DBAQueryExplainer()
        quota_error = _http_error(
            429,
            {
                "error": {
                    "message": "Rate limit exceeded: free-models-per-day",
                    "code": 429,
                    "metadata": {"headers": {"X-RateLimit-Remaining": "0"}},
                }
            },
        )

        with patch.object(explainer, "_get_active_models", return_value=[(1, "openrouter/free"), (2, "openai/gpt-oss-120b:free")]), patch.object(
            explainer,
            "_call_openrouter",
            side_effect=quota_error,
        ) as mocked_call:
            with self.assertRaisesRegex(RuntimeError, "Quota diària de models gratuïts"):
                explainer.explain(self.req)

        self.assertEqual(mocked_call.call_count, 1)

    def test_explain_continues_on_model_specific_http_error(self):
        explainer = DBAQueryExplainer()
        model_error = _http_error(
            404,
            {"error": {"message": "No endpoints found for test-model", "code": 404}},
        )
        valid_payload = """
        {
          "resum_executiu": "Aquesta resposta supera el mínim de caràcters i descriu de manera suficient el control revisat.",
          "explicacio_funcional": "El control revisa la presència de claus primàries i detecta taules rellevants sense aquesta restricció estructural.",
          "explicacio_tecnica": "Consulta tècnica amb prou detall per superar la validació mínima exigida, descrivint catàleg, filtres i patró estructural observat en el model revisat.",
          "impacte": "Pot afectar integritat i rendiment.",
          "riscos": "Hi pot haver duplicats i relacions inconsistents.",
          "recomanacio_revisio": "Revisar definició de la PK.",
          "nivell_confianca": 0.82,
          "advertiments": null,
          "que_detecta": "Detecta taules sense PK.",
          "per_que_es_important": "La PK és clau per a la integritat.",
          "impacte_sobre_lot": "Pot generar incidències en el lot.",
          "com_revisar": "Verificar constraints.",
          "com_corregir": "Afegir PK si escau.",
          "limitacions_o_falsos_positius": "Pot afectar taules temporals.",
          "columnes_taula_recomanades": ["Lot", "Esquema", "Taula"],
          "validacio_posterior": "Reexecutar el control.",
          "seccio_auditoria_md": "-- CHECK 01: prova",
          "linia_consultes_txt": "CHECK_01 | TAULES RECENTS SENSE PRIMARY KEY | severitat base: Mitjà | paràmetres: days_back"
        }
        """

        with patch.object(explainer, "_get_active_models", return_value=[(1, "broken-model"), (2, "working-model")]), patch.object(
            explainer,
            "_call_openrouter",
            side_effect=[model_error, valid_payload],
        ) as mocked_call:
            response = explainer.explain(self.req)

        self.assertEqual(mocked_call.call_count, 2)
        self.assertEqual(response.model_utilitzat, "working-model")

    def test_build_response_strips_existing_check_header_from_sql(self):
        explainer = DBAQueryExplainer()
        req = DBAExplainRequest(
            check_id="CHECK_01",
            titol="TAULES RECENTS SENSE PRIMARY KEY",
            severitat="Mitjà",
            sql_nou=(
                "-- ======================================\n"
                "-- CHECK 01: TAULES RECENTS SENSE PRIMARY KEY\n"
                "-- Criteri:\n"
                "--   Text\n"
                "-- ======================================\n"
                "SELECT 1 FROM dual"
            ),
            versio_nova=2,
            parametres=["days_back"],
            context_check="Prova",
            tipus="SQL",
        )
        parsed = {
            "resum_executiu": "Aquesta resposta supera clarament el minim de caracters i resumeix be el control.",
            "explicacio_funcional": "Explicacio funcional suficient per descriure el comportament del control i la seva finalitat.",
            "explicacio_tecnica": "Explicacio tecnica prou extensa per superar la validacio i descriure catalegs, filtres i tractament del resultat.",
            "impacte": "Impacte",
            "riscos": "Riscos",
            "recomanacio_revisio": "Revisio",
            "nivell_confianca": 0.8,
            "advertiments": None,
            "seccio_auditoria_md": "-- CHECK 01: prova",
            "linia_consultes_txt": "CHECK_01 | TAULES RECENTS SENSE PRIMARY KEY | severitat base: Mitjà | paràmetres: days_back",
        }

        response = explainer._build_response(req, parsed, "test-model", 10, 1, 1)

        self.assertEqual(response.bloc_auditoria_md.count("-- CHECK 01:"), 1)
        self.assertIn("SELECT 1 FROM dual", response.bloc_auditoria_md)
        self.assertIn("CHECK_01", response.explicacio_preview_text)
        self.assertIn("Qu", response.explicacio_preview_text)
        self.assertIn("Valid", response.explicacio_preview_text)


if __name__ == "__main__":
    unittest.main()
