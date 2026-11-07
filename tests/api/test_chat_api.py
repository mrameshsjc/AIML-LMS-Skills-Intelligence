"""
API tests for API 5: POST /api/v1/ai/chat (Phase 13).

conftest.py sets LLM_PROVIDER=fallback, so answers list the facts (no model is
called). Each test builds its own temporary document index.

HOW TO RUN
    PS> pytest tests/api/test_chat_api.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.main import app
from app.rag.embeddings import TfidfEmbedder
from app.rag.index import build_index
from app.rag.vector_store import NumpyVectorStore

client = TestClient(app)
URL = "/api/v1/ai/chat"


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path))
    build_index("documents", tmp_path / "default", TfidfEmbedder(), NumpyVectorStore)
    get_settings.cache_clear()
    dependencies.get_knowledge_index.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()
    dependencies.get_knowledge_index.cache_clear()


def test_personal_question(index):
    response = client.post(URL, json={"question": "What are my current skill gaps?", "employee_id": "E1001"})
    assert response.status_code == 200
    body = response.json()
    assert "my_learning_path" in body["intents"] and body["provider"] == "fallback"
    assert "Gap (mandatory): SQL is level 2, Data Engineer needs level 4." in body["facts"]
    assert body["answer"].startswith("Fallback - no LLM")


def test_document_question_has_sources(index):
    body = client.post(URL, json={"question": "How many learning hours do I have per year?"}).json()
    assert body["sources"][0]["label"] == "S1" and body["sources"][0]["source"] == "faq.md"
    assert len(body["sources"][0]["excerpt"]) <= 300 and "40 hours" in body["answer"]


def test_role_question(index):
    body = client.post(URL, json={"question": "Which skills are required for an AI Engineer?"}).json()
    assert body["intents"][0] == "role_requirements"
    assert any("Prompt Engineering level 3" in f for f in body["facts"])


def test_no_information(index):
    body = client.post(URL, json={"question": "What is the capital of France?"}).json()
    assert body["provider"] == "none" and body["sources"] == [] and "don't have information" in body["answer"]


def test_history_is_accepted(index):
    payload = {
        "question": "And a second attempt?",
        "history": [
            {"role": "user", "content": "How much of the certification exam fee is reimbursed?"},
            {"role": "assistant", "content": "The first attempt in full."},
        ],
    }
    body = client.post(URL, json=payload).json()
    assert body["sources"][0]["source"] == "certification_reimbursement_policy.pdf"


def test_validation_and_unknown_employee(index):
    assert client.post(URL, json={"question": "x"}).status_code == 422  # too short
    assert client.post(URL, json={"question": "What are my gaps?", "employee_id": "1001"}).status_code == 422
    response = client.post(URL, json={"question": "What are my gaps?", "employee_id": "E9999"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"
