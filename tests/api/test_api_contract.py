"""
API contract checks against the running app (Phase 14).

  - The OpenAPI description FastAPI publishes (what /docs shows) lists exactly the
    endpoints in app/schemas/contract.py, with the same request/response models and
    parameters. A new endpoint without a contract entry fails here.
  - Every error, from every endpoint, has the shared format and a request ID.

HOW TO RUN
    PS> pytest tests/api/test_api_contract.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.contract import ENDPOINTS
from tests.conftest import TEST_ADMIN_KEY

client = TestClient(app)
OPERATIONAL = {"/api/v1/health", "/api/v1/health/llm", "/api/v1/health/rag"}


@pytest.fixture(scope="module")
def spec() -> dict:
    return app.openapi()


def _schema(spec: dict, ref: str) -> dict:
    return spec["components"]["schemas"][ref.rsplit("/", 1)[1]]


def test_every_api_path_has_a_contract(spec):
    published = {path for path in spec["paths"] if path.startswith("/api/v1")}
    in_contract = {path for _, _, path, *_ in ENDPOINTS}
    assert published - OPERATIONAL == in_contract


@pytest.mark.parametrize("api, method, path, request_model, response_model, params", ENDPOINTS)
def test_published_endpoint_matches_the_contract(
    spec, api, method, path, request_model, response_model, params
):
    operation = spec["paths"][path][method.lower()]
    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert response_model.__name__ in ok
    if request_model is not None:
        body = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        assert request_model.__name__ in body
    names = {p["name"]: p.get("required", False) for p in operation.get("parameters", [])}
    for p in params:
        if p["in"] in ("path", "query", "header"):
            assert names.get(p["name"]) == p["required"], (path, p["name"])
        else:  # form fields: a file upload (multipart) or the login form (urlencoded)
            content = next(iter(operation["requestBody"]["content"].values()))
            form = _schema(spec, content["schema"]["$ref"])
            assert (
                p["name"] in form["properties"] and (p["name"] in form.get("required", [])) == p["required"]
            )


def test_error_responses_are_documented(spec):
    for _, method, path, request_model, _, params in ENDPOINTS:
        if request_model is None and not params:
            continue  # takes no input, so nothing the caller sends can be wrong
        responses = spec["paths"][path][method.lower()]["responses"]
        assert set(responses) - {"200", "422"}, f"{method} {path} documents no error responses"


ADMIN = {"X-Admin-Key": TEST_ADMIN_KEY}
ERROR_CASES = [
    ("post", "/api/v1/skills/analyze", {"json": {"employee_id": "E9999"}}, 404, "EMPLOYEE_NOT_FOUND"),
    ("post", "/api/v1/skills/analyze", {"json": {"employee_id": "bad"}}, 422, "VALIDATION_ERROR"),
    ("post", "/api/v1/roles/match", {"json": {"employee_id": "E9999"}}, 404, "EMPLOYEE_NOT_FOUND"),
    (
        "post",
        "/api/v1/trainings/recommend",
        {"json": {"employee_id": "E1001", "skills": ["Cobol"]}},
        422,
        "UNKNOWN_SKILL",
    ),
    ("get", "/api/v1/learning-path/E9999", {}, 404, "EMPLOYEE_NOT_FOUND"),
    ("get", "/api/v1/learning-path/E1001?target_role_id=R999", {}, 404, "ROLE_NOT_FOUND"),
    ("post", "/api/v1/ai/chat", {"json": {"question": "?"}}, 422, "VALIDATION_ERROR"),
    (
        "post",
        "/api/v1/rag/ingest",
        {"files": {"file": ("tool.exe", b"MZ")}, "headers": ADMIN},
        422,
        "UNSUPPORTED_FILE_TYPE",
    ),
    ("post", "/api/v1/rag/ingest", {"files": {"file": ("a.md", b"# a")}}, 401, "ADMIN_AUTH_REQUIRED"),
    ("delete", "/api/v1/rag/documents/faq.md", {"headers": ADMIN}, 409, "DOCUMENT_IS_APPROVED"),
    (
        "delete",
        "/api/v1/rag/documents/faq.md",
        {"headers": {"X-Admin-Key": "wrong"}},
        401,
        "ADMIN_AUTH_REQUIRED",
    ),
    ("post", "/api/v1/ml/retrain", {"json": {}}, 401, "ADMIN_AUTH_REQUIRED"),
    ("post", "/api/v1/auth/token", {"data": {"username": "a", "password": "b"}}, 403, "AUTH_DISABLED"),
    ("get", "/api/v1/no-such-endpoint", {}, 404, "NOT_FOUND"),
]


@pytest.mark.parametrize("method, url, kwargs, status, code", ERROR_CASES)
def test_every_error_has_the_shared_format(method, url, kwargs, status, code):
    headers = {"X-Request-ID": "test-123", **kwargs.get("headers", {})}
    other = {k: v for k, v in kwargs.items() if k != "headers"}
    response = getattr(client, method)(url, **other, headers=headers)
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["message"]
    assert error["request_id"] == "test-123" == response.headers["X-Request-ID"]
