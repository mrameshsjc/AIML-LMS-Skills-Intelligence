"""
Tests for training recommendations (Phase 7). No web server needed.

HOW TO RUN
    PS> pytest tests/unit/test_training_recommendation.py -v
"""

from dataclasses import replace

import pytest

from app.core.errors import InvalidInputError
from app.domain.models import CourseSkill
from app.repositories.csv_repository import CsvLmsRepository
from app.services.training_recommendation import (
    ENROLLED_STATUSES,
    TrainingRecommendationService,
    combine,
    level_fit,
    useful_gain,
)


@pytest.fixture(scope="module")
def repo() -> CsvLmsRepository:
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def service(repo) -> TrainingRecommendationService:
    return TrainingRecommendationService(repo)


# --- The scoring parts ------------------------------------------------------------


@pytest.mark.parametrize(
    "current, required, course_from, course_to, expected",
    [
        (2, 4, 2, 4, 2),  # exactly the gap
        (1, 3, 0, 2, 1),  # course ends below the requirement
        (1, 3, 2, 4, 1),  # course starts above the learner: only 2->3 counts
        (3, 4, 2, 4, 1),  # learner already past the start
        (2, 3, 0, 2, 0),  # course ends where the learner already is
    ],
)
def test_useful_gain(current, required, course_from, course_to, expected):
    assert useful_gain(current, required, CourseSkill("C", "S", course_from, course_to)) == expected


@pytest.mark.parametrize(
    "current, start, expected", [(2, 2, 1.0), (1, 2, 0.5), (0, 2, 0.0), (3, 2, 0.8), (5, 0, 0.5)]
)
def test_level_fit(current, start, expected):
    assert level_fit(current, start) == pytest.approx(expected)


def test_combine_shares_missing_weight_proportionally():
    score, weights = combine(
        {"gap_coverage": 1.0, "level_fit": 0.5, "prereq_ready": 0.0, "completion_probability": None}
    )
    assert set(weights) == {"gap_coverage", "level_fit", "prereq_ready"}
    assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)
    assert score == round((0.50 * 1.0 + 0.20 * 0.5) / 0.85, 2)


# --- The worked example (E1001 -> Data Engineer) ----------------------------------


def test_e1001_recommendations(service):
    result = service.recommend("E1001")
    ids = [r.course.course_id for r in result.recommendations]
    assert ids == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201"]
    top = result.recommendations[0]
    assert top.score == 1.0 and top.rank == 1
    assert top.reason.startswith("Your SQL is level 2 and Data Engineer needs level 4")
    assert result.target_role.title == "Data Engineer" and result.uncovered_skills == []


def test_completed_courses_are_never_recommended(service, repo):
    completed = {c for c, s in repo.get_training_status("E1001").items() if s == "Completed"}
    recommended = {r.course.course_id for r in service.recommend("E1001", max_results=30).recommendations}
    assert completed and not completed & recommended


def test_mandatory_gaps_come_before_optional_ones(service):
    recs = service.recommend("E1001").recommendations
    docker = next(r for r in recs if r.course.course_id == "C-DOCKER-201")
    aws_201 = next(r for r in recs if r.course.course_id == "C-AWS-201")
    assert docker.score > aws_201.score  # higher score...
    assert docker.rank > aws_201.rank  # ...but listed later: Docker is not mandatory for Data Engineer


def test_prerequisites_completed_skill_level_or_missing(service):
    recs = {r.course.course_id: r for r in service.recommend("E1001").recommendations}
    assert [(p.course_id, p.how) for p in recs["C-SQL-201"].prerequisites] == [("C-SQL-101", "completed")]
    assert [(p.course_id, p.how) for p in recs["C-DOCKER-201"].prerequisites] == [
        ("C-DOCKER-101", "skill level")
    ]
    aws = recs["C-AWS-201"]
    assert aws.prerequisites[0].satisfied is False and aws.components["prereq_ready"] == 0.0
    assert "Complete first: C-AWS-101" in aws.reason and "may be hard" in aws.reason


# --- Options ---------------------------------------------------------------------


def test_skill_filter_and_max_results(service):
    result = service.recommend("E1001", skills=["aws"], max_results=1)
    assert [r.course.course_id for r in result.recommendations] == ["C-AWS-101"]
    assert [g.skill_name for g in result.gaps] == ["AWS"]


def test_unknown_skill_filter(service):
    with pytest.raises(InvalidInputError):
        service.recommend("E1001", skills=["Cobol"])


def test_no_gaps_means_no_recommendations(service):
    result = service.recommend("E1001", target_role_id="R001")  # current role, fully met
    assert result.recommendations == [] and "nothing to recommend" in result.notes[0]


def test_include_enrolled_false_hides_enrolled_courses(service, repo):
    for employee_id in sorted(repo._employees):
        result = service.recommend(employee_id, max_results=30)
        enrolled = [
            r.course.course_id for r in result.recommendations if r.enrollment_status in ENROLLED_STATUSES
        ]
        if enrolled:
            hidden = service.recommend(employee_id, max_results=30, include_enrolled=False)
            assert not set(enrolled) & {r.course.course_id for r in hidden.recommendations}
            assert "already enrolled" in next(r.reason for r in result.recommendations if r.enrollment_status)
            return
    pytest.skip("no employee with a relevant enrolled course in the sample data")


def test_completion_model_hook_uses_all_four_weights(repo):
    service = TrainingRecommendationService(repo, completion_model=lambda employee, course: 0.5)
    result = service.recommend("E1001")
    top = result.recommendations[0]
    assert top.components["completion_probability"] == 0.5
    assert set(result.weights_used) == {"gap_coverage", "level_fit", "prereq_ready", "completion_probability"}
    assert top.score == pytest.approx(
        0.50 + 0.20 + 0.15 + 0.15 * 0.5, abs=0.006
    )  # 0.925, shown to 2 decimals
    assert not any("not available yet" in n for n in result.notes)


class NoAwsCoursesRepository(CsvLmsRepository):
    """Same data, but every AWS course is inactive."""

    def get_courses(self):
        return {
            cid: replace(c, is_active=not cid.startswith("C-AWS")) for cid, c in super().get_courses().items()
        }


def test_gap_without_any_course_is_reported():
    result = TrainingRecommendationService(NoAwsCoursesRepository()).recommend("E1001")
    assert result.uncovered_skills == ["AWS"]
    assert any("No available course closes the gap in: AWS" in n for n in result.notes)
    assert all(not r.course.course_id.startswith("C-AWS") for r in result.recommendations)
