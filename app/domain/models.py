"""
Domain models: the engine's own vocabulary.

PURPOSE
    Small, read-only Python objects for the things the engine reasons about:
    skills, job roles, role requirements and employees. Every repository
    (CSV today, the LMS database later) returns THESE objects, so the services
    never see CSV columns or database tables.

WHY DATACLASSES
    @dataclass writes __init__, __repr__ and __eq__ for us; frozen=True makes
    objects read-only, so a service cannot change data by accident.
    (Pydantic models are used at the API edge, where input must be validated;
    inside the engine, data has already been validated.)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    category: str


@dataclass(frozen=True)
class JobRole:
    role_id: str
    title: str
    department: str
    job_family: str
    seniority: str


@dataclass(frozen=True)
class RoleRequirement:
    """One skill a role needs: the level, how much it counts, and whether it is a must-have."""

    skill_id: str
    required_level: int
    weight: float = 1.0
    mandatory: bool = True


@dataclass(frozen=True)
class Employee:
    employee_id: str
    first_name: str
    last_name: str
    department: str
    current_role_id: str
    location: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class Course:
    course_id: str
    title: str
    description: str
    difficulty: str
    duration_hours: int
    delivery_mode: str
    provider: str
    is_active: bool = True


@dataclass(frozen=True)
class CourseSkill:
    """A course raises one skill from level_from (expected entry level) to level_to."""

    course_id: str
    skill_id: str
    level_from: int
    level_to: int
