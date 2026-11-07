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


# --- API 7: upload, list, delete (Phase 13) ------------------------------------------------------

CSV = b"training,provider,hours\nKafka Essentials,External Partner,12\n"


@pytest.fixture
def ingest_env(tmp_path, monkeypatch):
    from app.api import dependencies

    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("RAG_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tfidf")
    get_settings.cache_clear()
    dependencies.get_knowledge_index.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()
    dependencies.get_knowledge_index.cache_clear()


def _upload(name: str, content: bytes, overwrite: bool = False):
    return client.post(
        "/api/v1/rag/ingest", files={"file": (name, content)}, data={"overwrite": str(overwrite).lower()}
    )


def test_upload_list_chat_and_delete(ingest_env):
    response = _upload("internal_trainings.csv", CSV)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body["status"] == "added"
        and body["title"] == "Internal Trainings"
        and body["index"]["documents"] == 9
    )

    listing = client.get("/api/v1/rag/documents").json()
    origins = {d["source"]: d["origin"] for d in listing["documents"]}
    assert origins["internal_trainings.csv"] == "uploaded" and origins["faq.md"] == "base"

    answer = client.post("/api/v1/ai/chat", json={"question": "How long is Kafka Essentials?"}).json()
    assert answer["sources"][0]["source"] == "internal_trainings.csv"  # the new document is used at once

    deleted = client.delete("/api/v1/rag/documents/internal_trainings.csv")
    assert deleted.status_code == 200 and deleted.json()["status"] == "deleted"
    assert client.delete("/api/v1/rag/documents/internal_trainings.csv").status_code == 404


def test_upload_errors(ingest_env):
    assert _upload("internal_trainings.csv", CSV).status_code == 200
    conflict = _upload("internal_trainings.csv", CSV + b"x,y,1\n")
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "DOCUMENT_EXISTS"
    assert _upload("internal_trainings.csv", CSV + b"x,y,1\n", overwrite=True).json()["status"] == "updated"
    assert _upload("copy.csv", CSV + b"x,y,1\n").json()["error"]["code"] == "DUPLICATE_DOCUMENT"
    assert _upload("faq.md", b"# x\n\ny").json()["error"]["code"] == "DOCUMENT_IS_APPROVED"
    assert _upload("tool.exe", b"MZ").status_code == 422
    assert client.delete("/api/v1/rag/documents/faq.md").status_code == 409
