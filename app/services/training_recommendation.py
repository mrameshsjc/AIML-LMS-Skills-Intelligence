"""
Training recommendations: which courses close an employee's skill gaps? (API 3)

PURPOSE
    For the gaps found by skill analysis (API 1), find courses that raise
    those skills, score each course, and explain the score in plain language.

STEP BY STEP
    1. Gaps        run SkillAnalysisService for the target role (same rules as API 1).
    2. Candidates  active courses that raise at least one gap skill by at least one
                   level, excluding courses the employee already completed.
    3. Score       four parts, each between 0 and 1 (see below).
    4. Order       courses for MANDATORY gaps first; within that, highest score first.
    5. Explain     a reason built from the same numbers as the score.

THE HYBRID SCORE (project blueprint, section 4.2)
    score = 0.50 x gap_coverage + 0.20 x level_fit + 0.15 x prereq_ready
          + 0.15 x completion_probability

    gap_coverage   how much of the gap in the course's skills it closes.
                   Useful gain per skill = min(level_to, required) - max(current, level_from).
                   SQL 2 -> needed 4, course 2 -> 4: gain 2 of gap 2 = 1.0.
                   AWS 1 -> needed 3, course 0 -> 2: gain 1 of gap 2 = 0.5.
    level_fit      does the course start where the learner is?
                   starts ABOVE the learner by n levels: 1 - 0.5 x n (1 above = 0.5, 2+ = 0)
                   starts BELOW (some repetition) by n levels: 1 - 0.2 x n, never below 0.5
                   Phase 4 chart 05: completion drops from 74 % to 41 % when a course
                   starts 2+ levels too high - this is why fit matters.
    prereq_ready   share of the course's prerequisites that are satisfied, either
                   COMPLETED or already covered by the learner's skill level (someone
                   with Docker 2 does not need "Docker Fundamentals", which ends at 2).
    completion_probability
                   predicted chance of finishing, from the ML model in Phase 8. Until
                   that model exists this part is missing, and its weight is shared
                   proportionally among the other three (the response says so).

WHY RULES AND NOT A MODEL FOR THE MAIN SCORE
    Every part has a clear meaning a learner and a manager can check. The ML
    model adds one learned signal (completion) on top, without hiding the rest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.errors import InvalidInputError
from app.domain.models import Course, CourseSkill, JobRole
from app.repositories.base import LmsRepository
from app.services.skill_analysis import SkillAnalysisService, SkillGap

WEIGHTS = {"gap_coverage": 0.50, "level_fit": 0.20, "prereq_ready": 0.15, "completion_probability": 0.15}
ENROLLED_STATUSES = ("Enrolled", "In Progress")

# A completion model: (employee_id, course_id) -> probability 0..1, or None if unknown.
CompletionModel = Callable[[str, str], float | None]


@dataclass(frozen=True)
class SkillContribution:
    """What one course does for one gap skill."""

    skill_id: str
    skill_name: str
    current_level: int
    required_level: int
    level_from: int
    level_to: int
    gain: int  # gap levels this course closes
    gap: int  # the employee's gap in this skill
    mandatory: bool
    weight: float


@dataclass(frozen=True)
class PrerequisiteCheck:
    course_id: str
    title: str
    satisfied: bool
    how: str  # completed | skill level | not yet


@dataclass(frozen=True)
class Recommendation:
    course: Course
    contributions: list[SkillContribution]
    prerequisites: list[PrerequisiteCheck]
    components: dict[str, float | None]
    score: float
    enrollment_status: str | None
    reason: str
    rank: int = 0

    @property
    def addresses_mandatory_gap(self) -> bool:
        return any(c.mandatory for c in self.contributions)


@dataclass(frozen=True)
class RecommendationResult:
    employee_id: str
    employee_name: str
    target_role: JobRole
    target_source: str
    gap_score: float
    match_percentage: float
    gaps: list[SkillGap]
    recommendations: list[Recommendation]
    uncovered_skills: list[str]
    weights_used: dict[str, float]
    notes: list[str] = field(default_factory=list)


def useful_gain(current: int, required: int, cs: CourseSkill) -> int:
    """Gap levels a course closes for one skill: overlap of [current, required] and [from, to]."""
    return max(0, min(cs.level_to, required) - max(current, cs.level_from))


def level_fit(current: int, level_from: int) -> float:
    """1.0 when the course starts at the learner's level; lower when it starts above or far below."""
    if level_from > current:
        return max(0.0, 1 - 0.5 * (level_from - current))
    return max(0.5, 1 - 0.2 * (current - level_from))


def combine(components: dict[str, float | None]) -> tuple[float, dict[str, float]]:
    """Weighted average of the available parts; missing parts' weight is shared proportionally."""
    available = {k: WEIGHTS[k] for k, v in components.items() if v is not None}
    total = sum(available.values())
    weights = {k: round(w / total, 3) for k, w in available.items()}
    score = sum(components[k] * w / total for k, w in available.items())
    return round(score, 2), weights


class TrainingRecommendationService:
    def __init__(self, repository: LmsRepository, completion_model: CompletionModel | None = None) -> None:
        self.repo = repository
        self.analysis = SkillAnalysisService(repository)
        self.completion_model = completion_model

    def recommend(
        self,
        employee_id: str,
        target_role_id: str | None = None,
        skills: list[str] | None = None,
        max_results: int = 10,
        include_enrolled: bool = True,
    ) -> RecommendationResult:
        """Recommend courses for an employee's gaps towards a target role.

        target_role_id    as in skill analysis (default: career goal, else current role)
        skills            only recommend for these skills (names or IDs); default: all gaps
        max_results       how many courses to return
        include_enrolled  also list courses the employee is already enrolled in
        """
        analysis = self.analysis.analyze(employee_id, target_role_id)
        target = analysis.target_role
        gaps = {g.skill_id: g for g in analysis.summary.gaps}
        if skills:
            wanted = self._resolve_skills(skills)
            gaps = {sid: g for sid, g in gaps.items() if sid in wanted}

        levels = self.repo.get_employee_skills(employee_id)
        history = self.repo.get_training_status(employee_id)
        courses = self.repo.get_courses()

        candidates = []
        for course in courses.values():
            if not course.is_active or history.get(course.course_id) == "Completed":
                continue
            status = history.get(course.course_id)
            if status in ENROLLED_STATUSES and not include_enrolled:
                continue
            contributions = self._contributions(course.course_id, gaps)
            if contributions:
                candidates.append(
                    self._score(employee_id, course, contributions, status, levels, history, courses, target)
                )

        candidates.sort(key=lambda r: (not r.addresses_mandatory_gap, -r.score, r.course.course_id))
        ranked = [_with_rank(r, i) for i, r in enumerate(candidates, start=1)][: max(1, max_results)]

        covered = {c.skill_id for r in candidates for c in r.contributions}
        uncovered = [g.skill_name for sid, g in gaps.items() if sid not in covered]
        _, weights = combine(
            {k: (1.0 if k != "completion_probability" or self.completion_model else None) for k in WEIGHTS}
        )

        notes = []
        if not gaps:
            notes.append(
                f"No skill gaps for {target.title}{' in the chosen skills' if skills else ''}: "
                "nothing to recommend."
            )
        if self.completion_model is None:
            notes.append(
                "No completion model is loaded (train one with data_science/11_train_model.py); "
                "its 15% weight is shared proportionally among the other three parts."
            )
        else:
            version = getattr(self.completion_model, "version", None)
            notes.append(
                f"completion_probability comes from the ML model{f' version {version}' if version else ''}, "
                "trained on SYNTHETIC data: it shows the method, not real-world accuracy."
            )
        if uncovered:
            notes.append(f"No available course closes the gap in: {', '.join(uncovered)}.")

        return RecommendationResult(
            employee_id=analysis.employee_id,
            employee_name=analysis.employee_name,
            target_role=target,
            target_source=analysis.target_source,
            gap_score=analysis.summary.gap_score,
            match_percentage=analysis.summary.match_percentage,
            gaps=list(gaps.values()),
            recommendations=ranked,
            uncovered_skills=uncovered,
            weights_used=weights,
            notes=notes,
        )

    # --- helpers -------------------------------------------------------------
    def _resolve_skills(self, keys: list[str]) -> set[str]:
        skills = self.repo.get_skills()
        by_name = {s.name.lower(): sid for sid, s in skills.items()}
        resolved = set()
        for key in keys:
            sid = key if key in skills else by_name.get(key.strip().lower())
            if sid is None:
                raise InvalidInputError("UNKNOWN_SKILL", f"Skill '{key}' does not exist.")
            resolved.add(sid)
        return resolved

    def _contributions(self, course_id: str, gaps: dict[str, SkillGap]) -> list[SkillContribution]:
        result = []
        for cs in self.repo.get_course_skills(course_id):
            gap = gaps.get(cs.skill_id)
            if gap is None:
                continue
            gain = useful_gain(gap.current_level, gap.required_level, cs)
            if gain > 0:
                result.append(
                    SkillContribution(
                        cs.skill_id,
                        gap.skill_name,
                        gap.current_level,
                        gap.required_level,
                        cs.level_from,
                        cs.level_to,
                        gain,
                        gap.gap,
                        gap.mandatory,
                        gap.weight,
                    )
                )
        return result

    def _prerequisites(
        self, course_id: str, levels: dict[str, int], history: dict[str, str], courses: dict[str, Course]
    ) -> list[PrerequisiteCheck]:
        checks = []
        for pid in self.repo.get_prerequisites(course_id):
            title = courses[pid].title if pid in courses else pid
            if history.get(pid) == "Completed":
                checks.append(PrerequisiteCheck(pid, title, True, "completed"))
                continue
            taught = self.repo.get_course_skills(pid)
            if taught and all(levels.get(cs.skill_id, 0) >= cs.level_to for cs in taught):
                checks.append(PrerequisiteCheck(pid, title, True, "skill level"))
            else:
                checks.append(PrerequisiteCheck(pid, title, False, "not yet"))
        return checks

    def _score(
        self, employee_id, course, contributions, status, levels, history, courses, target
    ) -> Recommendation:
        coverage = sum(c.weight * c.gain for c in contributions) / sum(
            c.weight * c.gap for c in contributions
        )
        fit = min(level_fit(c.current_level, c.level_from) for c in contributions)
        prereqs = self._prerequisites(course.course_id, levels, history, courses)
        ready = sum(p.satisfied for p in prereqs) / len(prereqs) if prereqs else 1.0
        completion = self.completion_model(employee_id, course.course_id) if self.completion_model else None
        components = {
            "gap_coverage": round(coverage, 2),
            "level_fit": round(fit, 2),
            "prereq_ready": round(ready, 2),
            "completion_probability": None if completion is None else round(completion, 2),
        }
        score, _ = combine(components)
        reason = _reason(course, contributions, prereqs, status, target)
        return Recommendation(course, contributions, prereqs, components, score, status, reason)


def _with_rank(rec: Recommendation, rank: int) -> Recommendation:
    return Recommendation(
        rec.course,
        rec.contributions,
        rec.prerequisites,
        rec.components,
        rec.score,
        rec.enrollment_status,
        rec.reason,
        rank,
    )


def _reason(
    course: Course,
    contributions: list[SkillContribution],
    prereqs: list[PrerequisiteCheck],
    status: str | None,
    target: JobRole,
) -> str:
    """Plain-language explanation built from the same numbers as the score."""
    main = max(contributions, key=lambda c: (c.gain, c.mandatory))
    text = (
        f"Your {main.skill_name} is level {main.current_level} and {target.title} needs level "
        f"{main.required_level}; this course takes it from level {main.level_from} to {main.level_to}"
    )
    text += f", closing {main.gain} of the {main.gap} levels." if main.gain < main.gap else "."
    others = [c.skill_name for c in contributions if c is not main]
    if others:
        text += f" It also raises {', '.join(others)}."
    if main.level_from < main.current_level:
        start, now = main.level_from, main.current_level
        text += f" It starts at level {start}, below your level {now}: part of it is revision."
    if main.level_from > main.current_level:
        text += (
            f" It starts at level {main.level_from}, above your level {main.current_level}, "
            "so it may be hard without preparation."
        )
    if not prereqs:
        text += " No prerequisites."
    elif all(p.satisfied for p in prereqs):
        how = {"completed": "completed", "skill level": "covered by your current level"}
        text += " Prerequisites met (" + ", ".join(f"{p.course_id} {how[p.how]}" for p in prereqs) + ")."
    else:
        text += " Complete first: " + ", ".join(p.course_id for p in prereqs if not p.satisfied) + "."
    if status in ENROLLED_STATUSES:
        text += f" You are already enrolled ({status})."
    elif status == "Dropped":
        text += " You started this course before but did not finish it."
    return text
