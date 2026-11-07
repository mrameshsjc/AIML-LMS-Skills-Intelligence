"""
API tests for API 6: POST /api/v1/ml/retrain (admin only) and GET /api/v1/ml/status (Phase 16).

Each test uses a temporary models folder and its own admin key; MLflow is
switched off so the tests do not depend on it.

HOW TO RUN
    PS> pytest tests/api/test_ml_api.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.main import app

client = TestClient(app)
URL = "/api/v1/ml/retrain"
KEY = "test-admin-key"


@pytest.fixture
def ml_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("ADMIN_API_KEY", KEY)
    monkeypatch.setenv("MLFLOW_ENABLED", "false")
    get_settings.cache_clear()
    dependencies.get_completion_predictor.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()
    dependencies.get_completion_predictor.cache_clear()


def test_retraining_needs_the_admin_key(ml_env):
    for headers in ({}, {"X-Admin-Key": "wrong"}):
        response = client.post(URL, json={}, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "ADMIN_AUTH_REQUIRED"


def test_retraining_is_off_without_a_configured_key(ml_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    get_settings.cache_clear()
    response = client.post(URL, json={}, headers={"X-Admin-Key": "anything"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "ADMIN_ACTIONS_DISABLED"


@pytest.mark.slow
def test_admin_retrains_and_status_shows_it(ml_env):
    response = client.post(URL, json={"reason": "first model"}, headers={"X-Admin-Key": KEY})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "promoted" and body["gate_passed"] is True
    assert (body["previous_version"], body["new_version"], body["current_version"]) == (None, 1, 1)
    assert [c["name"] for c in body["quality_gate"]] == [
        "minimum_quality",
        "better_than_chance",
        "no_regression",
    ]
    assert body["training"]["rows"]["total"] == 443 and body["data_validation"]["errors"] == 0
    assert body["mlflow"]["enabled"] is False and body["requested_by"] == "admin"

    status = client.get("/api/v1/ml/status").json()
    assert status["current_version"] == 1 and status["versions"][0]["status"] == "approved"
    assert status["recent_runs"][0]["reason"] == "first model" and status["admin_actions_enabled"] is True


@pytest.mark.slow
def test_promoted_model_is_used_by_api3_at_once(ml_env, monkeypatch):
    monkeypatch.setenv("USE_COMPLETION_MODEL", "true")
    get_settings.cache_clear()
    before = client.post("/api/v1/trainings/recommend", json={"employee_id": "E1001"}).json()
    assert before["recommendations"][0]["components"]["completion_probability"] is None
    assert client.post(URL, json={}, headers={"X-Admin-Key": KEY}).json()["status"] == "promoted"
    after = client.post("/api/v1/trainings/recommend", json={"employee_id": "E1001"}).json()
    assert (
        after["recommendations"][0]["components"]["completion_probability"] is not None
    )  # no restart needed


def test_status_without_any_model(ml_env):
    status = client.get("/api/v1/ml/status").json()
    assert status["current_version"] is None and status["versions"] == [] and status["recent_runs"] == []
    assert status["quality_gate"]["min_roc_auc"] == 0.6 and status["mlflow"]["setting"] == "false"


def test_reason_is_validated(ml_env):
    response = client.post(URL, json={"reason": "x" * 501}, headers={"X-Admin-Key": KEY})
    assert response.status_code == 422
