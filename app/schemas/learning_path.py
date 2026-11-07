"""Response shapes for API 4: GET /api/v1/learning-path/{employee_id}."""

from pydantic import BaseModel, Field

from app.schemas.common import RoleRef
from app.schemas.trainings import PrerequisiteOut


class CurrentSkillOut(BaseModel):
    skill: str
    level: int
    required_for_target: bool


class SkillGapPlanOut(BaseModel):
    skill: str
    current_level: int
    required_level: int
    gap: int
    mandatory: bool
    closed_by: list[str] = Field(description="Course IDs in the path that raise this skill.")
    level_after_path: int = Field(description="Level reached after the path (capped at the required level).")


class StepSkillOut(BaseModel):
    skill: str
    course_from: int
    course_to: int


class PathStepOut(BaseModel):
    step: int = Field(description="Position in the recommended sequence (1 = first).")
    course_id: str
    title: str
    difficulty: str
    duration_hours: int
    delivery_mode: str
    purpose: str = Field(description="closes_gap, or prerequisite (needed by a later step).")
    status: str = Field(description="Not started, Enrolled, In Progress or Dropped before.")
    raises: list[StepSkillOut]
    prerequisites: list[PrerequisiteOut]
    after_steps: list[int] = Field(description="Steps to finish before this one.")
    ready_now: bool = Field(description="True if nothing in the path has to come first.")
    addresses_mandatory_gap: bool
    score: float | None = Field(description="The API 3 score, when the course is in API 3's list.")
    reason: str
    cumulative_hours: int = Field(description="Hours from step 1 up to and including this step.")


class CourseRef(BaseModel):
    course_id: str
    title: str


class ProgressOut(BaseModel):
    match_percentage: float = Field(description="Match with the target role now (same as API 1).")
    projected_match_percentage: float = Field(description="Match after completing every step.")
    skills_met: int
    skills_required: int
    completed_courses: list[CourseRef] = Field(
        description="Completed courses that raise a target-role skill."
    )
    in_progress_courses: list[CourseRef] = Field(description="Path courses you are enrolled in or doing.")
    total_steps: int
    total_hours: int


class ExplanationOut(BaseModel):
    text: str = Field(description="The explanation (or, from the fallback, the facts as a list).")
    provider: str = Field(description="ollama, or fallback when no language model was used.")
    model: str
    is_fallback: bool
    duration_ms: int
    grounding_warnings: list[str] = Field(
        description="Course IDs or numbers in the text that are not in the engine's facts. Empty is good."
    )
    facts: list[str] = Field(
        description="Exactly what the model was given: the text can be checked against it."
    )
    notes: list[str]


class LearningPathResponse(BaseModel):
    employee_id: str
    employee_name: str
    current_role: RoleRef
    target_role: RoleRef
    target_source: str = Field(description="request, career_goal or current_role.")
    current_skills: list[CurrentSkillOut]
    skill_gaps: list[SkillGapPlanOut]
    path: list[PathStepOut]
    progress: ProgressOut
    next_action: str = Field(description="The one thing to do next.")
    uncovered_skills: list[str] = Field(description="Gaps no available course fully closes.")
    notes: list[str]
    explanation: ExplanationOut | None = Field(
        default=None, description="Plain-language explanation, only with ?explain=true (Phase 11)."
    )
    engine_version: str
