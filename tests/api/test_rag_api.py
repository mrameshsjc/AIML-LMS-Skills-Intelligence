"""
API tests for GET /api/v1/health/rag (Phase 12). Each test uses its own
temporary index folder, never your vector_store/.

HOW TO RUN
    PS> pytest tests/api/test_rag_api.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.rag.embeddings import TfidfEmbedder
from app.rag.index import build_index
from app.rag.vector_store import NumpyVectorStore

client = TestClient(app)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()


def test_status_before_the_index_is_built(store):
    body = client.get("/api/v1/health/rag").json()
    assert body["ready"] is False and body["tenant"] == "default"
    assert "build_index.py" in body["detail"]


def test_status_after_building(store):
    build_index("documents", store / "default", TfidfEmbedder(), NumpyVectorStore)
    body = client.get("/api/v1/health/rag").json()
    assert body["ready"] is True and body["embedder"] == "tfidf" and body["backend"] == "numpy"
    sources = {d["source"] for d in body["documents"]}
    assert len(sources) == 8 and "mentoring_programme.docx" in sources
    assert body["chunk_count"] == sum(d["chunks"] for d in body["documents"])
