"""
API tests for the language model parts (Phase 11): GET /api/v1/health/llm and
API 4 with ?explain=true. conftest.py sets LLM_PROVIDER=fallback, so these
tests never call a real model.

HOW TO RUN
    PS> pytest tests/api/test_llm_api.py -v
"""

from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.llm.base import LLMResult
from app.main import app

client = TestClient(app)


def test_llm_status_with_the_fallback():
    body = client.get("/api/v1/health/llm").json()
    assert body["setting"] == "fallback" and body["provider"] == "fallback"
    assert body["available"] is True and body["models_installed"] == []


def test_learning_path_without_explanation_by_default():
    assert client.get("/api/v1/learning-path/E1001").json()["explanation"] is None


def test_learning_path_explained_by_the_fallback():
    body = client.get("/api/v1/learning-path/E1001", params={"explain": "true"}).json()
    explanation = body["explanation"]
    assert explanation["provider"] == "fallback" and explanation["is_fallback"] is True
    assert explanation["text"].startswith("Fallback - no LLM")
    assert any(f.startswith("Next action: Enrol in C-SQL-201") for f in explanation["facts"])


class FakeModel:
    name, model = "ollama", "fake-model"

    def generate(self, request):
        return LLMResult("Start with C-SQL-201, then take C-NOSUCH-101.", "ollama", "fake-model")

    def status(self):
        raise NotImplementedError


def test_learning_path_explained_by_a_model_with_grounding_check():
    app.dependency_overrides[get_llm_provider] = FakeModel
    try:
        body = client.get("/api/v1/learning-path/E1001", params={"explain": "true"}).json()
    finally:
        app.dependency_overrides.clear()
    explanation = body["explanation"]
    assert explanation["provider"] == "ollama" and explanation["model"] == "fake-model"
    assert "C-NOSUCH-101" in explanation["grounding_warnings"][0]
