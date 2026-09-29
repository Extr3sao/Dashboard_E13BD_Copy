import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from src.api.security import SecretProvider, SQLExecutionPolicy, SessionStore, redact_secrets, require_csrf, require_service, require_user


def test_secret_provider_and_redaction():
    provider = SecretProvider({"SMTP_PASSWORD": "nope", "VALUE": "ok"})
    assert provider.get("VALUE") == "ok"
    assert provider.require("SMTP_PASSWORD") == "nope"
    assert redact_secrets({"smtp_password": "nope", "nested": {"token": "x", "ok": 1}}) == {"smtp_password": "[REDACTED]", "nested": {"token": "[REDACTED]", "ok": 1}}
    with pytest.raises(RuntimeError):
        provider.require("MISSING")


@pytest.mark.parametrize("query", ["SELECT * FROM users", "WITH x AS (SELECT 1) SELECT * FROM x;"])
def test_read_only_sql_policy_accepts_selects(query):
    assert SQLExecutionPolicy.validate_read_only(query)


@pytest.mark.parametrize("query", ["DELETE FROM users", "SELECT 1; DROP TABLE users", "WITH x AS (DELETE FROM users RETURNING id) SELECT * FROM x", "SELECT 1 -- comment"])
def test_read_only_sql_policy_rejects_writes_and_ambiguity(query):
    with pytest.raises(ValueError):
        SQLExecutionPolicy.validate_read_only(query)


def test_sessions_expire_rotate_revoke_and_csrf():
    now = [100.0]
    store = SessionStore(ttl_seconds=10, clock=lambda: now[0])
    token = store.create("alice")
    csrf = store.csrf_token(token)
    assert store.principal(token).subject == "alice"
    assert store.validate_csrf(token, csrf)
    replacement = store.rotate(token)
    assert store.get(token) is None
    assert store.get(replacement) is not None
    assert not store.validate_csrf(replacement, csrf)
    store.revoke(replacement)
    assert store.get(replacement) is None
    expiring = store.create("bob")
    now[0] = 111.0
    assert store.get(expiring) is None


def test_fastapi_user_service_and_csrf_policies():
    store = SessionStore()
    app = FastAPI()
    @app.get("/user")
    def user(principal=Depends(require_user(store))): return {"user": principal.subject}
    @app.post("/mutate", dependencies=[Depends(require_csrf(store))])
    def mutate(): return {"ok": True}
    @app.get("/service")
    def service(principal=Depends(require_service("service-secret"))): return {"role": principal.role}
    client = TestClient(app)
    assert client.get("/user").status_code == 401
    token = store.create("alice")
    client.cookies.set("session", token)
    assert client.get("/user").json() == {"user": "alice"}
    assert client.post("/mutate").status_code == 403
    assert client.post("/mutate", headers={"x-csrf-token": store.csrf_token(token)}).status_code == 200
    assert client.get("/service").status_code == 401
    assert client.get("/service", headers={"Authorization": "Bearer service-secret"}).json() == {"role": "SERVICE"}
