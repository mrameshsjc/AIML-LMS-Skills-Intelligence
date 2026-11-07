"""
API tests with DATA_SOURCE=database (Phase 9).

The same requests as the CSV tests must give the same answers when the API
reads from a SQLite database. Each test builds its own temporary database
and switches the settings to it, so your data/lms_ai.db is never touched.

HOW TO RUN
    PS> pytest tests/api/test_database_source.py -v
"""

from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.data_processing.loader import load_all
from app.database.connection import connect
from app.database.migrate import apply_migrations
from app.database.tables import save_datasets
from app.main import app
from app.repositories.sqlite_repository import SqliteLmsRepository

client = TestClient(app)


def _clear_caches() -> None:
    # Settings and the repository are created once and cached; clear them so the new settings apply.
    get_settings.cache_clear()
    dependencies.get_repository.cache_clear()


@pytest.fixture
def database_source(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'lms.db'}"
    with closing(connect(url, create_folder=True)) as conn:
        apply_migrations(conn)
        save_datasets(conn, load_all())
    monkeypatch.setenv("DATA_SOURCE", "database")
    monkeypatch.setenv("DATABASE_URL", url)
    _clear_caches()
    yield url
    monkeypatch.undo()  # back to the CSV settings for the other tests
    _clear_caches()


def test_setting_selects_the_database_repository(database_source):
    repository = dependencies.get_repository()
    assert isinstance(repository, SqliteLmsRepository)
    assert repository.database_url == database_source


def test_api_1_from_the_database(database_source):
    body = client.post(
        "/api/v1/skills/analyze", json={"employee_id": "E1001", "target_role_id": "R004"}
    ).json()
    assert body["gap_score"] == 37.5 and body["match_percentage"] == 62.5
    assert body["target_role"] == {"role_id": "R004", "title": "Data Engineer"}


def test_api_2_from_the_database(database_source):
    body = client.post("/api/v1/roles/match", json={"employee_id": "E1001"}).json()
    assert [m["title"] for m in body["matches"][:3]] == ["Software Developer", "QA Engineer", "Data Engineer"]


def test_api_3_from_the_database(database_source):
    body = client.post("/api/v1/trainings/recommend", json={"employee_id": "E1001"}).json()
    ids = [r["course_id"] for r in body["recommendations"]]
    assert ids == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201"]


def test_api_4_from_the_database(database_source):
    body = client.get("/api/v1/learning-path/E1001").json()
    assert [s["course_id"] for s in body["path"]][:2] == ["C-SQL-201", "C-PY-201"]
    assert body["progress"]["projected_match_percentage"] == 100.0


def test_unknown_employee_from_the_database(database_source):
    response = client.post("/api/v1/skills/analyze", json={"employee_id": "E9999", "target_role_id": "R004"})
    assert response.status_code == 404
    assert response.json()["error"]["code"]
