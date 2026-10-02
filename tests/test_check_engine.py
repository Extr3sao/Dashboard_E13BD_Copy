import unittest
from src.api.check_engine import RuleDefinition, RuleEngine, RuleStatus
from src.api.post_crq_rule_adapter import definition_from_post_crq, result_from_post_crq


class CheckEngineTests(unittest.TestCase):
    def test_statuses_gates_isolation_and_redaction(self):
        rules = [RuleDefinition("pass", "Pass"), RuleDefinition("bad", "Bad"), RuleDefinition("licensed", "L", license_requirements=("pack",)), RuleDefinition("cap", "C", required_capabilities=("x",))]
        result = RuleEngine().execute(rules, "db", lambda r: (_ for _ in ()).throw(RuntimeError("password=topsecret")) if r.rule_id == "bad" else {"status":"WARN", "evidence":{"token":"x"}}, engine="oracle", version="19", privileges=[])
        self.assertEqual([x.status for x in result], [RuleStatus.WARN, RuleStatus.ERROR, RuleStatus.SKIPPED, RuleStatus.SKIPPED])
        self.assertIn("[REDACTED]", result[0].evidence["token"]); self.assertNotIn("topsecret", result[1].error)

    def test_post_crq_adapter_preserves_normalized_semantics(self):
        definition = definition_from_post_crq({"check_id":"CHECK_01", "title":"x", "severitat":"MITJA"})
        result = result_from_post_crq({"status":"ok", "row_count":1, "duration_ms":1, "rows":[{"password":"x"}], "columns":["password"]}, "E13DB", definition)
        self.assertEqual(result.status, RuleStatus.FAIL)
        self.assertEqual(result.evidence["row_count"], 1)
        self.assertEqual(result.evidence["columns"], ["password"])
        self.assertNotIn("rows", result.evidence)
