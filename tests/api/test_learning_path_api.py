"""
API tests for API 4: GET /api/v1/learning-path/{employee_id} (Phase 10).

HOW TO RUN
    PS> pytest tests/api/test_learning_path_api.py -v
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
URL = "/api/v1/learning-path"


def test_learning_path_for_e1001():
    response = client.get(f"{URL}/E1001")
    assert response.status_code == 200
    body = response.json()
    assert body["current_role"]["title"] == "Software Developer"
    assert body["target_role"] == {"role_id": "R004", "title": "Data Engineer"}
    assert body["target_source"] == "career_goal"
    assert [s["course_id"] for s in body["path"]] == [
        "C-SQL-201",
        "C-PY-201",
        "C-AWS-101",
        "C-AWS-201",
        "C-DOCKER-201",
    ]
    aws_201 = body["path"][3]
    assert aws_201["after_steps"] == [3] and aws_201["ready_now"] is False
    assert aws_201["prerequisites"][0] == {
        "course_id": "C-AWS-101",
        "title": "AWS Cloud Foundations",
        "satisfied": False,
        "how": "not yet",
    }
    assert body["progress"]["match_percentage"] == 62.5
    assert body["progress"]["projected_match_percentage"] == 100.0
    assert body["progress"]["total_hours"] == 90
    assert body["next_action"].startswith("Enrol in C-SQL-201")
    aws_gap = next(g for g in body["skill_gaps"] if g["skill"] == "AWS")
    assert aws_gap["closed_by"] == ["C-AWS-101", "C-AWS-201"]
    assert any(s["skill"] == "Python" and s["level"] == 3 for s in body["current_skills"])
    assert body["engine_version"]


def test_target_role_and_optional_skills_query_parameters():
    body = client.get(f"{URL}/E1001", params={"target_role_id": "R001"}).json()
    assert body["path"] == [] and body["next_action"].startswith("You already meet")
    body = client.get(f"{URL}/E1001", params={"include_optional": "false"}).json()
    assert "C-DOCKER-201" not in [s["course_id"] for s in body["path"]]


def test_unknown_employee_returns_404():
    response = client.get(f"{URL}/E9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"


def test_unknown_role_returns_404():
    response = client.get(f"{URL}/E1001", params={"target_role_id": "R999"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROLE_NOT_FOUND"


def test_invalid_ids_return_422():
    assert client.get(f"{URL}/1001").status_code == 422
    assert client.get(f"{URL}/E1001", params={"target_role_id": "Data Engineer"}).status_code == 422
