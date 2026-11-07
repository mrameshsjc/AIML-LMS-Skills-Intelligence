"""Request and response shapes for API 3: POST /api/v1/trainings/recommend."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RoleRef


class TrainingRecommendationRequest(BaseModel):
    employee_id: str = Field(pattern=r"^E\d{4}$", examples=["E1001"])
    target_role_id: str | None = Field(
        default=None,
        pattern=r"^R\d{3}$",
        description="Role to prepare for. Default: the employee's career goal, else their current role.",
    )
    skills: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Only recommend for these skills (names or IDs). Default: every gap.",
    )
    max_results: int = Field(default=10, ge=1, le=30)
    include_enrolled: bool = Field(
        default=True, description="Also list courses the employee is already enrolled in."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"employee_id": "E1001"},
                {"employee_id": "E1001", "target_role_id": "R004", "skills": ["AWS"], "max_results": 3},
            ]
        }
    )


class SkillCoveredOut(BaseModel):
    skill: str
    current_level: int
    required_level: int
    course_from: int = Field(description="Level the course expects you to have at the start.")
    course_to: int = Field(description="Level the course brings you to.")
    gap_closed: int = Field(description="How many of your gap levels this course closes.")
    gap: int
    mandatory: bool


class PrerequisiteOut(BaseModel):
    course_id: str
    title: str
    satisfied: bool
    how: str = Field(description="completed | skill level (your current level already covers it) | not yet")


class ScoreComponents(BaseModel):
    gap_coverage: float = Field(description="Share of the gap in the course's skills that it closes (0-1).")
    level_fit: float = Field(
        description="1 = starts at your level; lower if it starts above you or far below."
    )
    prereq_ready: float = Field(description="Share of prerequisites completed or covered by your level.")
    completion_probability: float | None = Field(description="From the ML model (Phase 8); null until then.")


class RecommendationOut(BaseModel):
    rank: int
    course_id: str
    title: str
    description: str
    difficulty: str
    duration_hours: int
    delivery_mode: str
    provider: str
    skills_covered: list[SkillCoveredOut]
    prerequisites: list[PrerequisiteOut]
    score: float = Field(description="Weighted combination of the components (0-1). See weights_used.")
    components: ScoreComponents
    addresses_mandatory_gap: bool
    enrollment_status: str | None = Field(
        description="Enrolled / In Progress / Dropped if taken before, else null."
    )
    reason: str


class TrainingRecommendationResponse(BaseModel):
    employee_id: str
    employee_name: str
    target_role: RoleRef
    target_source: str
    gap_score: float
    match_percentage: float
    skill_gaps: list[str] = Field(description="Gap skills considered, e.g. 'SQL 2->4 (mandatory)'.")
    recommendations: list[RecommendationOut] = Field(
        description="Courses for mandatory gaps first; within that, highest score first."
    )
    uncovered_skills: list[str] = Field(description="Gap skills no available course can close.")
    weights_used: dict[str, float]
    notes: list[str]
    engine_version: str
