"""Request and response shapes for API 2: POST /api/v1/roles/match."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RoleRef
from app.schemas.skills import SkillLevelIn


class RoleMatchRequest(BaseModel):
    employee_id: str = Field(pattern=r"^E\d{4}$", examples=["E1001"])
    role_ids: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Compare only these roles (each like R004). Default: all roles.",
    )
    target_role_id: str | None = Field(
        default=None,
        pattern=r"^R\d{3}$",
        description="A role of special interest: always reported, and related roles are found for it. "
        "Default: the employee's career goal.",
    )
    top_n: int = Field(default=5, ge=1, le=20, description="How many ranked roles to return.")
    current_skills: list[SkillLevelIn] | None = Field(
        default=None, max_length=50, description="Optional what-if levels for this request only."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"employee_id": "E1001"},
                {"employee_id": "E1001", "target_role_id": "R006", "top_n": 3},
                {"employee_id": "E1001", "role_ids": ["R002", "R004", "R008"]},
            ]
        }
    )


class SkillShortfall(BaseModel):
    skill: str
    current_level: int
    required_level: int
    mandatory: bool


class RoleMatchOut(BaseModel):
    rank: int = Field(description="Position among the compared roles (0 = not among them).")
    role_id: str
    title: str
    department: str
    seniority: str
    match_percentage: float
    gap_score: float
    readiness: str = Field(description="Ready (100%) | Close (80-99%) | Developing (50-79%) | Early (<50%)")
    is_current_role: bool
    is_career_goal: bool
    matching_skills: list[str] = Field(description="Required skills already at or above the required level.")
    needs_improvement: list[SkillShortfall] = Field(
        description="Skills the employee has, below the required level."
    )
    missing_skills: list[SkillShortfall] = Field(description="Required skills the employee does not have.")
    mandatory_gaps: int
    explanation: str


class RelatedRoleOut(BaseModel):
    role_id: str
    title: str
    similarity: float = Field(
        description="TF-IDF cosine similarity of required skills: 0 = none, 1 = identical."
    )
    shared_skills: list[str]
    employee_match_percentage: float


class RoleMatchResponse(BaseModel):
    employee_id: str
    employee_name: str
    current_role: RoleRef
    career_goal: RoleRef | None
    roles_considered: int
    matches: list[RoleMatchOut]
    target: RoleMatchOut | None = Field(
        description="The target role's result, even if it is outside the top N."
    )
    related_to: RoleRef | None = Field(description="Role the related roles were found for.")
    related_roles: list[RelatedRoleOut]
    summary: str
    overrides_applied: list[str]
    engine_version: str
