"""
Role matching: which job roles fit an employee best? (API 2)

PURPOSE
    Compare one employee's skills with EVERY job role (or a chosen list) and
    rank the roles by match percentage. For each role, show the skills that
    match, the skills that need improvement and the skills that are missing,
    with a readiness label and a one-line explanation. Then suggest related
    roles using TF-IDF similarity (see role_similarity.py).

SAME NUMBERS AS API 1
    Each role is scored with compute_gaps() from skill_analysis.py - the
    exact formula of API 1. The match % for Data Engineer here is always the
    same as POST /skills/analyze returns for Data Engineer.

RANKING
    1. higher match percentage first;
    2. ties: fewer mandatory gaps first;
    3. still tied: alphabetical by title.

READINESS LABELS (from match percentage)
    Ready        100 % - every requirement met
    Close        80-99 %
    Developing   50-79 %
    Early        below 50 %
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import NotFoundError
from app.domain.models import JobRole
from app.repositories.base import LmsRepository
from app.services.role_similarity import RoleSimilarityIndex, SimilarRole
from app.services.skill_analysis import MISSING, GapSummary, SkillGap, apply_skill_overrides, compute_gaps

READINESS_BANDS = ((100.0, "Ready"), (80.0, "Close"), (50.0, "Developing"), (0.0, "Early"))
MAX_GAPS_IN_EXPLANATION = 3


def readiness(match_percentage: float) -> str:
    return next(label for threshold, label in READINESS_BANDS if match_percentage >= threshold)


def explain_match(summary: GapSummary) -> str:
    """e.g. 'Meets 1 of 5 skills; gaps: AWS 1->3, SQL 2->4, Python 3->4 (+1 more). 3 mandatory gaps.'"""
    total, gaps = len(summary.skills), summary.gaps
    if not gaps:
        return f"Meets all {total} required skills."
    shown = ", ".join(
        f"{g.skill_name} {'missing' if g.status == MISSING else g.current_level}->{g.required_level}"
        for g in gaps[:MAX_GAPS_IN_EXPLANATION]
    )
    more = f" (+{len(gaps) - MAX_GAPS_IN_EXPLANATION} more)" if len(gaps) > MAX_GAPS_IN_EXPLANATION else ""
    mandatory = sum(1 for g in gaps if g.mandatory)
    tail = (
        f" {mandatory} mandatory gap{'s' if mandatory != 1 else ''}." if mandatory else " No mandatory gaps."
    )
    return f"Meets {total - len(gaps)} of {total} skills; gaps: {shown}{more}.{tail}"


@dataclass(frozen=True)
class RoleMatch:
    role: JobRole
    summary: GapSummary
    is_current_role: bool
    is_career_goal: bool
    rank: int = 0

    @property
    def match_percentage(self) -> float:
        return self.summary.match_percentage

    @property
    def readiness(self) -> str:
        return readiness(self.summary.match_percentage)

    @property
    def mandatory_gaps(self) -> int:
        return sum(1 for g in self.summary.gaps if g.mandatory)

    def skills_with(self, status: str) -> list[SkillGap]:
        return [s for s in self.summary.skills if s.status == status]

    @property
    def explanation(self) -> str:
        return explain_match(self.summary)


@dataclass(frozen=True)
class RelatedRole:
    similar: SimilarRole
    shared_skill_names: list[str]
    employee_match: float  # the employee's match % for this related role


@dataclass(frozen=True)
class RoleMatchResult:
    employee_id: str
    employee_name: str
    current_role: JobRole
    career_goal: JobRole | None
    roles_considered: int
    matches: list[RoleMatch]  # top_n, ranked
    target: RoleMatch | None  # always present when a target was requested, even if outside top_n
    related_to: JobRole | None
    related_roles: list[RelatedRole]
    summary: str
    overrides_applied: list[str] = field(default_factory=list)


class RoleMatchingService:
    def __init__(self, repository: LmsRepository) -> None:
        self.repo = repository
        roles = repository.list_roles()
        self.similarity = RoleSimilarityIndex(
            roles, {r.role_id: repository.get_role_requirements(r.role_id) for r in roles}
        )

    def match(
        self,
        employee_id: str,
        role_ids: list[str] | None = None,
        target_role_id: str | None = None,
        top_n: int = 5,
        skill_overrides: dict[str, int] | None = None,
    ) -> RoleMatchResult:
        """Rank roles for an employee.

        role_ids        limit the comparison to these roles (default: all roles)
        target_role_id  a role of special interest; it is always reported in
                        `target`, and related roles are found for it. Default:
                        the employee's career goal, if any.
        top_n           how many ranked roles to return (1-20)
        skill_overrides what-if levels, as in skill analysis
        """
        employee = self.repo.get_employee(employee_id)
        if employee is None:
            raise NotFoundError("EMPLOYEE_NOT_FOUND", f"Employee {employee_id} does not exist.")

        if role_ids:
            roles = []
            for role_id in dict.fromkeys(role_ids):  # remove repeats, keep order
                role = self.repo.get_role(role_id)
                if role is None:
                    raise NotFoundError("ROLE_NOT_FOUND", f"Job role {role_id} does not exist.")
                roles.append(role)
        else:
            roles = self.repo.list_roles()

        goal_id = self.repo.get_career_goal(employee_id)
        target_id = target_role_id or goal_id
        target_role = self.repo.get_role(target_id) if target_id else None
        if target_role_id and target_role is None:
            raise NotFoundError("ROLE_NOT_FOUND", f"Job role {target_role_id} does not exist.")

        skills = self.repo.get_skills()
        levels = self.repo.get_employee_skills(employee_id)
        applied = apply_skill_overrides(levels, skill_overrides or {}, skills)

        def score(role: JobRole) -> RoleMatch:
            summary = compute_gaps(levels, self.repo.get_role_requirements(role.role_id), skills)
            return RoleMatch(role, summary, role.role_id == employee.current_role_id, role.role_id == goal_id)

        scored = [score(r) for r in roles]
        scored.sort(key=lambda m: (-m.match_percentage, m.mandatory_gaps, m.role.title))
        ranked = [
            RoleMatch(m.role, m.summary, m.is_current_role, m.is_career_goal, rank=i)
            for i, m in enumerate(scored, start=1)
        ]
        target = None
        if target_role is not None:
            target = next((m for m in ranked if m.role.role_id == target_role.role_id), None) or score(
                target_role
            )

        # Related roles: for the target if there is one, otherwise the best role that is not the current one.
        anchor = target_role or next((m.role for m in ranked if not m.is_current_role), None)
        related = self._related(anchor, levels, skills) if anchor else []

        top = ranked[: max(1, top_n)]
        return RoleMatchResult(
            employee_id=employee.employee_id,
            employee_name=employee.full_name,
            current_role=self.repo.get_role(employee.current_role_id),
            career_goal=self.repo.get_role(goal_id) if goal_id else None,
            roles_considered=len(ranked),
            matches=top,
            target=target,
            related_to=anchor,
            related_roles=related,
            summary=self._summarise(employee.full_name, ranked, target),
            overrides_applied=applied,
        )

    def _related(self, anchor: JobRole, levels: dict[str, int], skills) -> list[RelatedRole]:
        related = []
        for similar in self.similarity.similar_to(anchor.role_id):
            summary = compute_gaps(levels, self.repo.get_role_requirements(similar.role.role_id), skills)
            names = [skills[s].name for s in similar.shared_skill_ids if s in skills]
            related.append(RelatedRole(similar, names, summary.match_percentage))
        return related

    @staticmethod
    def _summarise(name: str, ranked: list[RoleMatch], target: RoleMatch | None) -> str:
        """One or two sentences: the best match, the best new role, and the target."""
        if not ranked:
            return f"No roles to compare for {name}."
        best = ranked[0]
        parts = [
            f"{name}'s best match is {best.role.title}"
            f"{' (current role)' if best.is_current_role else ''} at {best.match_percentage:g}%."
        ]
        other = next((m for m in ranked if not m.is_current_role), None)
        if best.is_current_role and other is not None:
            parts.append(
                f"Best other role: {other.role.title} at {other.match_percentage:g}% ({other.readiness})."
            )
        if target is not None:
            rank = f"rank {target.rank} of {len(ranked)}" if target.rank else "not in the compared roles"
            parts.append(
                f"Target {target.role.title}: {target.match_percentage:g}% ({target.readiness}, {rank})."
            )
        return " ".join(parts)
