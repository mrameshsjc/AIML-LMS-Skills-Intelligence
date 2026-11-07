"""
Repository interface: how services ask for LMS data.

PURPOSE
    Services depend on THIS interface, never on a concrete data source.
    Today CsvLmsRepository reads the CSV files; in the LMS integration project
    an LmsMySqlRepository will implement the same methods against the real
    database. Services and the seven API contracts stay unchanged.

WHY AN ABSTRACT BASE CLASS (ABC)
    @abstractmethod forces every repository to implement every method:
    Python refuses to create an object of a class that forgot one. That makes
    a missing method fail immediately, not halfway through a request.
"""

from abc import ABC, abstractmethod

from app.domain.models import Course, CourseSkill, Employee, JobRole, RoleRequirement, Skill


class LmsRepository(ABC):
    """Read-only access to employees, skills, roles, career goals, courses and training history."""

    @abstractmethod
    def get_employee(self, employee_id: str) -> Employee | None:
        """The employee, or None if unknown."""

    @abstractmethod
    def get_employee_skills(self, employee_id: str) -> dict[str, int]:
        """{skill_id: current level} for the employee (empty if none)."""

    @abstractmethod
    def get_role(self, role_id: str) -> JobRole | None:
        """The job role, or None if unknown."""

    @abstractmethod
    def list_roles(self) -> list[JobRole]:
        """All job roles."""

    @abstractmethod
    def get_role_requirements(self, role_id: str) -> list[RoleRequirement]:
        """Skills the role needs (empty if the role is unknown)."""

    @abstractmethod
    def get_skills(self) -> dict[str, Skill]:
        """{skill_id: Skill} for every known skill."""

    @abstractmethod
    def get_career_goal(self, employee_id: str) -> str | None:
        """The employee's target role_id, or None if no goal is recorded."""

    @abstractmethod
    def get_courses(self) -> dict[str, Course]:
        """{course_id: Course} for every course (active and inactive)."""

    @abstractmethod
    def get_course_skills(self, course_id: str) -> list[CourseSkill]:
        """Skills the course raises (empty if unknown)."""

    @abstractmethod
    def get_prerequisites(self, course_id: str) -> list[str]:
        """Course IDs that must be completed before this course."""

    @abstractmethod
    def get_training_status(self, employee_id: str) -> dict[str, str]:
        """{course_id: status} of the employee's enrolments.

        If a course was taken more than once, the most advanced status wins:
        Completed > In Progress > Enrolled > Dropped.
        """
