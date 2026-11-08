"""
API tests with login switched ON (Phase 17): tokens, who may see whom,
admin-only endpoints, rate limits, security headers and the audit log.

Accounts (temporary users file, never data/users.json):
    asha  employee  E1001          lead  manager  E1064 (E1001's manager)
    root  admin

HOW TO RUN
    PS> pytest tests/api/test_auth_api.py -v
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.security.users import UserStore

client = TestClient(app)
SECRET = "test-secret-" + "x" * 40
PASSWORDS = {"asha": "employee-pass-1", "lead": "manager-pass-1", "root": "admin-pass-123"}


@pytest.fixture(scope="module")
def users_file(tmp_path_factory):
    """Created once: hashing a password is slow on purpose (600,000 PBKDF2 rounds)."""
    file = tmp_path_factory.mktemp("accounts") / "users.json"
    store = UserStore(file)
    store.save("asha", PASSWORDS["asha"], "employee", "E1001")
    store.save("lead", PASSWORDS["lead"], "manager", "E1064")
    store.save("root", PASSWORDS["root"], "admin")
    return file


@pytest.fixture
def auth_on(tmp_path, monkeypatch, users_file):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SECRET_KEY", SECRET)
    monkeypatch.setenv("USERS_FILE", str(users_file))
    monkeypatch.setenv("AUDIT_LOG_FILE", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()


def login(username: str) -> dict:
    response = client.post("/api/v1/auth/token", data={"username": username, "password": PASSWORDS[username]})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_returns_a_bearer_token(auth_on):
    body = client.post("/api/v1/auth/token", data={"username": "asha", "password": PASSWORDS["asha"]}).json()
    assert body["token_type"] == "bearer" and body["role"] == "employee" and body["employee_id"] == "E1001"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me["username"] == "asha" and me["can_view"] == "self" and me["authenticated"] is True


def test_wrong_password_and_unknown_user_look_the_same(auth_on):
    for data in ({"username": "asha", "password": "wrong-pass"}, {"username": "ghost", "password": "x"}):
        response = client.post("/api/v1/auth/token", data=data)
        assert response.status_code == 401 and response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_business_apis_need_a_login(auth_on):
    response = client.post("/api/v1/skills/analyze", json={"employee_id": "E1001"})
    assert response.status_code == 401 and response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    bad = client.get("/api/v1/learning-path/E1001", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_TOKEN"


def test_health_stays_open(auth_on):
    assert client.get("/api/v1/health").status_code == 200


def test_employee_sees_only_their_own_data(auth_on):
    asha = login("asha")
    assert client.get("/api/v1/learning-path/E1001", headers=asha).status_code == 200
    for method, url, body in [
        ("get", "/api/v1/learning-path/E1002", None),
        ("post", "/api/v1/skills/analyze", {"employee_id": "E1002"}),
        ("post", "/api/v1/roles/match", {"employee_id": "E1002"}),
        ("post", "/api/v1/trainings/recommend", {"employee_id": "E1002"}),
        ("post", "/api/v1/ai/chat", {"question": "What are my gaps?", "employee_id": "E1002"}),
        ("get", "/api/v1/learning-path/E9999", None),  # 403 too: unknown IDs cannot be probed
    ]:
        kwargs = {"headers": asha, **({"json": body} if body else {})}
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 403, (url, response.text)
        assert response.json()["error"]["code"] == "ACCESS_DENIED"


def test_chat_uses_the_logged_in_employee(auth_on):
    answer = client.post("/api/v1/ai/chat", json={"question": "What are my gaps?"}, headers=login("asha"))
    assert answer.status_code == 200, answer.text
    body = answer.json()  # no employee_id was sent: the answer is about asha's own employee, E1001 (Arjun)
    assert "my_learning_path" in body["intents"] and "Employee first name: Arjun." in body["facts"]


def test_manager_sees_the_team_only(auth_on):
    lead = login("lead")
    assert client.get("/api/v1/learning-path/E1001", headers=lead).status_code == 200
    assert client.get("/api/v1/learning-path/E1002", headers=lead).status_code == 403


def test_admin_sees_everyone_and_gets_404_for_unknown(auth_on):
    root = login("root")
    assert client.get("/api/v1/learning-path/E1002", headers=root).status_code == 200
    assert client.get("/api/v1/learning-path/E9999", headers=root).status_code == 404


def test_only_admins_upload_and_retrain(auth_on):
    files = {"file": ("note.md", b"# Note\n\nHello.")}
    denied = client.post("/api/v1/rag/ingest", files=files, headers=login("asha"))
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "ADMIN_ONLY"
    retrain = client.post("/api/v1/ml/retrain", json={}, headers=login("lead"))
    assert retrain.status_code == 403 and retrain.json()["error"]["code"] == "ADMIN_ONLY"
    nobody = client.delete("/api/v1/rag/documents/note.md")
    assert nobody.status_code == 401 and nobody.json()["error"]["code"] == "ADMIN_AUTH_REQUIRED"


def test_login_attempts_are_rate_limited(auth_on):
    for _ in range(10):
        client.post("/api/v1/auth/token", data={"username": "asha", "password": "guess-guess"})
    blocked = client.post("/api/v1/auth/token", data={"username": "asha", "password": PASSWORDS["asha"]})
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_global_rate_limit(auth_on, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    statuses = [client.get("/api/v1/auth/me").status_code for _ in range(4)]
    assert statuses[:3] == [401, 401, 401] and statuses[3] == 429
    assert client.get("/api/v1/health").status_code == 200  # health checks are never limited


def test_security_headers(auth_on):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_audit_log_records_who_but_never_secrets(auth_on):
    asha = login("asha")
    client.get("/api/v1/learning-path/E1002", headers=asha)
    lines = [json.loads(line) for line in (auth_on / "audit.jsonl").read_text().splitlines()]
    denied = [e for e in lines if e["path"] == "/api/v1/learning-path/E1002"][-1]
    assert denied["user"] == "asha" and denied["status"] == 403 and denied["role"] == "employee"
    text = (auth_on / "audit.jsonl").read_text()
    assert PASSWORDS["asha"] not in text and "Bearer" not in text


def test_me_in_open_local_mode():
    me = client.get("/api/v1/auth/me").json()
    assert me["authenticated"] is False and me["can_view"] == "everyone" and me["auth_enabled"] is False
