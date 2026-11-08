"""
The container start step (Phase 18, app/core/prepare.py): a fresh, empty set
of volumes becomes a working system; a second start changes nothing.
"""

import sqlite3

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.prepare import (
    ensure_admin_account,
    ensure_database,
    ensure_folders,
    ensure_index,
    ensure_model,
    prepare,
    reset_demo,
)
from app.ml.model_registry import current_version
from app.rag.index import read_manifest
from app.security.users import UserStore


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
        mlflow_enabled="false",
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


# --- Phase 19: admin account, first model, reset -------------------------------------------------
def test_admin_account_is_created_once_from_the_secret(settings):
    assert ensure_admin_account(settings).startswith("skipped")
    with_secret = settings.model_copy(update={"bootstrap_admin_password": SecretStr("long-enough-pass-1")})
    assert ensure_admin_account(with_secret).startswith("created admin")
    assert UserStore(settings.users_file).authenticate("admin", "long-enough-pass-1").role == "admin"
    assert ensure_admin_account(with_secret) == "ready (admin)"


@pytest.mark.slow
def test_first_model_is_trained_only_when_asked(settings, tmp_path):
    assert ensure_model(settings).startswith("skipped")
    on = settings.model_copy(update={"prepare_train_model": True})
    assert ensure_model(on).startswith("promoted: version 1")
    assert current_version(tmp_path / "models") == 1 and ensure_model(on).startswith("ready")


def test_reset_puts_the_demo_back_to_the_start(settings, tmp_path):
    prepare(settings)
    upload = tmp_path / "uploads" / "documents" / "extra.md"
    upload.write_text("# Extra\n\nAn uploaded document.", encoding="utf-8")
    (tmp_path / "models" / "leftover.txt").write_text("x", encoding="utf-8")
    store = UserStore(settings.users_file)
    store.save("root", "long-enough-pass-1", "admin")
    lines = reset_demo(settings)
    assert lines[0].startswith("Removed:") and not upload.exists()
    assert not (tmp_path / "models" / "leftover.txt").exists()
    assert any(line.startswith("Database: created") for line in lines)  # rebuilt from the sample
    assert read_manifest(tmp_path / "store" / "default")["chunk_count"] > 0
    assert store.get("root") is not None  # accounts survive a reset
