import unittest
from unittest.mock import Mock, patch

import requests

from src.core.ai_assistant import AIAssistant


class TestAIAssistant(unittest.TestCase):
    def setUp(self):
        self.assistant = AIAssistant(model_name="google/gemini-2.0-flash-exp:free")
        self.assistant.config = Mock()

    @patch("src.core.ai_assistant.time.sleep", return_value=None)
    @patch("src.core.ai_assistant.random.uniform", return_value=0)
    @patch("src.core.ai_assistant.requests.post")
    def test_generate_openrouter_retries_rate_limit_then_succeeds(self, mock_post, _uniform, _sleep):
        self.assistant.config.get_env_var.return_value = "token"
        rate_limited = Mock(status_code=429, text="too many requests")
        success = Mock(status_code=200)
        success.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        mock_post.side_effect = [rate_limited, success]

        result = self.assistant._generate_openrouter("hola")

        self.assertEqual(result, "OK")
        self.assertEqual(mock_post.call_count, 2)

    @patch("src.core.ai_assistant.requests.post", side_effect=requests.RequestException("down"))
    @patch("src.core.ai_assistant.time.sleep", return_value=None)
    def test_generate_openrouter_returns_last_error_when_all_models_fail(self, _sleep, _post):
        self.assistant.config.get_env_var.return_value = "token"

        result = self.assistant._generate_openrouter("hola", timeout=5)

        self.assertIn("Tots els models d'IA han fallat", result)
        self.assertIn("down", result)

    @patch("src.core.ai_assistant.requests.get", side_effect=requests.RequestException("catalog down"))
    def test_get_models_returns_fallback_when_catalog_fails(self, _get):
        models = self.assistant.get_models()

        self.assertEqual(models, ["meta-llama/llama-3.3-70b-instruct:free"])

    @patch("src.core.ai_assistant.genai.GenerativeModel")
    @patch("src.core.ai_assistant.genai.configure")
    def test_generate_response_native_includes_active_schemas_in_prompt(self, mock_configure, mock_model_cls):
        native_assistant = AIAssistant(model_name="gemini-2.0-flash")
        native_assistant.config = Mock()
        native_assistant.config.get_env_var.return_value = "token"
        mock_model = mock_model_cls.return_value
        mock_model.generate_content.return_value = Mock(text="OK")

        result = native_assistant.generate_response(
            "fes una query",
            {"active_schemas": ["ABOIX", "E13_RALC"]},
        )

        self.assertEqual(result, "OK")
        mock_configure.assert_called_once_with(api_key="token")
        prompt = mock_model.generate_content.call_args.args[0]
        self.assertIn("ESQUEMES ACTIUS", prompt)
        self.assertIn("ABOIX", prompt)
        self.assertIn("fes una query", prompt)

    @patch("src.core.ai_assistant.genai.GenerativeModel")
    @patch("src.core.ai_assistant.genai.configure")
    def test_generate_response_native_returns_error_when_model_raises(self, _configure, mock_model_cls):
        native_assistant = AIAssistant(model_name="gemini-2.0-flash")
        native_assistant.config = Mock()
        native_assistant.config.get_env_var.return_value = "token"
        mock_model_cls.return_value.generate_content.side_effect = RuntimeError("native boom")

        result = native_assistant.generate_response("hola")

        self.assertIn("Error de la IA (Native)", result)
        self.assertIn("native boom", result)


if __name__ == "__main__":
    unittest.main()
