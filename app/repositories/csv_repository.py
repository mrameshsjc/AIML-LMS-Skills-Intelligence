"""
CSV repository: serves LMS data from the CSV files (Phase 5).

PURPOSE
    Implements LmsRepository by loading the 11 CSV files ONCE into memory and
    building dictionaries for fast look-ups ("what are E1001's skills?" is a
    single dict access, not a scan of 925 rows).

WHICH FOLDER
    By default data/sample. Point it at data/processed to serve cleaned data.
    The API reads the folder from the DATA_DIR setting.

WHY LOAD EVERYTHING AT START
    The data is small (about 2,000 rows). Loading once keeps every request
    fast. The LMS database version will query on demand instead.
"""

from __future__ import annotations

from pathlib import Path

from app.data_processing.loader import load_all
from app.domain.models import Course, CourseSkill, Employee, JobRole, RoleRequirement, Skill
from app.repositories.base import LmsRepository

# When a course appears more than once in someone's history, keep the most advanced status.
STATUS_ORDER = {"Completed": 4, "In Progress": 3, "Enrolled": 2, "Dropped": 1}


class CsvLmsRepository(LmsRepository):
    def __init__(self, folder: str | Path | None = None) -> None:
        data = load_all(folder, typed=True)

        self._skills = {
            r.skill_id: Skill(r.skill_id, r.skill_name, r.category) for r in data["skills.csv"].itertuples()
        }
        self._roles = {
            r.role_id: JobRole(r.role_id, r.role_title, r.department, r.job_family, r.seniority)
            for r in data["job_roles.csv"].itertuples()
        }
        self._requirements: dict[str, list[RoleRequirement]] = {}
        for r in data["role_required_skills.csv"].itertuples():
            self._requirements.setdefault(r.role_id, []).append(
                RoleRequirement(
                    r.skill_id, int(r.required_level), float(r.importance_weight), bool(r.is_mandatory)
                )
            )
        self._employees = {
            r.employee_id: Employee(
                r.employee_id,
                r.first_name,
                r.last_name,
                r.department,
                r.current_role_id,
                r.location,
                r.manager_id if isinstance(r.manager_id, str) and r.manager_id else None,
            )
            for r in data["employees.csv"].itertuples()
        }
        self._employee_skills: dict[str, dict[str, int]] = {}
        for r in data["employee_skills.csv"].itertuples():
            self._employee_skills.setdefault(r.employee_id, {})[r.skill_id] = int(r.current_level)
        self._goals = {r.employee_id: r.target_role_id for r in data["career_goals.csv"].itertuples()}

        self._courses = {
            r.course_id: Course(
                r.course_id,
                r.course_title,
                r.description,
                r.difficulty,
                int(r.duration_hours),
                r.delivery_mode,
                r.provider,
                bool(r.is_active),
            )
            for r in data["courses.csv"].itertuples()
        }
        self._course_skills: dict[str, list[CourseSkill]] = {}
        for r in data["course_skills.csv"].itertuples():
            self._course_skills.setdefault(r.course_id, []).append(
                CourseSkill(r.course_id, r.skill_id, int(r.level_from), int(r.level_to))
            )
        self._prerequisites: dict[str, list[str]] = {}
        for r in data["course_prerequisites.csv"].itertuples():
            self._prerequisites.setdefault(r.course_id, []).append(r.prerequisite_course_id)
        self._training: dict[str, dict[str, str]] = {}
        for r in data["training_history.csv"].itertuples():
            statuses = self._training.setdefault(r.employee_id, {})
            if STATUS_ORDER.get(r.status, 0) > STATUS_ORDER.get(statuses.get(r.course_id, ""), 0):
                statuses[r.course_id] = r.status

    def get_employee(self, employee_id: str) -> Employee | None:
        return self._employees.get(employee_id)

    def direct_reports(self, manager_id: str) -> list[str]:
        return [e.employee_id for e in self._employees.values() if e.manager_id == manager_id]

    def get_employee_skills(self, employee_id: str) -> dict[str, int]:
        return dict(self._employee_skills.get(employee_id, {}))  # a copy: callers cannot change our data

    def get_role(self, role_id: str) -> JobRole | None:
        return self._roles.get(role_id)

    def list_roles(self) -> list[JobRole]:
        return list(self._roles.values())

    def get_role_requirements(self, role_id: str) -> list[RoleRequirement]:
        return list(self._requirements.get(role_id, []))

    def get_skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def get_career_goal(self, employee_id: str) -> str | None:
        return self._goals.get(employee_id)

    def get_courses(self) -> dict[str, Course]:
        return dict(self._courses)

    def get_course_skills(self, course_id: str) -> list[CourseSkill]:
        return list(self._course_skills.get(course_id, []))

    def get_prerequisites(self, course_id: str) -> list[str]:
        return list(self._prerequisites.get(course_id, []))

    def get_training_status(self, employee_id: str) -> dict[str, str]:
        return dict(self._training.get(employee_id, {}))
