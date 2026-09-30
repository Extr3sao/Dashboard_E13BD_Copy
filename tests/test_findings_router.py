import unittest

from fastapi.testclient import TestClient

from src.api import main


class FindingsRouterSecurityTests(unittest.TestCase):
    def setUp(self):
        main.finding_store.reconcile("API_TEST", [{"database_id": "API_TEST", "rule_id": "R1", "status": "FAIL", "severity": "HIGH", "summary": "test", "metrics": {"row_count": 1}}])
        self.finding_id = main.finding_store.list_findings(database="API_TEST")[0]["id"]
        self.client = TestClient(main.app)

    def test_list_requires_user_and_mutation_requires_csrf(self):
        self.assertEqual(self.client.get("/api/findings").status_code, 401)
        session = main.session_store.create("dba", "USER")
        csrf = main.session_store.csrf_token(session)
        self.client.cookies.set(main.SESSION_COOKIE_NAME, session)
        self.assertEqual(self.client.get("/api/findings").status_code, 200)
        self.assertEqual(self.client.post(f"/api/findings/{self.finding_id}/acknowledge", json={"reason": "known"}).status_code, 403)
        response = self.client.post(f"/api/findings/{self.finding_id}/acknowledge", json={"reason": "known"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ACKNOWLEDGED")
