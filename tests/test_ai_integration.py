import sys
import os
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.ai_assistant import AIAssistant


class TestAIIntegration(unittest.TestCase):
    def setUp(self):
        self.assistant = AIAssistant(model_name="google/gemini-2.0-flash-exp:free")

    def test_basic_query(self):
        prompt = "Hola! Respon breument: Què és una base de dades SQL?"

        with patch.object(self.assistant, "_generate_openrouter", return_value="SQL és un llenguatge de consulta.") as openrouter_mock:
            response = self.assistant.generate_response(prompt)

        openrouter_mock.assert_called_once_with(prompt, None, timeout=45)
        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)
        self.assertTrue(len(response) > 0)
        self.assertIn("SQL", response.upper())

    def test_analyze_query_integration(self):
        sql = "SELECT * FROM usuaris WHERE id = 1"

        with patch.object(self.assistant, "generate_response", return_value="Anàlisi correcta") as generate_mock:
            analysis = self.assistant.analyze_query(sql)

        generate_mock.assert_called_once()
        called_prompt = generate_mock.call_args.args[0]
        self.assertIn("Analitza la següent consulta SQL", called_prompt)
        self.assertIn(sql, called_prompt)
        self.assertIsNotNone(analysis)
        self.assertTrue(len(analysis) > 10)


if __name__ == "__main__":
    unittest.main()
