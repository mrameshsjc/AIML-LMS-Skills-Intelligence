"""
Personalised learning path: which courses, in which order? (API 4)

PURPOSE
    API 3 ranks courses one by one. A learner also needs a PLAN: the smallest
    sensible set of courses that closes every gap, in an order they can
    actually follow (prerequisites first), with progress and one clear next
    step.

STEP BY STEP
    1. Gaps and scores  reuse API 3 (TrainingRecommendationService): the same
                        gaps, scores and reasons, so the two APIs never disagree.
    2. Select           for each gap skill (mandatory and largest first), "climb"
                        from the current level to the required level:
                          - pick a course the learner can START (it begins at or
                            below their level at that point);
                          - prefer a course they are already enrolled in, then
                            the one closing the most levels, then the best score;
                          - assume the course brings them to its level_to, and
                            repeat until the requirement is met.
                        AWS 1 -> 3: C-AWS-101 (0 -> 2), then C-AWS-201 (2 -> 4).
                        One course can raise several skills; every skill it raises
                        counts, so no course is chosen twice.
                        A COMPLETED course is evidence too: if the learner finished
                        C-PY-101 (Python 0 -> 2), they can start C-PY-201 (from 2)
                        even when their skill record still says 0. The path then
                        suggests a skill re-assessment. (Skill scores in APIs 1-3
                        stay based on the recorded levels.)
    3. Prerequisites    a chosen course whose prerequisite is not yet satisfied
                        (not completed, not covered by the learner's level) pulls
                        that prerequisite into the path, recursively.
    4. Order            a TOPOLOGICAL SORT: a course comes after every course it
                        depends on (its prerequisites, and lower courses on the
                        same skill ladder). Among courses that are free to go next,
                        the API 3 order decides: mandatory gaps first, then score.
                        A prerequisite inherits the priority of the course that
                        needs it, so it is placed just in time.
    5. Progress         match % now and after the path, skills met, completed
                        courses relevant to the target role, courses in progress,
                        total hours.
    6. Next action      the first step that can be started now.

WHY A GREEDY CLIMB, NOT AN OPTIMISER
    Each choice can be explained in one sentence ("starts at your level and
    closes the most of the gap"). An optimiser (e.g. minimum total hours)
    could find a slightly shorter plan, but not one a learner could check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import Course, CourseSkill, JobRole
from app.repositories.base import LmsRepository
from app.services.skill_analysis import ProfileSkill, SkillAnalysisService, SkillGap, compute_gaps
from app.services.training_recommendation import (
    ENROLLED_STATUSES,
    CompletionModel,
    PrerequisiteCheck,
    Recommendation,
    TrainingRecommendationService,
)

GAP, PREREQUISITE = "closes_gap", "prerequisite"


@dataclass(frozen=True)
class StepSkill:
    skill_name: str
    level_from: int
    level_to: int


@dataclass(frozen=True)
class PathStep:
    step: int
    course: Course
    purpose: str  # closes_gap | prerequisite
    status: str  # Not started | Enrolled | In Progress | Dropped before
    raises: list[StepSkill]
    prerequisites: list[PrerequisiteCheck]
    after_steps: list[int]  # steps that must be finished first
    ready_now: bool  # nothing in the path has to come first
    mandatory: bool
    score: float | None  # API 3 score; None for prerequisite-only courses
    reason: str
    cumulative_hours: int


@dataclass(frozen=True)
class GapPlan:
    gap: SkillGap
    closed_by: list[str]  # course IDs in the path that raise this skill
    level_after_path: int


@dataclass(frozen=True)
class Progress:
    match_percentage: float
    projected_match_percentage: float
    skills_met: int
    skills_required: int
    completed_courses: list[Course]  # completed courses that raise a target-role skill
    in_progress_courses: list[Course]
    total_steps: int
    total_hours: int


@dataclass(frozen=True)
class LearningPath:
    employee_id: str
    employee_name: str
    current_role: JobRole
    target_role: JobRole
    target_source: str
    current_skills: list[ProfileSkill]
    gaps: list[GapPlan]
    steps: list[PathStep]
    progress: Progress
    next_action: str
    uncovered_skills: list[str]
    notes: list[str] = field(default_factory=list)


def _status(history: dict[str, str], course_id: str) -> str:
    status = history.get(course_id)
    if status in ENROLLED_STATUSES:
        return status
    return "Dropped before" if status == "Dropped" else "Not started"


class LearningPathService:
    def __init__(self, repository: LmsRepository, completion_model: CompletionModel | None = None) -> None:
        self.repo = repository
        self.analysis = SkillAnalysisService(repository)
        self.recommender = TrainingRecommendationService(repository, completion_model)

    def build(
        self, employee_id: str, target_role_id: str | None = None, include_optional: bool = True
    ) -> LearningPath:
        """The learning path towards target_role_id (default: career goal, else current role)."""
        analysis = self.analysis.analyze(employee_id, target_role_id)
        recs = self.recommender.recommend(employee_id, target_role_id, max_results=10_000)
        ranked: dict[str, Recommendation] = {r.course.course_id: r for r in recs.recommendations}
        rank = {cid: i for i, cid in enumerate(ranked)}  # API 3 order: mandatory first, then score

        levels = self.repo.get_employee_skills(employee_id)
        history = self.repo.get_training_status(employee_id)
        courses = self.repo.get_courses()
        skills_of = {cid: self.repo.get_course_skills(cid) for cid in courses}

        self._names = {sid: sk.name for sid, sk in self.repo.get_skills().items()}
        gaps = [g for g in recs.gaps if include_optional or g.mandatory]
        evidence = _completed_evidence(history, skills_of)
        candidates = [
            cid
            for cid, c in courses.items()
            if c.is_active and history.get(cid) != "Completed" and skills_of[cid]
        ]
        chosen, reached, uncovered = self._select(
            gaps, candidates, rank, levels, evidence, skills_of, history
        )
        prereq_steps, depends_on, notes = self._add_prerequisites(chosen, levels, history, courses)
        depends_on = self._add_ladder_order(chosen + prereq_steps, depends_on, skills_of, levels)
        order = self._order(chosen + prereq_steps, depends_on, rank)

        steps = self._steps(
            order, depends_on, ranked, prereq_steps, levels, history, courses, skills_of, gaps, evidence
        )
        gap_plans = [
            GapPlan(
                g,
                [
                    s.course.course_id
                    for s in steps
                    if g.skill_id in {cs.skill_id for cs in skills_of[s.course.course_id]}
                ],
                reached.get(g.skill_id, g.current_level),
            )
            for g in gaps
        ]
        projected = compute_gaps(
            {**levels, **reached},
            self.repo.get_role_requirements(analysis.target_role.role_id),
            self.repo.get_skills(),
        )
        progress = self._progress(analysis, projected.match_percentage, history, courses, skills_of, steps)

        notes = [n for n in recs.notes if "nothing to recommend" not in n] + notes
        outdated = [
            f"{g.skill_name} (record: level {g.current_level}; "
            f"completed {evidence[g.skill_id][1]} ends at level {evidence[g.skill_id][0]})"
            for g in gaps
            if evidence.get(g.skill_id, (0, ""))[0] > g.current_level
        ]
        if outdated:
            notes.append(
                "Your skill record looks lower than the courses you completed: "
                + "; ".join(outdated)
                + ". The path builds on the completed courses; ask your manager for a skill re-assessment."
            )
        if not include_optional and len(gaps) < len(recs.gaps):
            notes.append("Optional skills are left out (include_optional=false).")
        if uncovered:
            notes.append(
                "No available course fully closes: "
                + ", ".join(f"{name} (reaches level {got} of {need})" for name, got, need in uncovered)
                + ". Consider on-the-job practice or a mentor for these."
            )
        if analysis.target_source == "current_role":
            notes.append(
                "No career goal is recorded, so the path targets the current role. "
                "Pass target_role_id to plan for another role."
            )

        return LearningPath(
            employee_id=analysis.employee_id,
            employee_name=analysis.employee_name,
            current_role=analysis.current_role,
            target_role=analysis.target_role,
            target_source=analysis.target_source,
            current_skills=analysis.skill_profile,
            gaps=gap_plans,
            steps=steps,
            progress=progress,
            next_action=_next_action(steps, gaps, uncovered, analysis.target_role),
            uncovered_skills=[name for name, _, _ in uncovered],
            notes=notes,
        )

    # --- 2. Select -----------------------------------------------------------------
    def _select(self, gaps, candidates, rank, levels, evidence, skills_of, history):
        big = len(candidates) + len(rank)
        sim = dict(levels)  # the learner's levels as the plan progresses
        chosen: list[str] = []
        uncovered: list[tuple[str, int, int]] = []
        for gap in gaps:
            sid, need = gap.skill_id, gap.required_level
            while sim.get(sid, 0) < need:
                now = sim.get(sid, 0)
                can_start_at = max(now, evidence.get(sid, (0, ""))[0])  # completed courses count as evidence
                options = []
                for cid in candidates:
                    cs = next((c for c in skills_of[cid] if c.skill_id == sid), None)
                    if cid in chosen or cs is None or cs.level_to <= now:
                        continue
                    startable = cs.level_from <= can_start_at
                    gain = min(cs.level_to, need) - now
                    enrolled = history.get(cid) in ENROLLED_STATUSES
                    key = (
                        not startable,
                        0 if startable else cs.level_from,
                        not enrolled,
                        -gain,
                        rank.get(cid, big),
                        cid,
                    )
                    options.append((key, cid))
                if not options:
                    uncovered.append((gap.skill_name, now, need))
                    break
                pick = min(options)[1]
                chosen.append(pick)
                for cs in skills_of[pick]:  # every skill the course raises counts
                    sim[cs.skill_id] = max(sim.get(cs.skill_id, 0), cs.level_to)
        reached = {g.skill_id: min(sim.get(g.skill_id, 0), g.required_level) for g in gaps}
        return chosen, reached, uncovered

    # --- 3. Prerequisites -----------------------------------------------------------------
    def _add_prerequisites(self, chosen, levels, history, courses):
        added: list[str] = []
        depends_on: dict[str, set[str]] = {cid: set() for cid in chosen}
        notes: list[str] = []
        queue = list(chosen)
        while queue:
            cid = queue.pop(0)
            for check in self.recommender.check_prerequisites(cid, levels, history, courses):
                if check.satisfied:
                    continue
                pid = check.course_id
                if pid not in courses or not courses[pid].is_active:
                    notes.append(f"{cid} needs {pid}, which is not available; ask your L&D team.")
                    continue
                depends_on[cid].add(pid)
                if pid not in depends_on:
                    depends_on[pid] = set()
                    added.append(pid)
                    queue.append(pid)
        return added, depends_on, notes

    @staticmethod
    def _add_ladder_order(path, depends_on, skills_of, levels):
        """Lower courses on the same skill come first (AWS-101 before AWS-201), if not already ordered."""
        for a in path:
            for b in path:
                if a == b:
                    continue
                for ca in skills_of[a]:
                    for cb in skills_of[b]:
                        if ca.skill_id == cb.skill_id and ca.level_from < cb.level_from:
                            if a not in _ancestors(b, depends_on) and b not in _ancestors(a, depends_on):
                                depends_on[b].add(a)
        return depends_on

    # --- 4. Order ------------------------------------------------------------------------
    @staticmethod
    def _order(path, depends_on, rank):
        big = len(rank) + len(path)
        # A prerequisite takes the priority of the most urgent course that needs it.
        priority = {cid: rank.get(cid, big) for cid in path}
        for cid in path:
            for dep in _ancestors(cid, depends_on):
                priority[dep] = min(priority[dep], priority[cid])
        done: list[str] = []
        remaining = set(path)
        while remaining:
            free = [c for c in remaining if depends_on[c] <= set(done)]
            if not free:  # a loop in the data: keep going rather than fail
                free = list(remaining)
            nxt = min(free, key=lambda c: (priority[c], rank.get(c, big), c))
            done.append(nxt)
            remaining.discard(nxt)
        return done

    # --- 5. Steps and progress -------------------------------------------------------------
    def _steps(
        self, order, depends_on, ranked, prereq_steps, levels, history, courses, skills_of, gaps, evidence
    ):
        gap_by_skill = {g.skill_id: g for g in gaps}
        number = {cid: i for i, cid in enumerate(order, start=1)}
        needed_by: dict[str, list[str]] = {}
        for cid, deps in depends_on.items():
            for dep in deps:
                needed_by.setdefault(dep, []).append(cid)
        steps, hours = [], 0
        for cid in order:
            course = courses[cid]
            hours += course.duration_hours
            rec = ranked.get(cid)
            prereqs = self.recommender.check_prerequisites(cid, levels, history, courses)
            after = sorted(number[d] for d in depends_on[cid])
            if rec is not None and cid not in prereq_steps:
                purpose, reason, score, mandatory = GAP, rec.reason, rec.score, rec.addresses_mandatory_gap
            elif cid not in prereq_steps:  # chosen because a completed course shows a higher level
                raised = [gap_by_skill[cs.skill_id] for cs in skills_of[cid] if cs.skill_id in gap_by_skill]
                g = raised[0]
                cs = next(c for c in skills_of[cid] if c.skill_id == g.skill_id)
                level, done = evidence.get(g.skill_id, (0, ""))
                purpose, score, mandatory = GAP, None, any(r.mandatory for r in raised)
                reason = (
                    f"Takes {g.skill_name} from level {cs.level_from} to {cs.level_to} "
                    f"(needed: {g.required_level}). "
                    f"It builds on {done}, which you completed (ends at level {level}), although your skill "
                    f"record shows level {g.current_level}."
                )
            else:
                users = sorted(needed_by.get(cid, []), key=number.get)
                purpose, score = PREREQUISITE, (rec.score if rec else None)
                mandatory = any(ranked[u].addresses_mandatory_gap for u in users if u in ranked)
                reason = (
                    "Prerequisite for "
                    + ", ".join(f"step {number[u]} ({u})" for u in users)
                    + ": complete it first."
                )
                if rec is not None:
                    reason += " " + rec.reason
            if after:
                first = ", ".join(f"step {number[d]} ({d})" for d in sorted(depends_on[cid], key=number.get))
                reason += f" In this path, {first} comes first and prepares you for it."
            steps.append(
                PathStep(
                    step=number[cid],
                    course=course,
                    purpose=purpose,
                    status=_status(history, cid),
                    raises=[
                        StepSkill(self._names.get(cs.skill_id, cs.skill_id), cs.level_from, cs.level_to)
                        for cs in skills_of[cid]
                    ],
                    prerequisites=prereqs,
                    after_steps=after,
                    ready_now=not after,
                    mandatory=mandatory,
                    score=score,
                    reason=reason,
                    cumulative_hours=hours,
                )
            )
        return steps

    def _progress(self, analysis, projected, history, courses, skills_of, steps) -> Progress:
        role_skills = {s.skill_id for s in analysis.summary.skills}
        completed = [
            courses[cid]
            for cid, status in history.items()
            if status == "Completed"
            and cid in courses
            and role_skills & {cs.skill_id for cs in skills_of[cid]}
        ]
        return Progress(
            match_percentage=analysis.summary.match_percentage,
            projected_match_percentage=projected,
            skills_met=sum(1 for s in analysis.summary.skills if s.gap == 0),
            skills_required=len(analysis.summary.skills),
            completed_courses=completed,
            in_progress_courses=[s.course for s in steps if s.status in ENROLLED_STATUSES],
            total_steps=len(steps),
            total_hours=steps[-1].cumulative_hours if steps else 0,
        )


def _ancestors(cid: str, depends_on: dict[str, set[str]]) -> set[str]:
    """Every course that must come before cid, directly or indirectly."""
    seen: set[str] = set()
    stack = list(depends_on.get(cid, ()))
    while stack:
        dep = stack.pop()
        if dep not in seen:
            seen.add(dep)
            stack.extend(depends_on.get(dep, ()))
    return seen


def _completed_evidence(
    history: dict[str, str], skills_of: dict[str, list[CourseSkill]]
) -> dict[str, tuple[int, str]]:
    """{skill_id: (highest level_to of a completed course, that course)}."""
    best: dict[str, tuple[int, str]] = {}
    for cid, status in history.items():
        if status == "Completed":
            for cs in skills_of.get(cid, []):
                if cs.level_to > best.get(cs.skill_id, (0, ""))[0]:
                    best[cs.skill_id] = (cs.level_to, cid)
    return best


def _next_action(steps: list[PathStep], gaps: list[SkillGap], uncovered, target: JobRole) -> str:
    if not gaps:
        return (
            f"You already meet every requirement for {target.title}. "
            "Choose a new target role (target_role_id) to plan your next step."
        )
    first = next((s for s in steps if s.ready_now), None)
    if first is None:
        names = ", ".join(name for name, _, _ in uncovered)
        return (
            f"No course in the catalogue closes your gaps ({names}); agree a practice plan with your manager."
        )
    c = first.course
    if first.status == "In Progress":
        return f"Continue {c.course_id} '{c.title}' (step {first.step}), which you have already started."
    if first.status == "Enrolled":
        return f"Start {c.course_id} '{c.title}' (step {first.step}): you are already enrolled."
    return f"Enrol in {c.course_id} '{c.title}' (step {first.step}, {c.duration_hours} h). {first.reason}"
