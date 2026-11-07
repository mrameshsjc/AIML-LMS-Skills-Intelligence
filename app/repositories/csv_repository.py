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
from app.domain.models import Employee, JobRole, RoleRequirement, Skill
from app.repositories.base import LmsRepository


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
                r.employee_id, r.first_name, r.last_name, r.department, r.current_role_id, r.location
            )
            for r in data["employees.csv"].itertuples()
        }
        self._employee_skills: dict[str, dict[str, int]] = {}
        for r in data["employee_skills.csv"].itertuples():
            self._employee_skills.setdefault(r.employee_id, {})[r.skill_id] = int(r.current_level)
        self._goals = {r.employee_id: r.target_role_id for r in data["career_goals.csv"].itertuples()}

    def get_employee(self, employee_id: str) -> Employee | None:
        return self._employees.get(employee_id)

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
