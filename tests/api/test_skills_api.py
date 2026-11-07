"""
API tests for API 1: POST /api/v1/skills/analyze (Phase 5).

These send real HTTP requests to the app in memory (FastAPI TestClient) and
check status codes, the response shape and the shared error format.

HOW TO RUN
    PS> pytest tests/api/test_skills_api.py -v
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
URL = "/api/v1/skills/analyze"


def test_data_engineer_example():
    response = client.post(URL, json={"employee_id": "E1001", "target_role_id": "R004"})
    assert response.status_code == 200
    body = response.json()
    assert body["gap_score"] == 37.5
    assert body["match_percentage"] == 62.5
    assert body["target_role"] == {"role_id": "R004", "title": "Data Engineer"}
    assert body["current_role"]["title"] == "Software Developer"
    assert body["mandatory_gaps"] == 3 and body["role_ready"] is False
    assert [s["skill"] for s in body["skills"]][:2] == ["AWS", "SQL"]
    assert body["suggestions"][0] == "Raise AWS (mandatory) from level 1 to 3."
    assert body["engine_version"]


def test_target_role_is_optional():
    body = client.post(URL, json={"employee_id": "E1001"}).json()
    assert body["target_source"] == "career_goal"


def test_what_if_levels():
    payload = {
        "employee_id": "E1001",
        "target_role_id": "R004",
        "current_skills": [
            {"skill": "SQL", "level": 4},
            {"skill": "Python", "level": 4},
            {"skill": "AWS", "level": 3},
            {"skill": "Docker", "level": 3},
        ],
    }
    body = client.post(URL, json=payload).json()
    assert body["role_ready"] is True and body["gap_score"] == 0.0
    assert len(body["overrides_applied"]) == 4


def test_unknown_employee_returns_404_in_standard_format():
    response = client.post(URL, json={"employee_id": "E9999", "target_role_id": "R004"})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "EMPLOYEE_NOT_FOUND" and "E9999" in error["message"] and error["request_id"]


def test_unknown_role_returns_404():
    response = client.post(URL, json={"employee_id": "E1001", "target_role_id": "R999"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "ROLE_NOT_FOUND"


def test_unknown_skill_returns_422():
    payload = {"employee_id": "E1001", "current_skills": [{"skill": "Cobol", "level": 3}]}
    response = client.post(URL, json=payload)
    assert response.status_code == 422 and response.json()["error"]["code"] == "UNKNOWN_SKILL"


def test_bad_format_returns_422_with_field_details():
    response = client.post(URL, json={"employee_id": "abc"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any("employee_id" in d["field"] for d in error["details"])


def test_endpoint_is_documented_in_swagger():
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][URL]["post"]
    assert operation["summary"].startswith("Analyse an employee")
    assert {"200", "404", "422"} <= set(operation["responses"])
