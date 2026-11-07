"""
Tests for the Phase 1 application skeleton.

HOW TO RUN (PowerShell, venv activated, from the project folder)
    PS> pytest -v

HOW THESE TESTS WORK
    FastAPI's `TestClient` sends HTTP requests to the app in memory, without
    starting a real server. That makes tests fast and lets GitHub Actions run
    them on every push.

EXPECTED RESULT
    tests/api/test_health.py::test_health_returns_ok PASSED
    tests/api/test_health.py::test_root_points_to_docs PASSED
    ... 6 passed
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    """The health endpoint answers 200 with status 'ok' and the app version."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == "LMS Skills Intelligence Engine"
    assert body["version"]  # not empty
    assert "timestamp" in body


def test_root_points_to_docs():
    """The root URL tells a new user where Swagger UI is."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_every_response_has_a_request_id():
    """Each response carries an X-Request-ID header for tracing in logs."""
    response = client.get("/api/v1/health")

    assert response.headers.get("X-Request-ID")


def test_incoming_request_id_is_reused():
    """If the caller sends an ID (as the LMS will later), we keep it."""
    response = client.get("/api/v1/health", headers={"X-Request-ID": "lms-12345"})

    assert response.headers["X-Request-ID"] == "lms-12345"


def test_unknown_url_uses_standard_error_format():
    """A wrong URL returns 404 in our shared error format, not a bare message."""
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"]


def test_swagger_docs_are_available():
    """Swagger UI and the OpenAPI schema load, and list the health endpoint."""
    assert client.get("/docs").status_code == 200

    schema = client.get("/openapi.json").json()
    assert "/api/v1/health" in schema["paths"]
