"""
Integration tests: the services work TOGETHER and never contradict each other (Phase 14).

The requirements describe one business flow:
    profile -> skills analysis (API 1) -> role matching (API 2) -> recommendations (API 3)
            -> learning path (API 4) -> assistant (API 5), with documents from API 7.

Unit tests check each step alone. These tests check the HAND-OVERS between the
steps, for every employee: the same gap score in APIs 1 and 2, the same course
scores in APIs 3 and 4, the assistant repeating API 4's next action, and the
same answers from the CSV files and the database. A contradiction between two
APIs would confuse users more than a wrong number in one of them.

HOW TO RUN
    PS> pytest tests/integration -v
    PS> pytest -m "not slow"          (skip the slower all-employee sweeps)
"""

from contextlib import closing

import pytest

from app.data_processing.loader import load_all
from app.database.connection import connect
from app.database.migrate import apply_migrations
from app.database.tables import save_datasets
from app.llm.fallback_provider import FallbackProvider
from app.rag.embeddings import TfidfEmbedder
from app.rag.index import KnowledgeIndex, build_index
from app.rag.vector_store import NumpyVectorStore
from app.repositories.csv_repository import CsvLmsRepository
from app.repositories.sqlite_repository import SqliteLmsRepository
from app.services.chat_service import ChatService
from app.services.ingestion_service import IngestionService
from app.services.learning_path import GAP, LearningPathService
from app.services.role_matching import RoleMatchingService
from app.services.skill_analysis import SkillAnalysisService
from app.services.training_recommendation import TrainingRecommendationService


@pytest.fixture(scope="module")
def repo():
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def services(repo):
    return {
        "skills": SkillAnalysisService(repo),
        "roles": RoleMatchingService(repo),
        "recs": TrainingRecommendationService(repo),
        "path": LearningPathService(repo),
    }


@pytest.fixture(scope="module")
def employees(repo):
    return sorted(repo._employees)


# --- The worked example, end to end ------------------------------------------------------------


def test_e1001_flow_from_profile_to_next_action(repo, services):
    analysis = services["skills"].analyze("E1001")
    assert analysis.target_role.title == "Data Engineer" and analysis.summary.gap_score == 37.5

    roles = services["roles"].match("E1001")
    assert roles.target.role.title == "Data Engineer" and roles.target.match_percentage == 62.5

    recs = services["recs"].recommend("E1001")
    assert recs.gap_score == analysis.summary.gap_score
    assert {g.skill_name for g in recs.gaps} == {g.skill_name for g in analysis.summary.gaps}

    path = services["path"].build("E1001")
    assert [s.course.course_id for s in path.steps] == [r.course.course_id for r in recs.recommendations]
    assert path.progress.match_percentage == analysis.summary.match_percentage
    assert path.next_action.startswith(f"Enrol in {recs.recommendations[0].course.course_id}")

    answer = ChatService(repo, FallbackProvider()).ask("Which courses should I complete next?", "E1001")
    assert f"Next action: {path.next_action}" in answer.facts


# --- Consistency between the APIs, for every employee ---------------------------------------------


def test_api1_and_api2_agree_for_every_employee(services, employees):
    for employee_id in employees:
        analysis = services["skills"].analyze(employee_id)
        target = services["roles"].match(employee_id, target_role_id=analysis.target_role.role_id).target
        assert target.summary.gap_score == analysis.summary.gap_score, employee_id
        assert target.match_percentage == analysis.summary.match_percentage, employee_id


def test_api3_and_api4_agree_for_every_employee(services, employees):
    for employee_id in employees:
        recs = services["recs"].recommend(employee_id, max_results=1000)
        scores = {r.course.course_id: r.score for r in recs.recommendations}
        path = services["path"].build(employee_id)
        assert path.progress.match_percentage == recs.match_percentage
        assert {g.gap.skill_name for g in path.gaps} == {g.skill_name for g in recs.gaps}
        for step in path.steps:
            if step.score is not None:  # a course from API 3's list keeps API 3's score
                assert step.score == scores[step.course.course_id], (employee_id, step.course.course_id)
            if step.purpose == GAP and step.score is not None:
                assert step.reason.startswith(
                    next(
                        r.reason for r in recs.recommendations if r.course.course_id == step.course.course_id
                    )
                )
        assert not ({s.course.course_id for s in path.steps} & set(recs.uncovered_skills))


def test_completed_courses_never_come_back(repo, services, employees):
    for employee_id in employees:
        completed = {c for c, s in repo.get_training_status(employee_id).items() if s == "Completed"}
        recommended = {
            r.course.course_id
            for r in services["recs"].recommend(employee_id, max_results=1000).recommendations
        }
        in_path = {s.course.course_id for s in services["path"].build(employee_id).steps}
        assert not completed & (recommended | in_path), employee_id


def test_assistant_uses_the_same_numbers_as_the_apis(repo, services):
    chat = ChatService(repo, FallbackProvider())
    for employee_id in ("E1001", "E1003", "E1020"):
        path = services["path"].build(employee_id)
        facts = chat.ask("What are my current skill gaps?", employee_id).facts
        assert f"Next action: {path.next_action}" in facts
        for g in path.gaps:
            assert any(f"{g.gap.skill_name} is level {g.gap.current_level}" in f for f in facts)


# --- CSV and database give the same results through every service -------------------------------------


@pytest.fixture(scope="module")
def db_repo(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('db') / 'lms.db'}"
    with closing(connect(url, create_folder=True)) as conn:
        apply_migrations(conn)
        save_datasets(conn, load_all())
    return SqliteLmsRepository(url)


def test_csv_and_database_flows_are_identical(repo, db_repo, employees):
    csv_flow = (SkillAnalysisService(repo), TrainingRecommendationService(repo), LearningPathService(repo))
    db_flow = (
        SkillAnalysisService(db_repo),
        TrainingRecommendationService(db_repo),
        LearningPathService(db_repo),
    )
    for employee_id in employees[::10]:  # every tenth employee keeps the test quick
        assert db_flow[0].analyze(employee_id) == csv_flow[0].analyze(employee_id)
        assert db_flow[1].recommend(employee_id) == csv_flow[1].recommend(employee_id)
        assert db_flow[2].build(employee_id) == csv_flow[2].build(employee_id)


# --- Documents: upload, ask, delete ---------------------------------------------------------------------


def test_uploaded_document_reaches_the_assistant_and_leaves_again(repo, tmp_path):
    index_dir = tmp_path / "store" / "default"
    build_index("documents", index_dir, TfidfEmbedder(), NumpyVectorStore)
    cache: dict = {}

    def load():
        if "index" not in cache:
            cache["index"] = KnowledgeIndex.load(index_dir)
        return cache["index"]

    ingestion = IngestionService(
        "documents",
        tmp_path / "uploads",
        index_dir,
        lambda: (TfidfEmbedder(), []),
        NumpyVectorStore,
        on_change=cache.clear,
    )
    chat = ChatService(repo, FallbackProvider(), load, lambda index: 0.08)
    question = "How many hours does the Kafka Essentials training take?"
    assert all(s.source != "internal_trainings.csv" for s in chat.ask(question).sources)

    ingestion.ingest("internal_trainings.csv", b"training,hours\nKafka Essentials,12\nSpark Bootcamp,24\n")
    answer = chat.ask(question)
    assert answer.sources[0].source == "internal_trainings.csv" and "hours: 12" in answer.answer

    ingestion.delete("internal_trainings.csv")
    assert all(s.source != "internal_trainings.csv" for s in chat.ask(question).sources)
