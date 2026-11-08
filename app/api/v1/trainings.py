"""
API 3 - Training Recommendations: POST /api/v1/trainings/recommend

PURPOSE
    Recommend courses that close an employee's skill gaps for a target role,
    each with a score, its parts and a plain-language reason. All logic is in
    app/services/training_recommendation.py.

ERRORS (shared format)
    404 EMPLOYEE_NOT_FOUND / ROLE_NOT_FOUND
    422 VALIDATION_ERROR, UNKNOWN_SKILL
"""

from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, RepositoryDep, TrainingRecommendationServiceDep
from app.core.config import get_settings
from app.schemas.common import AUTH_RESPONSES, ErrorResponse, RoleRef
from app.schemas.trainings import (
    PrerequisiteOut,
    RecommendationOut,
    ScoreComponents,
    SkillCoveredOut,
    TrainingRecommendationRequest,
    TrainingRecommendationResponse,
)
from app.security.access import authorize_employee
from app.services.training_recommendation import Recommendation, RecommendationResult

router = APIRouter(prefix="/trainings", tags=["3. Training Recommendations"])


def _recommendation_out(rec: Recommendation) -> RecommendationOut:
    course = rec.course
    return RecommendationOut(
        rank=rec.rank,
        course_id=course.course_id,
        title=course.title,
        description=course.description,
        difficulty=course.difficulty,
        duration_hours=course.duration_hours,
        delivery_mode=course.delivery_mode,
        provider=course.provider,
        skills_covered=[
            SkillCoveredOut(
                skill=c.skill_name,
                current_level=c.current_level,
                required_level=c.required_level,
                course_from=c.level_from,
                course_to=c.level_to,
                gap_closed=c.gain,
                gap=c.gap,
                mandatory=c.mandatory,
            )
            for c in rec.contributions
        ],
        prerequisites=[
            PrerequisiteOut(course_id=p.course_id, title=p.title, satisfied=p.satisfied, how=p.how)
            for p in rec.prerequisites
        ],
        score=rec.score,
        components=ScoreComponents(**rec.components),
        addresses_mandatory_gap=rec.addresses_mandatory_gap,
        enrollment_status=rec.enrollment_status,
        reason=rec.reason,
    )


def to_response(result: RecommendationResult) -> TrainingRecommendationResponse:
    return TrainingRecommendationResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        target_role=RoleRef(role_id=result.target_role.role_id, title=result.target_role.title),
        target_source=result.target_source,
        gap_score=result.gap_score,
        match_percentage=result.match_percentage,
        skill_gaps=[
            f"{g.skill_name} {g.current_level}->{g.required_level}{' (mandatory)' if g.mandatory else ''}"
            for g in result.gaps
        ],
        recommendations=[_recommendation_out(r) for r in result.recommendations],
        uncovered_skills=result.uncovered_skills,
        weights_used=result.weights_used,
        notes=result.notes,
        engine_version=get_settings().app_version,
    )


@router.post(
    "/recommend",
    response_model=TrainingRecommendationResponse,
    summary="Recommend courses that close an employee's skill gaps",
    description=(
        "Finds active courses that raise the employee's gap skills for the target role "
        "(excluding courses already completed), scores and explains each one.\n\n"
        "**score** = 0.50 x gap_coverage + 0.20 x level_fit + 0.15 x prereq_ready "
        "+ 0.15 x completion_probability. Until the completion model exists (Phase 8), its weight is "
        "shared proportionally among the other parts - see `weights_used`.\n\n"
        "Courses for **mandatory** gaps are listed first; within that, highest score first."
    ),
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Employee or role not found"},
        422: {"model": ErrorResponse, "description": "Invalid input or unknown skill"},
    },
)
def recommend_trainings(
    request: TrainingRecommendationRequest,
    service: TrainingRecommendationServiceDep,
    principal: CurrentUserDep,
    repository: RepositoryDep,
) -> TrainingRecommendationResponse:
    authorize_employee(principal, request.employee_id, repository)  # Phase 17: own / team data only
    result = service.recommend(
        request.employee_id,
        request.target_role_id,
        request.skills,
        request.max_results,
        request.include_enrolled,
    )
    return to_response(result)
