"""
Tests for skill analysis (Phase 5): the gap formula, the service, the CSV
repository and the request/response schemas. No web server needed.

HOW TO RUN
    PS> pytest tests/unit/test_skill_analysis.py -v
"""

import pytest
from pydantic import ValidationError

from app.core.errors import InvalidInputError, NotFoundError
from app.domain.models import RoleRequirement, Skill
from app.repositories.csv_repository import CsvLmsRepository
from app.schemas.skills import SkillAnalysisRequest
from app.services.skill_analysis import BELOW, MET, MISSING, SkillAnalysisService, compute_gaps

SKILLS = {sid: Skill(sid, name, "Test") for sid, name in [("S1", "Alpha"), ("S2", "Beta"), ("S3", "Gamma")]}


@pytest.fixture(scope="module")
def repo() -> CsvLmsRepository:
    return CsvLmsRepository()  # data/sample


@pytest.fixture(scope="module")
def service(repo) -> SkillAnalysisService:
    return SkillAnalysisService(repo)


# --- The pure formula -------------------------------------------------------


def test_compute_gaps_statuses_and_scores():
    reqs = [RoleRequirement("S1", 4), RoleRequirement("S2", 2), RoleRequirement("S3", 3, mandatory=False)]
    result = compute_gaps({"S1": 2, "S2": 5}, reqs, SKILLS)
    by_name = {g.skill_name: g for g in result.skills}
    assert (by_name["Alpha"].gap, by_name["Alpha"].status) == (2, BELOW)
    assert (by_name["Beta"].gap, by_name["Beta"].status) == (0, MET)  # above requirement: no extra credit
    assert (by_name["Gamma"].gap, by_name["Gamma"].status) == (3, MISSING)
    # required 4+2+3 = 9; gaps 2+0+3 = 5; covered 2+2+0 = 4
    assert result.gap_score == round(100 * 5 / 9, 1)
    assert result.match_percentage == round(100 * 4 / 9, 1)


def test_compute_gaps_orders_mandatory_then_largest_gap():
    reqs = [RoleRequirement("S1", 2, mandatory=False), RoleRequirement("S2", 3), RoleRequirement("S3", 5)]
    order = [g.skill_name for g in compute_gaps({}, reqs, SKILLS).skills]
    assert order == ["Gamma", "Beta", "Alpha"]


def test_compute_gaps_uses_weights():
    reqs = [RoleRequirement("S1", 4, weight=3.0), RoleRequirement("S2", 4, weight=1.0)]
    result = compute_gaps({"S1": 4}, reqs, SKILLS)  # heavy skill met, light skill missing
    assert result.gap_score == 25.0 and result.match_percentage == 75.0


def test_compute_gaps_with_no_requirements_is_ready():
    result = compute_gaps({"S1": 3}, [], SKILLS)
    assert (result.gap_score, result.match_percentage, result.gaps) == (0.0, 100.0, [])


# --- The worked example from the requirements ------------------------------


def test_data_engineer_example(service):
    result = service.analyze("E1001", "R004")
    assert result.target_role.title == "Data Engineer" and result.target_source == "request"
    assert result.summary.gap_score == 37.5
    assert result.summary.match_percentage == 62.5
    gaps = {g.skill_name: (g.current_level, g.required_level, g.gap) for g in result.summary.skills}
    assert gaps == {
        "Python": (3, 4, 1),
        "SQL": (2, 4, 2),
        "AWS": (1, 3, 2),
        "Machine Learning": (2, 2, 0),
        "Docker": (2, 3, 1),
    }
    assert result.mandatory_gaps == 3 and not result.role_ready and result.missing_skills == []
    assert result.suggestions[0] == "Raise AWS (mandatory) from level 1 to 3."
    assert result.explanation.startswith("Arjun Krishnan meets 1 of 5 skill requirements for Data Engineer")


def test_profile_lists_all_skills_with_target_flag(service):
    profile = service.analyze("E1001", "R004").skill_profile
    assert len(profile) == 10
    assert {p.skill_name for p in profile if p.required_for_target} == {
        "Python", "SQL", "AWS", "Machine Learning", "Docker",
    }  # fmt: skip


# --- Choosing the target role ----------------------------------------------


def test_target_defaults_to_career_goal(service):
    result = service.analyze("E1001")
    assert result.target_source == "career_goal" and result.target_role.role_id == "R004"


def test_target_falls_back_to_current_role(service, repo):
    no_goal = next(e for e in sorted(repo._employees) if repo.get_career_goal(e) is None)
    result = service.analyze(no_goal)
    assert result.target_source == "current_role"
    assert result.target_role.role_id == repo.get_employee(no_goal).current_role_id


# --- What-if overrides --------------------------------------------------------


def test_overrides_by_name_or_id_close_the_gaps(service):
    result = service.analyze("E1001", "R004", {"sql": 4, "SK001": 4, "AWS": 3, "Docker": 3})
    assert result.role_ready and result.summary.gap_score == 0.0
    assert result.overrides_applied == ["SQL = 4", "Python = 4", "AWS = 3", "Docker = 3"]
    assert result.suggestions == ["You meet every skill requirement for Data Engineer."]


def test_override_to_zero_makes_a_skill_missing(service, repo):
    result = service.analyze("E1001", "R004", {"Machine Learning": 0})
    assert "Machine Learning" in result.missing_skills
    assert repo.get_employee_skills("E1001")["SK031"] == 2  # stored data unchanged


# --- Errors -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "args, error, code",
    [
        (("E9999", "R004"), NotFoundError, "EMPLOYEE_NOT_FOUND"),
        (("E1001", "R999"), NotFoundError, "ROLE_NOT_FOUND"),
        (("E1001", "R004", {"Cobol": 3}), InvalidInputError, "UNKNOWN_SKILL"),
        (("E1001", "R004", {"SQL": 7}), InvalidInputError, "INVALID_LEVEL"),
    ],
)
def test_errors_have_codes(service, args, error, code):
    with pytest.raises(error) as caught:
        service.analyze(*args)
    assert caught.value.code == code


# --- Repository --------------------------------------------------------------------


def test_csv_repository_returns_domain_objects(repo):
    assert repo.get_employee("E1001").full_name == "Arjun Krishnan"
    assert repo.get_employee("E9999") is None
    assert len(repo.list_roles()) == 13
    assert len(repo.get_skills()) == 42
    assert repo.get_role_requirements("R999") == []


def test_repository_returns_copies(repo):
    skills = repo.get_employee_skills("E1001")
    skills["SK001"] = 5
    assert repo.get_employee_skills("E1001")["SK001"] == 3


# --- Request schema ----------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"employee_id": "1001"},
        {"employee_id": "E1001", "target_role_id": "Data Engineer"},
        {"employee_id": "E1001", "current_skills": [{"skill": "SQL", "level": 6}]},
        {"employee_id": "E1001", "current_skills": [{"skill": "", "level": 3}]},
    ],
)
def test_request_schema_rejects_bad_input(payload):
    with pytest.raises(ValidationError):
        SkillAnalysisRequest(**payload)


def test_request_schema_accepts_minimal_input():
    assert SkillAnalysisRequest(employee_id="E1001").target_role_id is None
