"""
API 4 - Personalised Learning Path: GET /api/v1/learning-path/{employee_id}

PURPOSE
    The employee's plan towards a target role: current role and skills, the
    gaps, the courses in the order to take them (prerequisites first),
    progress, and one suggested next action. All logic is in
    app/services/learning_path.py.

WHY GET
    It only reads data and changes nothing, so it is a GET. The options are
    query parameters: /api/v1/learning-path/E1001?target_role_id=R004

ERRORS (shared format)
    404 EMPLOYEE_NOT_FOUND / ROLE_NOT_FOUND
    422 VALIDATION_ERROR (e.g. employee ID not in the form E1234)
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.dependencies import CurrentUserDep, ExplanationServiceDep, LearningPathServiceDep, RepositoryDep
from app.core.config import get_settings
from app.schemas.common import AUTH_RESPONSES, ErrorResponse, RoleRef
from app.schemas.learning_path import (
    CourseRef,
    CurrentSkillOut,
    ExplanationOut,
    LearningPathResponse,
    PathStepOut,
    ProgressOut,
    SkillGapPlanOut,
    StepSkillOut,
)
from app.schemas.trainings import PrerequisiteOut
from app.security.access import authorize_employee
from app.services.explanation_service import Explanation
from app.services.learning_path import LearningPath, PathStep

router = APIRouter(prefix="/learning-path", tags=["4. Learning Path"])


def _role(role) -> RoleRef:
    return RoleRef(role_id=role.role_id, title=role.title)


def _course(course) -> CourseRef:
    return CourseRef(course_id=course.course_id, title=course.title)


def _step_out(s: PathStep) -> PathStepOut:
    c = s.course
    return PathStepOut(
        step=s.step,
        course_id=c.course_id,
        title=c.title,
        difficulty=c.difficulty,
        duration_hours=c.duration_hours,
        delivery_mode=c.delivery_mode,
        purpose=s.purpose,
        status=s.status,
        raises=[
            StepSkillOut(skill=r.skill_name, course_from=r.level_from, course_to=r.level_to) for r in s.raises
        ],
        prerequisites=[
            PrerequisiteOut(course_id=p.course_id, title=p.title, satisfied=p.satisfied, how=p.how)
            for p in s.prerequisites
        ],
        after_steps=s.after_steps,
        ready_now=s.ready_now,
        addresses_mandatory_gap=s.mandatory,
        score=s.score,
        reason=s.reason,
        cumulative_hours=s.cumulative_hours,
    )


def _explanation_out(e: Explanation) -> ExplanationOut:
    return ExplanationOut(
        text=e.text,
        provider=e.provider,
        model=e.model,
        is_fallback=e.is_fallback,
        duration_ms=e.duration_ms,
        grounding_warnings=e.grounding_warnings,
        facts=e.facts,
        notes=e.notes,
    )


def to_response(p: LearningPath, explanation: Explanation | None = None) -> LearningPathResponse:
    return LearningPathResponse(
        employee_id=p.employee_id,
        employee_name=p.employee_name,
        current_role=_role(p.current_role),
        target_role=_role(p.target_role),
        target_source=p.target_source,
        current_skills=[
            CurrentSkillOut(skill=s.skill_name, level=s.level, required_for_target=s.required_for_target)
            for s in p.current_skills
        ],
        skill_gaps=[
            SkillGapPlanOut(
                skill=g.gap.skill_name,
                current_level=g.gap.current_level,
                required_level=g.gap.required_level,
                gap=g.gap.gap,
                mandatory=g.gap.mandatory,
                closed_by=g.closed_by,
                level_after_path=g.level_after_path,
            )
            for g in p.gaps
        ],
        path=[_step_out(s) for s in p.steps],
        progress=ProgressOut(
            match_percentage=p.progress.match_percentage,
            projected_match_percentage=p.progress.projected_match_percentage,
            skills_met=p.progress.skills_met,
            skills_required=p.progress.skills_required,
            completed_courses=[_course(c) for c in p.progress.completed_courses],
            in_progress_courses=[_course(c) for c in p.progress.in_progress_courses],
            total_steps=p.progress.total_steps,
            total_hours=p.progress.total_hours,
        ),
        next_action=p.next_action,
        uncovered_skills=p.uncovered_skills,
        notes=p.notes,
        explanation=_explanation_out(explanation) if explanation else None,
        engine_version=get_settings().app_version,
    )


@router.get(
    "/{employee_id}",
    response_model=LearningPathResponse,
    summary="Build an employee's personalised learning path",
    description=(
        "Selects the courses that close the employee's gaps for the target role and puts them in an order "
        "they can follow: **prerequisites first**, then mandatory gaps, then the API 3 score. "
        "Courses already completed are never included; courses in progress are kept, with their status.\n\n"
        "Also returns current skills, gaps (with the courses that close each), progress "
        "(match % now and after the path) and the **next action**.\n\n"
        "**explain=true** adds a plain-language explanation written by the language model (Ollama), "
        "based only on the path's facts; without a running model, a labelled fallback lists the facts."
    ),
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Employee or role not found"},
        422: {"model": ErrorResponse, "description": "Invalid employee or role ID"},
        503: {
            "model": ErrorResponse,
            "description": "explain=true but the LLM is unavailable (LLM_PROVIDER=ollama)",
        },
    },
)
def get_learning_path(
    employee_id: Annotated[str, Path(pattern=r"^E\d{4}$", examples=["E1001"])],
    service: LearningPathServiceDep,
    explainer: ExplanationServiceDep,
    principal: CurrentUserDep,
    repository: RepositoryDep,
    target_role_id: Annotated[
        str | None,
        Query(
            pattern=r"^R\d{3}$",
            description="Role to prepare for. Default: the employee's career goal, else their current role.",
        ),
    ] = None,
    include_optional: Annotated[
        bool, Query(description="Also plan for optional (non-mandatory) skills.")
    ] = True,
    explain: Annotated[
        bool, Query(description="Add a plain-language explanation from the language model (slower).")
    ] = False,
) -> LearningPathResponse:
    authorize_employee(principal, employee_id, repository)  # Phase 17: own / team data only
    path = service.build(employee_id, target_role_id, include_optional)
    return to_response(path, explainer.explain_path(path) if explain else None)
