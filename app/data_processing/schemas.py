"""
Dataset schemas: the single description of what "correct" data looks like.

PURPOSE
    For each of the 11 LMS files, describe:
      - its columns, their type and whether they may be empty;
      - allowed ranges (levels 1-5, score 0-100) and allowed values (statuses);
      - the primary key (which columns identify a row);
      - foreign keys (which columns must point to rows in another file).

WHY ONE PLACE
    The validation scripts (03-06), the automated tests, and later the CSV
    upload page and the API all read these definitions. If a rule changes, we
    change it here once, and every check follows.

    Alternatives considered: libraries such as Pandera or Great Expectations do
    this too. They are powerful but add a lot to learn at once; plain Python
    dataclasses keep every rule visible and easy to follow. We can switch later
    without changing the scripts' output.

TYPES USED
    "string"  any text                         e.g. "Data Engineer"
    "int"     whole number                     e.g. 4
    "float"   decimal number                   e.g. 1.0
    "bool"    the text True or False           e.g. True
    "date"    a date written as YYYY-MM-DD     e.g. 2026-10-31
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# The synthetic data describes the world as of this date (see DATA_DICTIONARY.md).
DATA_AS_OF = date(2026, 10, 31)

TRAINING_STATUSES = ("Enrolled", "In Progress", "Completed", "Dropped")


@dataclass(frozen=True)
class ColumnSpec:
    """Rules for one column.

    `required=True` means the column may not contain empty values.
    `min_value` / `max_value` apply to numbers.
    `allowed` lists the only accepted values (for text columns).
    `pattern` is a regular expression the value must match (for IDs).
    """

    name: str
    dtype: str = "string"
    required: bool = True
    min_value: float | None = None
    max_value: float | None = None
    allowed: tuple[str, ...] | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class ForeignKey:
    """`column` in this file must exist in `ref_column` of `ref_dataset`."""

    column: str
    ref_dataset: str
    ref_column: str


@dataclass(frozen=True)
class DatasetSchema:
    """Everything we expect from one CSV file."""

    name: str
    description: str
    columns: tuple[ColumnSpec, ...]
    primary_key: tuple[str, ...]
    unique: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    column_names: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        # Frozen dataclasses need object.__setattr__ to set a derived field.
        object.__setattr__(self, "column_names", tuple(c.name for c in self.columns))

    def column(self, name: str) -> ColumnSpec:
        return next(c for c in self.columns if c.name == name)


C = ColumnSpec  # short alias to keep the definitions below readable
FK = ForeignKey

SCHEMAS: dict[str, DatasetSchema] = {
    s.name: s
    for s in [
        DatasetSchema(
            "skills.csv",
            "One row per skill.",
            (
                C("skill_id", pattern=r"^SK\d{3}$"),
                C("skill_name"),
                C("category"),
                C("description"),
            ),
            primary_key=("skill_id",),
            unique=(("skill_name",),),
        ),
        DatasetSchema(
            "skill_proficiency.csv",
            "The 1-5 proficiency scale.",
            (C("level", "int", min_value=1, max_value=5), C("label"), C("description")),
            primary_key=("level",),
        ),
        DatasetSchema(
            "job_roles.csv",
            "One row per job role.",
            (
                C("role_id", pattern=r"^R\d{3}$"),
                C("role_title"),
                C("department"),
                C("job_family"),
                C("seniority", allowed=("Junior", "Mid", "Senior")),
                C("description"),
            ),
            primary_key=("role_id",),
            unique=(("role_title",),),
        ),
        DatasetSchema(
            "role_required_skills.csv",
            "Skills each role needs, with the required level.",
            (
                C("role_id"),
                C("skill_id"),
                C("required_level", "int", min_value=1, max_value=5),
                C("importance_weight", "float", min_value=0, max_value=10),
                C("is_mandatory", "bool"),
            ),
            primary_key=("role_id", "skill_id"),
            foreign_keys=(
                FK("role_id", "job_roles.csv", "role_id"),
                FK("skill_id", "skills.csv", "skill_id"),
            ),
        ),
        DatasetSchema(
            "courses.csv",
            "One row per training course.",
            (
                C("course_id", pattern=r"^C-[A-Z0-9]+-\d{3}$"),
                C("course_title"),
                C("description"),
                C("difficulty", allowed=("Beginner", "Intermediate", "Advanced")),
                C("duration_hours", "int", min_value=1, max_value=200),
                C("delivery_mode", allowed=("Online", "Blended", "Classroom")),
                C("provider"),
                C("is_active", "bool"),
            ),
            primary_key=("course_id",),
        ),
        DatasetSchema(
            "course_skills.csv",
            "Skills each course raises, from one level to another.",
            (
                C("course_id"),
                C("skill_id"),
                C("level_from", "int", min_value=0, max_value=4),
                C("level_to", "int", min_value=1, max_value=5),
            ),
            primary_key=("course_id", "skill_id"),
            foreign_keys=(
                FK("course_id", "courses.csv", "course_id"),
                FK("skill_id", "skills.csv", "skill_id"),
            ),
        ),
        DatasetSchema(
            "course_prerequisites.csv",
            "Courses that must be completed before another course.",
            (C("course_id"), C("prerequisite_course_id")),
            primary_key=("course_id", "prerequisite_course_id"),
            foreign_keys=(
                FK("course_id", "courses.csv", "course_id"),
                FK("prerequisite_course_id", "courses.csv", "course_id"),
            ),
        ),
        DatasetSchema(
            "employees.csv",
            "One row per employee.",
            (
                C("employee_id", pattern=r"^E\d{4}$"),
                C("first_name"),
                C("last_name"),
                C("email", pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
                C("department"),
                C("current_role_id"),
                C("manager_id", required=False),
                C("hire_date", "date"),
                C("location"),
                C("employment_status", allowed=("Active", "Inactive")),
            ),
            primary_key=("employee_id",),
            unique=(("email",),),
            foreign_keys=(
                FK("current_role_id", "job_roles.csv", "role_id"),
                FK("manager_id", "employees.csv", "employee_id"),
            ),
        ),
        DatasetSchema(
            "employee_skills.csv",
            "Each employee's current level in each skill.",
            (
                C("employee_id"),
                C("skill_id"),
                C("current_level", "int", min_value=1, max_value=5),
                C("source", allowed=("self", "manager", "assessment")),
                C("assessed_date", "date"),
            ),
            primary_key=("employee_id", "skill_id"),
            foreign_keys=(
                FK("employee_id", "employees.csv", "employee_id"),
                FK("skill_id", "skills.csv", "skill_id"),
            ),
        ),
        DatasetSchema(
            "career_goals.csv",
            "The role each employee wants next.",
            (
                C("employee_id"),
                C("target_role_id"),
                C("set_date", "date"),
                C("goal_status", allowed=("Active", "Achieved", "Withdrawn")),
            ),
            primary_key=("employee_id",),
            foreign_keys=(
                FK("employee_id", "employees.csv", "employee_id"),
                FK("target_role_id", "job_roles.csv", "role_id"),
            ),
        ),
        DatasetSchema(
            "training_history.csv",
            "One row per course enrolment.",
            (
                C("enrollment_id", pattern=r"^EN\d{4,}$"),
                C("employee_id"),
                C("course_id"),
                C("status", allowed=TRAINING_STATUSES),
                C("enrolled_date", "date"),
                # Empty unless the course was completed (checked as a business rule).
                C("completed_date", "date", required=False),
                C("score", "int", required=False, min_value=0, max_value=100),
                C("attempts", "int", min_value=1, max_value=5),
            ),
            primary_key=("enrollment_id",),
            foreign_keys=(
                FK("employee_id", "employees.csv", "employee_id"),
                FK("course_id", "courses.csv", "course_id"),
            ),
        ),
    ]
}

DATASET_NAMES: tuple[str, ...] = tuple(SCHEMAS)
