"""
The container start step (Phase 18, app/core/prepare.py): a fresh, empty set
of volumes becomes a working system; a second start changes nothing.
"""

import sqlite3

import pytest

from app.core.config import Settings
from app.core.prepare import ensure_database, ensure_folders, ensure_index, prepare
from app.rag.index import read_manifest


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_source="database",
        database_url=f"sqlite:///{(tmp_path / 'db' / 'lms_ai.db').as_posix()}",
        vector_store_dir=str(tmp_path / "store"),
        rag_upload_dir=str(tmp_path / "uploads" / "documents"),
        model_dir=str(tmp_path / "models"),
        users_file=str(tmp_path / "accounts" / "users.json"),
        audit_log_file=str(tmp_path / "logs" / "audit.jsonl"),
        embedding_provider="tfidf",
        vector_backend="numpy",
    )


def test_folders_are_created_once(settings, tmp_path):
    created = ensure_folders(settings)
    assert len(created) == 5 and (tmp_path / "accounts").is_dir() and (tmp_path / "logs").is_dir()
    assert ensure_folders(settings) == []


def test_database_is_created_and_loaded_only_when_empty(settings, tmp_path):
    first = ensure_database(settings)
    assert first.startswith("created and loaded") and "11 tables" in first
    with sqlite3.connect(tmp_path / "db" / "lms_ai.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 100
    assert ensure_database(settings) == "ready"


def test_database_step_is_skipped_for_csv(settings):
    assert ensure_database(settings.model_copy(update={"data_source": "csv"})).startswith("skipped")


def test_index_is_built_once(settings, tmp_path):
    assert ensure_index(settings).startswith("built: 8 documents")
    assert read_manifest(tmp_path / "store" / "default")["embedder"]["name"] == "tfidf"
    assert ensure_index(settings).startswith("ready")


def test_prepare_reports_every_step_and_survives_an_index_failure(settings, monkeypatch):
    import app.core.prepare as module

    def broken(_settings):
        raise RuntimeError("Ollama stopped")

    monkeypatch.setattr(module, "ensure_index", broken)
    lines = prepare(settings)
    assert lines[0].startswith("Folders:") and lines[1].startswith("Database: created")
    assert "NOT built (Ollama stopped)" in lines[2]  # the API still starts


def test_prepare_can_be_switched_off(settings):
    assert prepare(settings.model_copy(update={"prepare_on_start": False})) == [
        "Start step skipped (PREPARE_ON_START=false)."
    ]
