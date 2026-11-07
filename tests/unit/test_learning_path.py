"""
Tests for the personalised learning path (Phase 10). No web server needed.

HOW TO RUN
    PS> pytest tests/unit/test_learning_path.py -v
"""

from contextlib import closing

import pytest

from app.core.errors import NotFoundError
from app.data_processing.loader import load_all
from app.database.connection import connect
from app.database.migrate import apply_migrations
from app.database.tables import save_datasets
from app.repositories.csv_repository import CsvLmsRepository
from app.repositories.sqlite_repository import SqliteLmsRepository
from app.services.learning_path import GAP, PREREQUISITE, LearningPathService
from app.services.training_recommendation import TrainingRecommendationService


@pytest.fixture(scope="module")
def repo() -> CsvLmsRepository:
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def service(repo) -> LearningPathService:
    return LearningPathService(repo)


@pytest.fixture(scope="module")
def e1001(service):
    return service.build("E1001")


def _ids(path) -> list[str]:
    return [s.course.course_id for s in path.steps]


# --- The worked example (E1001 -> Data Engineer) -------------------------------------


def test_e1001_sequence(e1001):
    assert e1001.target_role.title == "Data Engineer" and e1001.target_source == "career_goal"
    assert _ids(e1001) == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201"]
    aws_201 = e1001.steps[3]
    assert aws_201.after_steps == [3] and aws_201.ready_now is False
    assert "step 3 (C-AWS-101) comes first" in aws_201.reason
    assert all(s.purpose == GAP for s in e1001.steps)


def test_e1001_gaps_and_progress(e1001):
    aws = next(g for g in e1001.gaps if g.gap.skill_name == "AWS")
    assert aws.closed_by == ["C-AWS-101", "C-AWS-201"] and aws.level_after_path == 3
    progress = e1001.progress
    assert progress.match_percentage == 62.5 and progress.projected_match_percentage == 100.0
    assert (progress.skills_met, progress.skills_required) == (1, 5)
    assert progress.total_steps == 5 and progress.total_hours == 90
    assert progress.total_hours == sum(s.course.duration_hours for s in e1001.steps)
    assert {c.course_id for c in progress.completed_courses} == {"C-PY-101", "C-SQL-101"}


def test_e1001_next_action(e1001):
    assert e1001.next_action.startswith("Enrol in C-SQL-201 'SQL for Data Engineering' (step 1, 21 h).")


def test_scores_and_reasons_match_api_3(repo, e1001):
    api3 = {
        r.course.course_id: r for r in TrainingRecommendationService(repo).recommend("E1001").recommendations
    }
    for step in e1001.steps:
        assert step.score == api3[step.course.course_id].score
        assert step.reason.startswith(api3[step.course.course_id].reason)


# --- Rules that must hold for every employee and every target role ---------------------------


def test_path_rules_for_all_employees_and_roles(repo, service):
    roles = [r.role_id for r in repo.list_roles()]
    for employee_id in repo._employees:
        history = repo.get_training_status(employee_id)
        for role_id in roles:
            path = service.build(employee_id, role_id)
            ids = _ids(path)
            position = {cid: i for i, cid in enumerate(ids)}
            assert len(ids) == len(set(ids)), "a course appears twice"
            for step in path.steps:
                assert history.get(step.course.course_id) != "Completed"
                assert step.course.is_active
                assert all(before < step.step for before in step.after_steps)
                for p in step.prerequisites:  # an unmet prerequisite in the path always comes earlier
                    if not p.satisfied and p.course_id in position:
                        assert position[p.course_id] < position[step.course.course_id]
            for g in path.gaps:  # every gap is closed, or reported as uncovered
                assert g.level_after_path == g.gap.required_level or g.gap.skill_name in path.uncovered_skills
            if not path.uncovered_skills:
                assert path.progress.projected_match_percentage == 100.0


# --- Special cases ----------------------------------------------------------------------------


def test_missing_prerequisite_is_added_just_before(service):
    path = service.build("E1003", "R004")
    ids = _ids(path)
    stats = path.steps[ids.index("C-STATS-101")]
    assert stats.purpose == PREREQUISITE and "C-ML-101" in stats.reason
    assert ids.index("C-STATS-101") == ids.index("C-ML-101") - 1  # placed just in time


def test_courses_in_progress_are_kept_with_status(service):
    path = service.build("E1003", "R004")
    aws_101 = next(s for s in path.steps if s.course.course_id == "C-AWS-101")
    assert aws_101.status == "Enrolled"
    assert aws_101.course in path.progress.in_progress_courses
    assert next(s for s in path.steps if s.course.course_id == "C-AWS-201").status == "Dropped before"


def test_next_action_continues_a_started_course(service):
    path = service.build("E1008", "R012")
    assert path.steps[0].status == "In Progress"
    assert path.next_action.startswith("Continue C-COMM-150")


def test_completed_course_counts_as_evidence(service):
    path = service.build("E1003", "R003")  # Python record 0, but C-PY-101 (0->2) completed
    py_201 = next(s for s in path.steps if s.course.course_id == "C-PY-201")
    assert py_201.score is None and "builds on C-PY-101" in py_201.reason
    assert "Python" not in path.uncovered_skills
    assert any("skill re-assessment" in n for n in path.notes)


def test_no_gaps_means_empty_path(service):
    path = service.build("E1001", "R001")  # the current role, fully met
    assert path.steps == [] and path.progress.projected_match_percentage == 100.0
    assert path.next_action.startswith("You already meet every requirement for Software Developer")


def test_optional_skills_can_be_left_out(service, e1001):
    path = service.build("E1001", include_optional=False)
    assert _ids(path) == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201"]  # Docker is optional
    assert any("include_optional=false" in n for n in path.notes)


def test_uncovered_skill_is_reported(service):
    path = service.build("E1001", "R003")
    assert "Advanced Excel" in path.uncovered_skills
    assert any("Advanced Excel (reaches level 3 of 4)" in n for n in path.notes)
    assert path.progress.projected_match_percentage < 100


def test_without_a_career_goal_the_current_role_is_used(service):
    path = service.build("E1005")
    assert path.target_source == "current_role"
    assert any("Pass target_role_id" in n for n in path.notes)


def test_unknown_employee_or_role(service):
    with pytest.raises(NotFoundError):
        service.build("E9999")
    with pytest.raises(NotFoundError):
        service.build("E1001", "R999")


def test_same_path_from_the_database(tmp_path, service):
    url = f"sqlite:///{tmp_path / 'lms.db'}"
    with closing(connect(url, create_folder=True)) as conn:
        apply_migrations(conn)
        save_datasets(conn, load_all())
    from_db = LearningPathService(SqliteLmsRepository(url))
    for employee_id in ("E1001", "E1003", "E1008"):
        assert from_db.build(employee_id) == service.build(employee_id)
