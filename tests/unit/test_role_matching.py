"""
Tests for role matching and TF-IDF role similarity (Phase 6). No web server needed.

HOW TO RUN
    PS> pytest tests/unit/test_role_matching.py -v
"""

import pytest

from app.core.errors import NotFoundError
from app.domain.models import JobRole, RoleRequirement
from app.repositories.csv_repository import CsvLmsRepository
from app.services.role_matching import RoleMatchingService, explain_match, readiness
from app.services.role_similarity import RoleSimilarityIndex, role_document
from app.services.skill_analysis import SkillAnalysisService, compute_gaps


@pytest.fixture(scope="module")
def repo() -> CsvLmsRepository:
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def service(repo) -> RoleMatchingService:
    return RoleMatchingService(repo)


# --- Ranking -------------------------------------------------------------------


def test_e1001_ranking(service):
    result = service.match("E1001")
    titles = [m.role.title for m in result.matches]
    assert titles[:3] == ["Software Developer", "QA Engineer", "Data Engineer"]
    assert result.matches[0].is_current_role and result.matches[0].readiness == "Ready"
    assert result.roles_considered == 13 and len(result.matches) == 5


def test_ties_are_broken_by_fewer_mandatory_gaps(service):
    qa, data_engineer = service.match("E1001").matches[1:3]
    assert qa.match_percentage == data_engineer.match_percentage == 62.5
    assert qa.mandatory_gaps < data_engineer.mandatory_gaps


def test_matches_are_sorted_and_ranked(service):
    matches = service.match("E1050", top_n=13).matches
    assert [m.rank for m in matches] == list(range(1, 14))
    assert [m.match_percentage for m in matches] == sorted(
        (m.match_percentage for m in matches), reverse=True
    )


def test_same_numbers_as_skill_analysis(service, repo):
    """Role matching and API 1 must never disagree."""
    analysis = SkillAnalysisService(repo)
    for match in service.match("E1020", top_n=13).matches:
        expected = analysis.analyze("E1020", match.role.role_id).summary
        assert (match.match_percentage, match.summary.gap_score) == (
            expected.match_percentage,
            expected.gap_score,
        )


# --- Target, subsets and overrides ---------------------------------------------


def test_target_defaults_to_career_goal_and_is_always_reported(service):
    result = service.match("E1001", top_n=1)
    assert result.target.role.title == "Data Engineer" and result.target.rank == 3
    assert all(m.role.title != "Data Engineer" for m in result.matches)  # outside top 1, still reported


def test_role_subset(service):
    result = service.match("E1001", role_ids=["R004", "R002", "R004"])
    assert [m.role.role_id for m in result.matches] == ["R004", "R002"]  # repeats removed, ranked
    assert result.roles_considered == 2


def test_target_outside_subset_has_rank_zero(service):
    result = service.match("E1001", role_ids=["R002"], target_role_id="R006")
    assert result.target.rank == 0 and "not in the compared roles" in result.summary


def test_what_if_levels_change_the_ranking(service):
    result = service.match("E1001", skill_overrides={"SQL": 4, "Python": 4, "AWS": 3, "Docker": 3})
    data_engineer = next(m for m in result.matches if m.role.title == "Data Engineer")
    assert data_engineer.readiness == "Ready" and len(result.overrides_applied) == 4


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"employee_id": "E9999"}, "EMPLOYEE_NOT_FOUND"),
        ({"employee_id": "E1001", "role_ids": ["R999"]}, "ROLE_NOT_FOUND"),
        ({"employee_id": "E1001", "target_role_id": "R999"}, "ROLE_NOT_FOUND"),
    ],
)
def test_not_found(service, kwargs, code):
    with pytest.raises(NotFoundError) as caught:
        service.match(**kwargs)
    assert caught.value.code == code


def test_employee_without_goal_gets_related_roles_for_best_new_role(service, repo):
    no_goal = next(e for e in sorted(repo._employees) if repo.get_career_goal(e) is None)
    result = service.match(no_goal)
    assert result.career_goal is None and result.target is None
    best_new = next(m for m in result.matches if not m.is_current_role)
    assert result.related_to.role_id == best_new.role.role_id


# --- Labels and explanations -------------------------------------------------------


@pytest.mark.parametrize(
    "pct, label", [(100, "Ready"), (99.9, "Close"), (80, "Close"), (50, "Developing"), (49.9, "Early")]
)
def test_readiness_bands(pct, label):
    assert readiness(pct) == label


def test_explanation_lists_top_gaps():
    reqs = [RoleRequirement(f"S{i}", 3) for i in range(5)]
    text = explain_match(compute_gaps({"S0": 3, "S1": 1}, reqs, {}))
    assert text.startswith("Meets 1 of 5 skills; gaps:")
    assert "(+1 more)" in text and "missing->3" in text and "4 mandatory gaps." in text


# --- TF-IDF similarity ---------------------------------------------------------------


def test_role_document_repeats_skills_by_level():
    assert role_document([RoleRequirement("A", 2), RoleRequirement("B", 1)]) == "A A B"


def test_similarity_matrix_properties(repo):
    roles = repo.list_roles()
    index = RoleSimilarityIndex(roles, {r.role_id: repo.get_role_requirements(r.role_id) for r in roles})
    sim = index.similarity
    assert sim.shape == (13, 13)
    assert (abs(sim - sim.T) < 1e-9).all()  # A~B equals B~A
    assert all(abs(sim[i, i] - 1) < 1e-9 for i in range(13))  # every role is identical to itself


def test_related_roles_for_data_engineer(service):
    related = service.match("E1001", target_role_id="R004").related_roles
    first = related[0]
    assert first.similar.role.title == "Machine Learning Engineer" and first.similar.similarity > 0.6
    assert {"Python", "SQL", "AWS"} <= set(first.shared_skill_names)
    assert [r.similar.similarity for r in related] == sorted(
        (r.similar.similarity for r in related), reverse=True
    )


def test_rare_skills_count_more_than_common_ones():
    """IDF: two roles sharing a RARE skill are more similar than two sharing a COMMON one."""
    roles = [JobRole(f"R{i}", f"Role {i}", "", "", "") for i in range(4)]
    reqs = {
        "R0": [RoleRequirement("COMMON", 3), RoleRequirement("RARE", 3)],
        "R1": [RoleRequirement("COMMON", 3), RoleRequirement("RARE", 3), RoleRequirement("X", 3)],
        "R2": [RoleRequirement("COMMON", 3), RoleRequirement("Y", 3)],
        "R3": [RoleRequirement("COMMON", 3), RoleRequirement("Z", 3)],
    }
    index = RoleSimilarityIndex(roles, reqs)
    scores = {s.role.role_id: s.similarity for s in index.similar_to("R0", top_n=3, min_similarity=0)}
    assert scores["R1"] > scores["R2"] and scores["R1"] > scores["R3"]


def test_unknown_role_has_no_similar_roles(repo):
    roles = repo.list_roles()
    index = RoleSimilarityIndex(roles, {r.role_id: repo.get_role_requirements(r.role_id) for r in roles})
    assert index.similar_to("R999") == []
