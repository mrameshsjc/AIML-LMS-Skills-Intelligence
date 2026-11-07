"""
Feature engineering for the course-completion model (Phase 8).

PURPOSE
    Turn LMS data into a table of numbers and categories ("features") that a
    machine-learning model can learn from, with one row per enrolment and
    the answer ("label"): was the course completed (1) or dropped (0)?

WHAT IS A FEATURE?
    One measurable fact about an enrolment that might help predict the outcome.
    Each one below has a reason to exist:

      level_jump           how far the course starts above the learner's current level
                           (max over the course's skills; missing skill = level 0).
      skills_too_advanced  how many of the course's skills start 2+ levels above the
                           learner. EDA chart 05 showed completion falls from 74 % to
                           41 % at that point: the effect is a THRESHOLD, not a straight
                           line, and a linear model cannot find a threshold in
                           level_jump by itself. This feature hands it over directly -
                           a classic example of feature engineering guided by EDA.
      prereq_count         how many prerequisites the course has
      prereq_missing       prerequisites neither completed BEFORE this enrolment
                           nor covered by the learner's level
      duration_hours       longer courses may be harder to finish
      relevant_to_career   1 if the course raises a skill of the learner's current
                           or target role (motivation)
      prior_completed      courses the learner completed BEFORE this enrolment
      prior_dropped        courses the learner dropped BEFORE this enrolment
      difficulty           Beginner / Intermediate / Advanced     (category)
      delivery_mode        Online / Blended / Classroom           (category)
      seniority            Mid / Senior of the learner's role     (category)

NO DATA LEAKAGE
    "Leakage" means giving the model information it would not have when making
    a real prediction. A leaky model looks brilliant in testing and fails in
    use. So:
      - score, attempts and completed_date are NOT features (they only exist
        AFTER the outcome);
      - prior_completed / prior_dropped / prereq_missing only count enrolments
        that happened BEFORE this one.
    One known limit: skill levels are a single snapshot (the latest
    assessment), not the level at enrolment time. With real LMS history, use
    the level recorded at the enrolment date.

WHICH ENROLMENTS ARE USED FOR TRAINING
    Only finished ones: Completed (label 1) and Dropped (label 0). Enrolled and
    In Progress have no outcome yet.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

NUMERIC_FEATURES = [
    "level_jump",
    "skills_too_advanced",
    "prereq_count",
    "prereq_missing",
    "duration_hours",
    "relevant_to_career",
    "prior_completed",
    "prior_dropped",
]
CATEGORICAL_FEATURES = ["difficulty", "delivery_mode", "seniority"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
LABEL = "completed"
ID_COLUMNS = ["enrollment_id", "employee_id", "course_id", "enrolled_date"]


class FeatureBuilder:
    """Builds feature rows from the typed LMS datasets (see loader.load_all)."""

    def __init__(self, datasets: dict[str, pd.DataFrame]) -> None:
        self.courses = datasets["courses.csv"].set_index("course_id")
        self.course_skills: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for r in datasets["course_skills.csv"].itertuples():
            self.course_skills[r.course_id].append((r.skill_id, int(r.level_from), int(r.level_to)))
        self.prereqs: dict[str, list[str]] = defaultdict(list)
        for r in datasets["course_prerequisites.csv"].itertuples():
            self.prereqs[r.course_id].append(r.prerequisite_course_id)
        self.levels: dict[str, dict[str, int]] = defaultdict(dict)
        for r in datasets["employee_skills.csv"].itertuples():
            self.levels[r.employee_id][r.skill_id] = int(r.current_level)

        roles = datasets["job_roles.csv"].set_index("role_id")
        role_skills: dict[str, set[str]] = defaultdict(set)
        for r in datasets["role_required_skills.csv"].itertuples():
            role_skills[r.role_id].add(r.skill_id)
        goals = dict(
            zip(
                datasets["career_goals.csv"]["employee_id"],
                datasets["career_goals.csv"]["target_role_id"],
                strict=True,
            )
        )
        self.career_skills: dict[str, set[str]] = {}
        self.seniority: dict[str, str] = {}
        for e in datasets["employees.csv"].itertuples():
            self.career_skills[e.employee_id] = role_skills[e.current_role_id] | role_skills.get(
                goals.get(e.employee_id), set()
            )
            self.seniority[e.employee_id] = roles.loc[e.current_role_id, "seniority"]

        self.history = datasets["training_history.csv"].sort_values(["employee_id", "enrolled_date"])

    # ------------------------------------------------------------------
    def _row(self, employee_id: str, course_id: str, earlier: pd.DataFrame) -> dict:
        """Features for one (employee, course) pair, given the enrolments that came before."""
        levels = self.levels.get(employee_id, {})
        skills = self.course_skills.get(course_id, [])
        jumps = [start - levels.get(sid, 0) for sid, start, _ in skills]
        jump = max(jumps, default=0)

        completed_before = set(earlier.loc[earlier["status"] == "Completed", "course_id"])
        missing = 0
        for pid in self.prereqs.get(course_id, []):
            covered = all(
                levels.get(sid, 0) >= end for sid, _, end in self.course_skills.get(pid, [])
            ) and bool(self.course_skills.get(pid))
            if pid not in completed_before and not covered:
                missing += 1

        course = self.courses.loc[course_id]
        return {
            "level_jump": jump,
            "skills_too_advanced": sum(1 for j in jumps if j >= 2),
            "prereq_count": len(self.prereqs.get(course_id, [])),
            "prereq_missing": missing,
            "duration_hours": int(course["duration_hours"]),
            "relevant_to_career": int(
                any(sid in self.career_skills.get(employee_id, set()) for sid, _, _ in skills)
            ),
            "prior_completed": int((earlier["status"] == "Completed").sum()),
            "prior_dropped": int((earlier["status"] == "Dropped").sum()),
            "difficulty": course["difficulty"],
            "delivery_mode": course["delivery_mode"],
            "seniority": self.seniority.get(employee_id, "Unknown"),
        }

    def training_table(self) -> pd.DataFrame:
        """One row per FINISHED enrolment: ID columns, the features, and the label."""
        rows = []
        for employee_id, enrolments in self.history.groupby("employee_id", sort=True):
            for e in enrolments.itertuples():
                if e.status not in ("Completed", "Dropped"):
                    continue
                earlier = enrolments[enrolments["enrolled_date"] < e.enrolled_date]  # only the past
                rows.append(
                    {
                        "enrollment_id": e.enrollment_id,
                        "employee_id": employee_id,
                        "course_id": e.course_id,
                        "enrolled_date": e.enrolled_date.date().isoformat(),
                        **self._row(employee_id, e.course_id, earlier),
                        LABEL: int(e.status == "Completed"),
                    }
                )
        return pd.DataFrame(rows, columns=ID_COLUMNS + FEATURES + [LABEL])

    def features_for(self, employee_id: str, course_ids: list[str]) -> pd.DataFrame:
        """Feature rows for courses the employee might take NOW (all past enrolments count)."""
        earlier = self.history[self.history["employee_id"] == employee_id]
        rows = [self._row(employee_id, cid, earlier) for cid in course_ids if cid in self.courses.index]
        return pd.DataFrame(rows, columns=FEATURES)
