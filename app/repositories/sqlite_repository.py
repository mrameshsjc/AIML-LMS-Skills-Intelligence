"""
SQLite repository: serves LMS data from the database (Phase 9).

PURPOSE
    Implements the same LmsRepository interface as CsvLmsRepository, but asks
    the database each time instead of holding everything in memory. The
    services cannot tell the difference: tests prove both repositories give
    identical answers for every employee, role and course.

HOW TO SWITCH THE API TO THE DATABASE
    1. python data_science/14_save_to_database.py   (creates data/lms_ai.db)
    2. In .env: DATA_SOURCE=database
    3. Restart uvicorn.

SQL HABITS USED HERE
    - Parameters (?) for every value, never string formatting: this is what
      prevents SQL injection.
    - ORDER BY rowid keeps the original file order, so lists come back in the
      same order as from the CSV files.
    - A fresh connection per call (cheap for SQLite) is simple and safe when
      FastAPI answers several requests at once in different threads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager

from app.database.connection import DatabaseNotReadyError, connect
from app.domain.models import Course, CourseSkill, Employee, JobRole, RoleRequirement, Skill
from app.repositories.base import LmsRepository

# Most advanced status wins when a course was taken more than once (same rule as the CSV repository).
_STATUS_RANK = (
    "CASE status WHEN 'Completed' THEN 4 WHEN 'In Progress' THEN 3 WHEN 'Enrolled' THEN 2 ELSE 1 END"
)


class SqliteLmsRepository(LmsRepository):
    def __init__(self, database_url: str = "sqlite:///./data/lms_ai.db") -> None:
        self.database_url = database_url
        with self._connection() as conn:  # fail at start-up with a clear message, not on a request
            try:
                ready = conn.execute("SELECT 1 FROM skills LIMIT 1").fetchone() is not None
            except sqlite3.OperationalError:  # "no such table"
                ready = False
        if not ready:
            raise DatabaseNotReadyError(
                f"The database {database_url} has no LMS data. "
                "Load it with: python data_science/14_save_to_database.py"
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with closing(connect(self.database_url)) as conn:
            yield conn

    def _all(self, sql: str, *params) -> list[sqlite3.Row]:
        with self._connection() as conn:
            return conn.execute(sql, params).fetchall()

    def _one(self, sql: str, *params) -> sqlite3.Row | None:
        with self._connection() as conn:
            return conn.execute(sql, params).fetchone()

    # --- People -----------------------------------------------------------------
    def get_employee(self, employee_id: str) -> Employee | None:
        r = self._one(
            "SELECT employee_id, first_name, last_name, department, current_role_id, location, manager_id "
            "FROM employees WHERE employee_id = ?",
            employee_id,
        )
        return Employee(*r) if r else None

    def direct_reports(self, manager_id: str) -> list[str]:
        rows = self._all("SELECT employee_id FROM employees WHERE manager_id = ? ORDER BY rowid", manager_id)
        return [r["employee_id"] for r in rows]

    def get_employee_skills(self, employee_id: str) -> dict[str, int]:
        rows = self._all(
            "SELECT skill_id, current_level FROM employee_skills WHERE employee_id = ? ORDER BY rowid",
            employee_id,
        )
        return {r["skill_id"]: r["current_level"] for r in rows}

    def get_career_goal(self, employee_id: str) -> str | None:
        r = self._one("SELECT target_role_id FROM career_goals WHERE employee_id = ?", employee_id)
        return r["target_role_id"] if r else None

    # --- Roles and skills -------------------------------------------------------------
    def get_role(self, role_id: str) -> JobRole | None:
        r = self._one(
            "SELECT role_id, role_title, department, job_family, seniority FROM job_roles WHERE role_id = ?",
            role_id,
        )
        return JobRole(*r) if r else None

    def list_roles(self) -> list[JobRole]:
        rows = self._all(
            "SELECT role_id, role_title, department, job_family, seniority FROM job_roles ORDER BY rowid"
        )
        return [JobRole(*r) for r in rows]

    def get_role_requirements(self, role_id: str) -> list[RoleRequirement]:
        rows = self._all(
            "SELECT skill_id, required_level, importance_weight, is_mandatory "
            "FROM role_required_skills WHERE role_id = ? ORDER BY rowid",
            role_id,
        )
        return [
            RoleRequirement(
                r["skill_id"], r["required_level"], r["importance_weight"], bool(r["is_mandatory"])
            )
            for r in rows
        ]

    def get_skills(self) -> dict[str, Skill]:
        rows = self._all("SELECT skill_id, skill_name, category FROM skills ORDER BY rowid")
        return {r["skill_id"]: Skill(*r) for r in rows}

    # --- Courses and training ------------------------------------------------------------
    def get_courses(self) -> dict[str, Course]:
        rows = self._all(
            "SELECT course_id, course_title, description, difficulty, duration_hours, delivery_mode, "
            "provider, is_active FROM courses ORDER BY rowid"
        )
        return {r["course_id"]: Course(*tuple(r)[:7], bool(r["is_active"])) for r in rows}

    def get_course_skills(self, course_id: str) -> list[CourseSkill]:
        rows = self._all(
            "SELECT course_id, skill_id, level_from, level_to FROM course_skills "
            "WHERE course_id = ? ORDER BY rowid",
            course_id,
        )
        return [CourseSkill(*r) for r in rows]

    def get_prerequisites(self, course_id: str) -> list[str]:
        rows = self._all(
            "SELECT prerequisite_course_id FROM course_prerequisites WHERE course_id = ? ORDER BY rowid",
            course_id,
        )
        return [r[0] for r in rows]

    def get_training_status(self, employee_id: str) -> dict[str, str]:
        # A window function picks, per course, the row with the most advanced status.
        rows = self._all(
            f"""
            SELECT course_id, status FROM (
                SELECT course_id, status, MIN(rowid) OVER (PARTITION BY course_id) AS first_seen,
                       ROW_NUMBER() OVER (PARTITION BY course_id ORDER BY {_STATUS_RANK} DESC, rowid) AS pick
                FROM training_history WHERE employee_id = ?
            ) WHERE pick = 1 ORDER BY first_seen
            """,
            employee_id,
        )
        return {r["course_id"]: r["status"] for r in rows}
