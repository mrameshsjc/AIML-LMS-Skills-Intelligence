"""
Skill analysis: how far is an employee from a target role? (API 1)

PURPOSE
    Compare an employee's current skill levels with the levels a job role
    requires, and explain the result in plain language:
      - per skill: current level, required level, gap, status;
      - missing skills (level 0);
      - a gap score and a match percentage;
      - suggestions, most important first.

THE FORMULAS (from the project blueprint)
    For each required skill s: required level R, current level C (0 if the
    employee does not have it), weight w (all 1.0 in the sample data):

        gap        g = max(0, R - C)
        gap score    = 100 * sum(w * g) / sum(w * R)        0 = role-ready, 100 = nothing yet
        match %      = 100 * sum(w * min(C, R)) / sum(w * R)

    Being ABOVE the required level never hides a gap elsewhere: min(C, R)
    gives no extra credit beyond what the role needs.

    Worked example (E1001 -> Data Engineer, all weights 1):
        required  4 + 4 + 3 + 2 + 3 = 16
        gaps      1 + 2 + 2 + 0 + 1 = 6   -> gap score = 100 * 6 / 16  = 37.5
        covered   3 + 2 + 1 + 2 + 2 = 10  -> match     = 100 * 10 / 16 = 62.5 %

WHY A FORMULA, NOT A MACHINE-LEARNING MODEL
    The answer is arithmetic on known levels. A model would add error and hide
    the reason. Rules are exact, fast and explainable; ML is used later only
    where there is something to learn (Phase 8).

REUSE
    compute_gaps() is a pure function (no data access), so Phase 6 role
    matching runs the same calculation for every role.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import InvalidInputError, NotFoundError
from app.domain.models import JobRole, RoleRequirement, Skill
from app.repositories.base import LmsRepository

MET, BELOW, MISSING = "met", "below_required", "missing"


@dataclass(frozen=True)
class SkillGap:
    skill_id: str
    skill_name: str
    category: str
    current_level: int
    required_level: int
    gap: int
    mandatory: bool
    weight: float
    status: str  # met | below_required | missing


@dataclass(frozen=True)
class GapSummary:
    skills: list[SkillGap]
    gap_score: float
    match_percentage: float

    @property
    def gaps(self) -> list[SkillGap]:
        return [s for s in self.skills if s.gap > 0]


def compute_gaps(
    current: dict[str, int], requirements: list[RoleRequirement], skills: dict[str, Skill]
) -> GapSummary:
    """Compare current levels with requirements. Pure calculation, no data access.

    Skills are ordered by importance: mandatory first, then the largest gap,
    then alphabetically, so the most urgent gap is always first.
    """
    rows = []
    for req in requirements:
        level = current.get(req.skill_id, 0)
        gap = max(0, req.required_level - level)
        status = MET if gap == 0 else MISSING if level == 0 else BELOW
        skill = skills.get(req.skill_id, Skill(req.skill_id, req.skill_id, "Unknown"))
        rows.append(
            SkillGap(
                skill.skill_id,
                skill.name,
                skill.category,
                level,
                req.required_level,
                gap,
                req.mandatory,
                req.weight,
                status,
            )
        )
    rows.sort(key=lambda s: (not s.mandatory, -s.gap, s.skill_name))

    total = sum(s.weight * s.required_level for s in rows)
    if total == 0:  # a role with no requirements: nothing to close
        return GapSummary(rows, 0.0, 100.0)
    gap_score = 100 * sum(s.weight * s.gap for s in rows) / total
    match = 100 * sum(s.weight * min(s.current_level, s.required_level) for s in rows) / total
    return GapSummary(rows, round(gap_score, 1), round(match, 1))


def suggestion_for(gap: SkillGap) -> str:
    """One plain-language action for one skill gap."""
    must = " (mandatory)" if gap.mandatory else ""
    if gap.status == MISSING:
        return f"Learn {gap.skill_name}{must}: build it from scratch to level {gap.required_level}."
    return f"Raise {gap.skill_name}{must} from level {gap.current_level} to {gap.required_level}."


@dataclass(frozen=True)
class ProfileSkill:
    skill_id: str
    skill_name: str
    level: int
    required_for_target: bool


@dataclass(frozen=True)
class SkillAnalysisResult:
    employee_id: str
    employee_name: str
    current_role: JobRole
    target_role: JobRole
    target_source: str  # request | career_goal | current_role
    summary: GapSummary
    skill_profile: list[ProfileSkill]
    suggestions: list[str]
    explanation: str
    overrides_applied: list[str] = field(default_factory=list)

    @property
    def missing_skills(self) -> list[str]:
        return [s.skill_name for s in self.summary.skills if s.status == MISSING]

    @property
    def mandatory_gaps(self) -> int:
        return sum(1 for s in self.summary.gaps if s.mandatory)

    @property
    def role_ready(self) -> bool:
        return not self.summary.gaps


class SkillAnalysisService:
    """Analyse one employee against one role, using any LmsRepository."""

    def __init__(self, repository: LmsRepository) -> None:
        self.repo = repository

    def analyze(
        self,
        employee_id: str,
        target_role_id: str | None = None,
        skill_overrides: dict[str, int] | None = None,
    ) -> SkillAnalysisResult:
        """Analyse an employee's skills against a target role.

        target_role_id   the role to compare with. If omitted: the employee's
                         career goal; if there is none, their current role.
        skill_overrides  {skill name or id: level} to try "what if" levels
                         (level 0 = does not have the skill). Stored data is
                         never changed.

        Raises NotFoundError for an unknown employee or role and
        InvalidInputError for an unknown skill or a level outside 0-5.
        """
        employee = self.repo.get_employee(employee_id)
        if employee is None:
            raise NotFoundError("EMPLOYEE_NOT_FOUND", f"Employee {employee_id} does not exist.")

        if target_role_id:
            source = "request"
        elif goal := self.repo.get_career_goal(employee_id):
            target_role_id, source = goal, "career_goal"
        else:
            target_role_id, source = employee.current_role_id, "current_role"
        target = self.repo.get_role(target_role_id)
        if target is None:
            raise NotFoundError("ROLE_NOT_FOUND", f"Job role {target_role_id} does not exist.")
        current_role = self.repo.get_role(employee.current_role_id)

        skills = self.repo.get_skills()
        levels = self.repo.get_employee_skills(employee_id)
        applied = self._apply_overrides(levels, skill_overrides or {}, skills)

        requirements = self.repo.get_role_requirements(target.role_id)
        summary = compute_gaps(levels, requirements, skills)
        required_ids = {r.skill_id for r in requirements}
        profile = sorted(
            (
                ProfileSkill(sid, skills[sid].name, lvl, sid in required_ids)
                for sid, lvl in levels.items()
                if lvl > 0
            ),
            key=lambda p: (not p.required_for_target, -p.level, p.skill_name),
        )

        return SkillAnalysisResult(
            employee_id=employee.employee_id,
            employee_name=employee.full_name,
            current_role=current_role,
            target_role=target,
            target_source=source,
            summary=summary,
            skill_profile=profile,
            suggestions=self._suggestions(summary, target),
            explanation=self._explain(employee.full_name, summary, target),
            overrides_applied=applied,
        )

    @staticmethod
    def _apply_overrides(
        levels: dict[str, int], overrides: dict[str, int], skills: dict[str, Skill]
    ) -> list[str]:
        """Apply what-if levels in place; accept skill IDs or names (any letter case)."""
        by_name = {s.name.lower(): s.skill_id for s in skills.values()}
        applied = []
        for key, level in overrides.items():
            skill_id = key if key in skills else by_name.get(key.strip().lower())
            if skill_id is None:
                raise InvalidInputError("UNKNOWN_SKILL", f"Skill '{key}' does not exist.")
            if not 0 <= level <= 5:
                raise InvalidInputError(
                    "INVALID_LEVEL", f"Level for '{key}' must be between 0 and 5, not {level}."
                )
            if level == 0:
                levels.pop(skill_id, None)
            else:
                levels[skill_id] = level
            applied.append(f"{skills[skill_id].name} = {level}")
        return applied

    @staticmethod
    def _suggestions(summary: GapSummary, target: JobRole) -> list[str]:
        if not summary.gaps:
            return [f"You meet every skill requirement for {target.title}."]
        return [suggestion_for(g) for g in summary.gaps]

    @staticmethod
    def _explain(name: str, summary: GapSummary, target: JobRole) -> str:
        total, gaps = len(summary.skills), summary.gaps
        if not gaps:
            return f"{name} meets all {total} skill requirements for {target.title}."
        mandatory = sum(1 for g in gaps if g.mandatory)
        return (
            f"{name} meets {total - len(gaps)} of {total} skill requirements for {target.title}; "
            f"{len(gaps)} need improvement ({mandatory} mandatory). "
            f"Match {summary.match_percentage:g}%, gap score {summary.gap_score:g} (0 = role-ready)."
        )
