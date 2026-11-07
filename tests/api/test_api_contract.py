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
        if p["in"] in ("path", "query"):
            assert names.get(p["name"]) == p["required"], (path, p["name"])
        else:  # form fields of a file upload
            form = _schema(spec, operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"])
            assert (
                p["name"] in form["properties"] and (p["name"] in form.get("required", [])) == p["required"]
            )


def test_error_responses_are_documented(spec):
    for _, method, path, request_model, _, params in ENDPOINTS:
        if request_model is None and not params:
            continue  # takes no input, so nothing the caller sends can be wrong
        responses = spec["paths"][path][method.lower()]["responses"]
        assert set(responses) - {"200", "422"}, f"{method} {path} documents no error responses"


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
    ("post", "/api/v1/rag/ingest", {"files": {"file": ("tool.exe", b"MZ")}}, 422, "UNSUPPORTED_FILE_TYPE"),
    ("delete", "/api/v1/rag/documents/faq.md", {}, 409, "DOCUMENT_IS_APPROVED"),
    ("get", "/api/v1/no-such-endpoint", {}, 404, "NOT_FOUND"),
]


@pytest.mark.parametrize("method, url, kwargs, status, code", ERROR_CASES)
def test_every_error_has_the_shared_format(method, url, kwargs, status, code):
    response = getattr(client, method)(url, **kwargs, headers={"X-Request-ID": "test-123"})
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["message"]
    assert error["request_id"] == "test-123" == response.headers["X-Request-ID"]
