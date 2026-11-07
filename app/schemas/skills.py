"""
Request and response shapes for API 1: POST /api/v1/skills/analyze.

WHY PYDANTIC MODELS
    FastAPI uses them to:
      - reject bad input automatically (for example employee_id "abc" or a
        level of 9) with a clear 422 error, before our code runs;
      - convert the response to JSON with exactly these fields;
      - show the fields, rules and examples in Swagger UI (/docs).
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RoleRef


class SkillLevelIn(BaseModel):
    """A what-if skill level supplied in the request."""

    skill: str = Field(
        min_length=1, max_length=80, examples=["SQL"], description="Skill name or ID (e.g. SK004)."
    )
    level: int = Field(
        ge=0, le=5, examples=[4], description="0 = does not have the skill, 1-5 = proficiency."
    )


class SkillAnalysisRequest(BaseModel):
    employee_id: str = Field(pattern=r"^E\d{4}$", examples=["E1001"], description="Employee to analyse.")
    target_role_id: str | None = Field(
        default=None,
        pattern=r"^R\d{3}$",
        examples=["R004"],
        description="Role to compare with. If omitted: the employee's career goal, else their current role.",
    )
    current_skills: list[SkillLevelIn] | None = Field(
        default=None,
        max_length=50,
        description="Optional what-if levels that replace the stored ones for this analysis only.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"employee_id": "E1001", "target_role_id": "R004"},
                {
                    "employee_id": "E1001",
                    "target_role_id": "R004",
                    "current_skills": [{"skill": "SQL", "level": 4}],
                },
            ]
        }
    )


class SkillGapOut(BaseModel):
    skill_id: str
    skill: str
    category: str
    current_level: int = Field(description="0 = the employee does not have this skill.")
    required_level: int
    gap: int = Field(description="max(0, required - current)")
    mandatory: bool
    status: str = Field(description="met | below_required | missing")


class ProfileSkillOut(BaseModel):
    skill_id: str
    skill: str
    level: int
    required_for_target: bool


class SkillAnalysisResponse(BaseModel):
    employee_id: str
    employee_name: str
    current_role: RoleRef
    target_role: RoleRef
    target_source: str = Field(description="Where the target came from: request | career_goal | current_role")
    skills: list[SkillGapOut] = Field(description="Every skill the target role requires, most urgent first.")
    skill_profile: list[ProfileSkillOut] = Field(description="All skills the employee has.")
    missing_skills: list[str] = Field(description="Required skills the employee does not have at all.")
    gap_score: float = Field(description="100 * sum(weight * gap) / sum(weight * required). 0 = role-ready.")
    match_percentage: float = Field(
        description="100 * sum(weight * min(current, required)) / sum(weight * required)."
    )
    mandatory_gaps: int
    role_ready: bool
    suggestions: list[str]
    summary: str
    overrides_applied: list[str] = Field(description="What-if levels used in this analysis, if any.")
    engine_version: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "employee_id": "E1001",
                    "employee_name": "Arjun Krishnan",
                    "current_role": {"role_id": "R001", "title": "Software Developer"},
                    "target_role": {"role_id": "R004", "title": "Data Engineer"},
                    "target_source": "request",
                    "skills": [
                        {
                            "skill_id": "SK017",
                            "skill": "AWS",
                            "category": "Cloud & DevOps",
                            "current_level": 1,
                            "required_level": 3,
                            "gap": 2,
                            "mandatory": True,
                            "status": "below_required",
                        },
                        {
                            "skill_id": "SK004",
                            "skill": "SQL",
                            "category": "Programming",
                            "current_level": 2,
                            "required_level": 4,
                            "gap": 2,
                            "mandatory": True,
                            "status": "below_required",
                        },
                    ],
                    "skill_profile": [
                        {"skill_id": "SK001", "skill": "Python", "level": 3, "required_for_target": True}
                    ],
                    "missing_skills": [],
                    "gap_score": 37.5,
                    "match_percentage": 62.5,
                    "mandatory_gaps": 3,
                    "role_ready": False,
                    "suggestions": [
                        "Raise AWS (mandatory) from level 1 to 3.",
                        "Raise SQL (mandatory) from level 2 to 4.",
                    ],
                    "summary": "Arjun Krishnan meets 1 of 5 skill requirements for Data Engineer; "
                    "4 need improvement (3 mandatory). Match 62.5%, gap score 37.5 (0 = role-ready).",
                    "overrides_applied": [],
                    "engine_version": "0.1.0",
                }
            ]
        }
    )
