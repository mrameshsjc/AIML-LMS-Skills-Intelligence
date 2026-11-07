"""
API tests for API 2: POST /api/v1/roles/match (Phase 6).

HOW TO RUN
    PS> pytest tests/api/test_roles_api.py -v
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
URL = "/api/v1/roles/match"


def test_ranked_matches_for_e1001():
    response = client.post(URL, json={"employee_id": "E1001"})
    assert response.status_code == 200
    body = response.json()
    assert [m["title"] for m in body["matches"][:3]] == ["Software Developer", "QA Engineer", "Data Engineer"]
    first = body["matches"][0]
    assert first["is_current_role"] is True and first["readiness"] == "Ready" and first["rank"] == 1
    assert body["career_goal"] == {"role_id": "R004", "title": "Data Engineer"}
    assert body["target"]["match_percentage"] == 62.5
    assert body["roles_considered"] == 13 and len(body["matches"]) == 5


def test_skill_lists_per_role():
    body = client.post(URL, json={"employee_id": "E1001", "role_ids": ["R004"]}).json()
    data_engineer = body["matches"][0]
    assert "Machine Learning" in data_engineer["matching_skills"]
    shortfall = {
        s["skill"]: (s["current_level"], s["required_level"]) for s in data_engineer["needs_improvement"]
    }
    assert shortfall["SQL"] == (2, 4) and shortfall["AWS"] == (1, 3)
    assert data_engineer["missing_skills"] == []


def test_related_roles_use_tf_idf_similarity():
    body = client.post(URL, json={"employee_id": "E1001"}).json()
    assert body["related_to"]["title"] == "Data Engineer"
    first = body["related_roles"][0]
    assert first["title"] == "Machine Learning Engineer"
    assert 0 < first["similarity"] <= 1 and "Python" in first["shared_skills"]


def test_top_n_and_target_outside_top_n():
    body = client.post(URL, json={"employee_id": "E1001", "top_n": 1, "target_role_id": "R006"}).json()
    assert len(body["matches"]) == 1
    assert body["target"]["title"] == "Machine Learning Engineer" and body["target"]["rank"] > 1


def test_errors():
    assert client.post(URL, json={"employee_id": "E9999"}).json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"
    response = client.post(URL, json={"employee_id": "E1001", "role_ids": ["R999"]})
    assert response.status_code == 404 and response.json()["error"]["code"] == "ROLE_NOT_FOUND"
    response = client.post(URL, json={"employee_id": "E1001", "role_ids": ["Data Engineer"]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_ROLE_ID"
    response = client.post(URL, json={"employee_id": "E1001", "top_n": 0})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_endpoint_is_documented_in_swagger():
    operation = client.get("/openapi.json").json()["paths"][URL]["post"]
    assert operation["summary"].startswith("Rank job roles")
    assert {"200", "404", "422"} <= set(operation["responses"])
