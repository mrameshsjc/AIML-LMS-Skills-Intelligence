"""
API 1 - Skills Analysis: POST /api/v1/skills/analyze

PURPOSE
    Analyse an employee's skills against a target job role and return the
    gaps, a gap score, a match percentage and explained suggestions.

THIS FILE ONLY TRANSLATES
    request (Pydantic) -> SkillAnalysisService.analyze() -> response (Pydantic)
    All decisions live in app/services/skill_analysis.py, so the dashboard and
    tests get exactly the same answers without going through HTTP.

ERRORS (shared format, see app/core/errors.py)
    404 EMPLOYEE_NOT_FOUND / ROLE_NOT_FOUND
    422 VALIDATION_ERROR (bad field format), UNKNOWN_SKILL, INVALID_LEVEL
"""

from fastapi import APIRouter

from app.api.dependencies import SkillAnalysisServiceDep
from app.core.config import get_settings
from app.schemas.common import ErrorResponse, RoleRef
from app.schemas.skills import ProfileSkillOut, SkillAnalysisRequest, SkillAnalysisResponse, SkillGapOut
from app.services.skill_analysis import SkillAnalysisResult

router = APIRouter(prefix="/skills", tags=["1. Skills Analysis"])


def to_response(result: SkillAnalysisResult) -> SkillAnalysisResponse:
    """Copy the service result into the API response shape."""
    return SkillAnalysisResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        current_role=RoleRef(role_id=result.current_role.role_id, title=result.current_role.title),
        target_role=RoleRef(role_id=result.target_role.role_id, title=result.target_role.title),
        target_source=result.target_source,
        skills=[
            SkillGapOut(
                skill_id=g.skill_id,
                skill=g.skill_name,
                category=g.category,
                current_level=g.current_level,
                required_level=g.required_level,
                gap=g.gap,
                mandatory=g.mandatory,
                status=g.status,
            )
            for g in result.summary.skills
        ],
        skill_profile=[
            ProfileSkillOut(
                skill_id=p.skill_id,
                skill=p.skill_name,
                level=p.level,
                required_for_target=p.required_for_target,
            )
            for p in result.skill_profile
        ],
        missing_skills=result.missing_skills,
        gap_score=result.summary.gap_score,
        match_percentage=result.summary.match_percentage,
        mandatory_gaps=result.mandatory_gaps,
        role_ready=result.role_ready,
        suggestions=result.suggestions,
        summary=result.explanation,
        overrides_applied=result.overrides_applied,
        engine_version=get_settings().app_version,
    )


@router.post(
    "/analyze",
    response_model=SkillAnalysisResponse,
    summary="Analyse an employee's skill gaps for a target role",
    description=(
        "Compares the employee's current skill levels with the levels the target role requires.\n\n"
        "- **target_role_id** is optional: without it the employee's career goal is used, "
        "or their current role if they have no goal.\n"
        "- **current_skills** is optional: what-if levels used only for this analysis.\n\n"
        "**gap_score** = 100 x sum(weight x gap) / sum(weight x required) - 0 means role-ready. "
        "**match_percentage** = 100 x sum(weight x min(current, required)) / sum(weight x required)."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Employee or role not found"},
        422: {"model": ErrorResponse, "description": "Invalid input (field format, unknown skill, level)"},
    },
)
def analyze_skills(
    request: SkillAnalysisRequest,
    service: SkillAnalysisServiceDep,
) -> SkillAnalysisResponse:
    overrides = {s.skill: s.level for s in request.current_skills or []}
    result = service.analyze(request.employee_id, request.target_role_id, overrides)
    return to_response(result)
