import os
os.environ["E13DB_AUTH_REQUIRED"] = "false"

from fastapi.testclient import TestClient
from src.api.alerting_engine import AlertingService
from src.api.alerting_router import create_alerting_router
from src.api.finding_engine import FindingStore
from src.api.security import SessionStore
from src.core.internal_db import InternalDBManager
from fastapi import FastAPI
import tempfile


def test_alert_routes_require_user_and_csrf():
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False); handle.close()
    sessions = SessionStore(); service = AlertingService(FindingStore(InternalDBManager(handle.name)))
    app = FastAPI(); app.include_router(create_alerting_router(service, sessions, "session")); client = TestClient(app)
    assert client.get("/api/alerting/alerts").status_code == 401
    token = sessions.create("operator", "USER")
    client.cookies.set("session", token)
    assert client.get("/api/alerting/alerts").status_code == 200
    assert client.post("/api/alerting/maintenance", json={"database_id":"D","starts_at":1,"ends_at":2}).status_code == 403
