"""
Tests for the SQLite database layer (Phase 9). No web server needed.

Every test uses a temporary database file, never your data/lms_ai.db.

HOW TO RUN
    PS> pytest tests/unit/test_database.py -v
"""

import importlib.util
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

from app.data_processing.loader import PROJECT_ROOT, load_all
from app.data_processing.schemas import SCHEMAS
from app.database.connection import DatabaseNotReadyError, DatabaseUrlError, connect, sqlite_path
from app.database.migrate import applied_migrations, apply_migrations, available_migrations
from app.database.tables import LOAD_ORDER, read_datasets, save_datasets, table_counts, table_name
from app.ml.predict import CompletionPredictor
from app.ml.train import run_training
from app.repositories.csv_repository import CsvLmsRepository
from app.repositories.sqlite_repository import SqliteLmsRepository
from app.services.role_matching import RoleMatchingService
from app.services.skill_analysis import SkillAnalysisService
from app.services.training_recommendation import TrainingRecommendationService


@pytest.fixture(scope="module")
def datasets():
    return load_all()


@pytest.fixture(scope="module")
def db_url(tmp_path_factory, datasets) -> str:
    """A database with migrations applied and the sample data loaded."""
    url = f"sqlite:///{tmp_path_factory.mktemp('db') / 'lms.db'}"
    with closing(connect(url, create_folder=True)) as conn:
        apply_migrations(conn)
        save_datasets(conn, datasets)
    return url


@pytest.fixture
def memory_db():
    with closing(connect("sqlite:///:memory:")) as conn:
        apply_migrations(conn)
        yield conn


@pytest.fixture(scope="module")
def csv_repo() -> CsvLmsRepository:
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def db_repo(db_url) -> SqliteLmsRepository:
    return SqliteLmsRepository(db_url)


# --- Connection ----------------------------------------------------------------------


def test_sqlite_path_forms():
    assert sqlite_path("sqlite:///:memory:") == ":memory:"
    assert Path(sqlite_path("sqlite:///./data/lms_ai.db")) == PROJECT_ROOT / "data" / "lms_ai.db"
    absolute = PROJECT_ROOT / "x.db"
    assert Path(sqlite_path(f"sqlite:///{absolute}")) == absolute


def test_mysql_url_is_rejected_with_a_clear_message():
    with pytest.raises(DatabaseUrlError, match="SQLite only"):
        sqlite_path("mysql+pymysql://user:pw@localhost/lms_ai")


def test_missing_database_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="14_save_to_database"):
        connect(f"sqlite:///{tmp_path / 'none.db'}")


def test_foreign_keys_are_switched_on(memory_db):
    assert memory_db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# --- Migrations ------------------------------------------------------------------------


def test_migrations_run_once(memory_db):
    assert applied_migrations(memory_db) == [f.stem for f in available_migrations()]
    assert apply_migrations(memory_db) == []  # second run: nothing new


def test_tables_match_the_dataset_schemas(memory_db):
    for name in SCHEMAS:
        columns = [r["name"] for r in memory_db.execute(f"PRAGMA table_info({table_name(name)})")]
        assert columns == list(SCHEMAS[name].column_names), name
    assert set(LOAD_ORDER) == set(SCHEMAS)


def test_failed_migration_changes_nothing(tmp_path):
    (tmp_path / "0001_good.sql").write_text("CREATE TABLE a (x INTEGER);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE b (x INTEGER);\nTHIS IS NOT SQL;")
    with closing(connect("sqlite:///:memory:")) as conn:
        with pytest.raises(sqlite3.Error):
            apply_migrations(conn, tmp_path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "a" in tables and "b" not in tables  # 0002 rolled back completely
        assert applied_migrations(conn) == ["0001_good"]


# --- Saving and reading ------------------------------------------------------------------


def test_round_trip_gives_identical_dataframes(memory_db, datasets):
    save_datasets(memory_db, datasets)
    back = read_datasets(memory_db)
    for name, original in datasets.items():
        pd.testing.assert_frame_equal(back[name], original.reset_index(drop=True), obj=name)


def test_saving_twice_replaces_instead_of_adding(memory_db, datasets):
    save_datasets(memory_db, datasets)
    counts = save_datasets(memory_db, datasets)
    assert table_counts(memory_db) == counts
    assert counts["employee_skills"] == len(datasets["employee_skills.csv"])


def test_bad_data_is_refused_and_old_data_kept(memory_db, datasets):
    save_datasets(memory_db, datasets)
    broken = dict(datasets)
    skills = datasets["employee_skills.csv"].copy()
    skills.loc[0, "employee_id"] = "E9999"  # no such employee
    broken["employee_skills.csv"] = skills
    with pytest.raises(sqlite3.IntegrityError):
        save_datasets(memory_db, broken)
    assert table_counts(memory_db)["employee_skills"] == len(skills)  # the old rows are still there
    assert memory_db.execute("SELECT 1 FROM employee_skills WHERE employee_id = 'E9999'").fetchone() is None


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO employee_skills VALUES ('E9999', 'SK001', 3, 'self', '2026-10-01')",  # foreign key
        "INSERT INTO employee_skills VALUES ('E1001', 'SK042', 7, 'self', '2026-10-01')",  # level 1-5
        "INSERT INTO training_history VALUES ('EN9999', 'E1001', 'C-SQL-101', 'Paused', "
        "'2026-01-01', NULL, NULL, 1)",  # status
        "INSERT INTO courses VALUES ('C-X-101', 't', 'd', 'Beginner', 'ten', 'Online', 'p', 1)",  # STRICT
        "INSERT INTO course_skills VALUES ('C-SQL-101', 'SK002', 3, 2)",  # level_to > level_from
    ],
)
def test_constraints_refuse_bad_rows(memory_db, datasets, sql):
    save_datasets(memory_db, datasets)
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(sql)
    memory_db.rollback()


# --- Repository: same answers as the CSV version --------------------------------------------


def _same(a, b) -> bool:
    return a == b and (not isinstance(a, dict) or list(a) == list(b))  # same content AND same order


def test_repository_matches_csv_for_every_employee(csv_repo, db_repo):
    for employee_id in [*csv_repo._employees, "E9999"]:
        for method in ("get_employee", "get_employee_skills", "get_career_goal", "get_training_status"):
            assert _same(getattr(db_repo, method)(employee_id), getattr(csv_repo, method)(employee_id)), (
                method,
                employee_id,
            )


def test_repository_matches_csv_for_roles_courses_and_lists(csv_repo, db_repo):
    for role in [*(r.role_id for r in csv_repo.list_roles()), "R999"]:
        assert db_repo.get_role(role) == csv_repo.get_role(role)
        assert db_repo.get_role_requirements(role) == csv_repo.get_role_requirements(role)
    for course in [*csv_repo.get_courses(), "C-NONE-000"]:
        assert db_repo.get_course_skills(course) == csv_repo.get_course_skills(course)
        assert db_repo.get_prerequisites(course) == csv_repo.get_prerequisites(course)
    for method in ("list_roles", "get_skills", "get_courses"):
        assert _same(getattr(db_repo, method)(), getattr(csv_repo, method)()), method


def test_repository_needs_a_loaded_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    connect(url, create_folder=True).close()  # the file exists, but has no tables
    with pytest.raises(DatabaseNotReadyError, match="14_save_to_database"):
        SqliteLmsRepository(url)


def test_services_give_identical_results(csv_repo, db_repo):
    assert SkillAnalysisService(db_repo).analyze("E1001") == SkillAnalysisService(csv_repo).analyze("E1001")
    assert SkillAnalysisService(db_repo).analyze("E1001").summary.gap_score == 37.5
    assert RoleMatchingService(db_repo).match("E1001") == RoleMatchingService(csv_repo).match("E1001")
    for employee_id in ("E1001", "E1020", "E1050"):
        db = TrainingRecommendationService(db_repo).recommend(employee_id)
        assert db == TrainingRecommendationService(csv_repo).recommend(employee_id)


@pytest.mark.slow
def test_predictor_reads_features_from_the_database(db_url, tmp_path):
    run_training(models_dir=tmp_path)
    from_csv = CompletionPredictor.from_files(tmp_path)
    from_db = CompletionPredictor.from_database(tmp_path, db_url)
    courses = ["C-SQL-201", "C-AWS-101", "C-MLOPS-201"]
    assert from_db.predict_many("E1001", courses) == from_csv.predict_many("E1001", courses)


# --- Script 14 -----------------------------------------------------------------------------


def _run_14(*args: str) -> subprocess.CompletedProcess:
    script = PROJECT_ROOT / "data_science" / "14_save_to_database.py"
    return subprocess.run(
        [sys.executable, str(script), *args], cwd=PROJECT_ROOT, capture_output=True, text=True
    )


@pytest.mark.slow
def test_script_14_creates_the_database(tmp_path):
    result = _run_14("--db", str(tmp_path / "lms.db"))
    assert result.returncode == 0, result.stderr
    assert "gap score = 100 x 6 / 16 = 37.5" in result.stdout
    assert result.stdout.count("refused:") == 3
    again = _run_14("--db", str(tmp_path / "lms.db"))
    assert "nothing - the database was already up to date" in again.stdout


@pytest.mark.slow
def test_script_14_refuses_invalid_data(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "make_dirty_data", PROJECT_ROOT / "scripts" / "make_dirty_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.make_dirty(tmp_path / "dirty")
    result = _run_14("--data", str(tmp_path / "dirty"), "--db", str(tmp_path / "dirty.db"))
    assert result.returncode != 0
    assert not (tmp_path / "dirty.db").exists()
