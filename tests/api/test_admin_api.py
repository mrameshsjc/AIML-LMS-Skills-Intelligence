"""
POST /api/v1/admin/reset-demo (Phase 19): administrators put the demo back to its
starting state. Temporary folders only - never your index, uploads or models.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.main import app
from tests.conftest import TEST_ADMIN_KEY

client = TestClient(app)
ADMIN = {"X-Admin-Key": TEST_ADMIN_KEY}


@pytest.fixture
def demo(tmp_path, monkeypatch):
    for name, value in {
        "VECTOR_STORE_DIR": str(tmp_path / "store"),
        "RAG_UPLOAD_DIR": str(tmp_path / "uploads"),
        "MODEL_DIR": str(tmp_path / "models"),
        "EMBEDDING_PROVIDER": "tfidf",
        "PREPARE_TRAIN_MODEL": "false",
        # never touch a developer's own database, even if their .env says DATA_SOURCE=database
        "DATA_SOURCE": "csv",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'db' / 'lms.db').as_posix()}",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    dependencies.get_knowledge_index.cache_clear()
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()
    for cache in (
        dependencies.get_knowledge_index,
        dependencies.get_repository,
        dependencies.get_completion_predictor,
    ):
        cache.cache_clear()


def test_reset_needs_an_administrator(demo):
    response = client.post("/api/v1/admin/reset-demo")
    assert response.status_code == 401 and response.json()["error"]["code"] == "ADMIN_AUTH_REQUIRED"


def test_reset_removes_uploads_and_rebuilds_the_index(demo):
    uploaded = client.post(
        "/api/v1/rag/ingest",
        files={"file": ("extra.md", b"# Extra\n\nKafka Essentials takes 12 hours.")},
        headers=ADMIN,
    )
    assert uploaded.status_code == 200 and uploaded.json()["index"]["documents"] == 9

    response = client.post("/api/v1/admin/reset-demo", headers=ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "reset" and body["requested_by"] == "admin"
    assert any(step.startswith("Document index: built: 8 documents") for step in body["steps"])
    sources = {d["source"] for d in client.get("/api/v1/rag/documents").json()["documents"]}
    assert "extra.md" not in sources and len(sources) == 8  # the API uses the new index at once
