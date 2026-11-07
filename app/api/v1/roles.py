"""
API 2 - Job Role Matching: POST /api/v1/roles/match

PURPOSE
    Rank job roles for an employee by how well their skills match, explain
    each match, and suggest related roles (TF-IDF similarity of required skills).
    All logic lives in app/services/role_matching.py; this file only converts
    the request and the result.

ERRORS (shared format)
    404 EMPLOYEE_NOT_FOUND / ROLE_NOT_FOUND
    422 VALIDATION_ERROR, UNKNOWN_SKILL, INVALID_LEVEL
"""

import re

from fastapi import APIRouter

from app.api.dependencies import RoleMatchingServiceDep
from app.core.config import get_settings
from app.core.errors import InvalidInputError
from app.schemas.common import ErrorResponse, RoleRef
from app.schemas.roles import (
    RelatedRoleOut,
    RoleMatchOut,
    RoleMatchRequest,
    RoleMatchResponse,
    SkillShortfall,
)
from app.services.role_matching import RoleMatch, RoleMatchResult
from app.services.skill_analysis import BELOW, MET, MISSING

router = APIRouter(prefix="/roles", tags=["2. Job Role Matching"])
ROLE_ID = re.compile(r"^R\d{3}$")


def _shortfalls(match: RoleMatch, status: str) -> list[SkillShortfall]:
    return [
        SkillShortfall(
            skill=g.skill_name,
            current_level=g.current_level,
            required_level=g.required_level,
            mandatory=g.mandatory,
        )
        for g in match.skills_with(status)
    ]


def _match_out(match: RoleMatch) -> RoleMatchOut:
    return RoleMatchOut(
        rank=match.rank,
        role_id=match.role.role_id,
        title=match.role.title,
        department=match.role.department,
        seniority=match.role.seniority,
        match_percentage=match.match_percentage,
        gap_score=match.summary.gap_score,
        readiness=match.readiness,
        is_current_role=match.is_current_role,
        is_career_goal=match.is_career_goal,
        matching_skills=[g.skill_name for g in match.skills_with(MET)],
        needs_improvement=_shortfalls(match, BELOW),
        missing_skills=_shortfalls(match, MISSING),
        mandatory_gaps=match.mandatory_gaps,
        explanation=match.explanation,
    )


def _ref(role) -> RoleRef | None:
    return RoleRef(role_id=role.role_id, title=role.title) if role else None


def to_response(result: RoleMatchResult) -> RoleMatchResponse:
    return RoleMatchResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        current_role=_ref(result.current_role),
        career_goal=_ref(result.career_goal),
        roles_considered=result.roles_considered,
        matches=[_match_out(m) for m in result.matches],
        target=_match_out(result.target) if result.target else None,
        related_to=_ref(result.related_to),
        related_roles=[
            RelatedRoleOut(
                role_id=r.similar.role.role_id,
                title=r.similar.role.title,
                similarity=r.similar.similarity,
                shared_skills=r.shared_skill_names,
                employee_match_percentage=r.employee_match,
            )
            for r in result.related_roles
        ],
        summary=result.summary,
        overrides_applied=result.overrides_applied,
        engine_version=get_settings().app_version,
    )


@router.post(
    "/match",
    response_model=RoleMatchResponse,
    summary="Rank job roles by how well an employee's skills match",
    description=(
        "Scores the employee against every role (or `role_ids`) with the same formula as "
        "`/skills/analyze`, ranks them by match percentage, and explains each result.\n\n"
        "- **target_role_id** (default: career goal) is always reported in `target`.\n"
        "- **related_roles** are the roles whose required skills are most similar to the target "
        "(TF-IDF + cosine similarity), with the employee's match for each."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Employee or role not found"},
        422: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
def match_roles(request: RoleMatchRequest, service: RoleMatchingServiceDep) -> RoleMatchResponse:
    for role_id in request.role_ids or []:
        if not ROLE_ID.match(role_id):
            raise InvalidInputError("INVALID_ROLE_ID", f"'{role_id}' is not a role ID like R004.")
    overrides = {s.skill: s.level for s in request.current_skills or []}
    result = service.match(
        request.employee_id, request.role_ids, request.target_role_id, request.top_n, overrides
    )
    return to_response(result)
