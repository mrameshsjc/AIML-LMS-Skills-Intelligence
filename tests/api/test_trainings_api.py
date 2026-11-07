"""
API tests for API 3: POST /api/v1/trainings/recommend (Phase 7).

HOW TO RUN
    PS> pytest tests/api/test_trainings_api.py -v
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
URL = "/api/v1/trainings/recommend"


def test_recommendations_for_e1001():
    response = client.post(URL, json={"employee_id": "E1001"})
    assert response.status_code == 200
    body = response.json()
    ids = [r["course_id"] for r in body["recommendations"]]
    assert ids == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201"]
    top = body["recommendations"][0]
    assert top["score"] == 1.0 and top["rank"] == 1 and top["addresses_mandatory_gap"] is True
    assert top["components"]["completion_probability"] is None
    assert top["skills_covered"][0] == {
        "skill": "SQL", "current_level": 2, "required_level": 4, "course_from": 2, "course_to": 4,
        "gap_closed": 2, "gap": 2, "mandatory": True,
    }  # fmt: skip
    assert top["reason"].startswith("Your SQL is level 2 and Data Engineer needs level 4")
    assert body["target_role"]["title"] == "Data Engineer"
    assert "completion_probability" not in body["weights_used"]
    assert "SQL 2->4 (mandatory)" in body["skill_gaps"]


def test_filter_and_limit():
    body = client.post(URL, json={"employee_id": "E1001", "skills": ["AWS"], "max_results": 1}).json()
    assert [r["course_id"] for r in body["recommendations"]] == ["C-AWS-101"]


def test_no_gaps():
    body = client.post(URL, json={"employee_id": "E1001", "target_role_id": "R001"}).json()
    assert body["recommendations"] == [] and "nothing to recommend" in body["notes"][0]


def test_errors():
    assert client.post(URL, json={"employee_id": "E9999"}).status_code == 404
    response = client.post(URL, json={"employee_id": "E1001", "skills": ["Cobol"]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "UNKNOWN_SKILL"
    response = client.post(URL, json={"employee_id": "E1001", "max_results": 0})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_endpoint_is_documented_in_swagger():
    operation = client.get("/openapi.json").json()["paths"][URL]["post"]
    assert operation["summary"].startswith("Recommend courses")
    assert {"200", "404", "422"} <= set(operation["responses"])
