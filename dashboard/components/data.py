"""
Data for the dashboard pages, as plain tables and numbers (Phase 15).

WHY A SEPARATE FILE WITHOUT STREAMLIT
    Every number on the dashboard comes from the same services as the API
    (app/services). This file only RESHAPES their results into DataFrames and
    small summaries for display. It never calculates a gap, a score or a path
    itself, so the dashboard can never disagree with Swagger.

    Keeping Streamlit out of this file means it can be unit-tested like any
    other Python code (tests/unit/test_dashboard_data.py). The page files stay
    thin: they arrange widgets and call these functions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from app.repositories.base import LmsRepository
from app.services.chat_service import ChatAnswer
from app.services.learning_path import LearningPath
from app.services.role_matching import RoleMatch, RoleMatchResult
from app.services.skill_analysis import BELOW, MET, MISSING, SkillAnalysisResult, SkillAnalysisService
from app.services.training_recommendation import RecommendationResult, TrainingRecommendationService

STATUS_LABEL = {MET: "Met", BELOW: "Below required", MISSING: "Missing"}


# --- Choices for the select boxes -----------------------------------------------------------------


def employee_choices(repo: LmsRepository) -> dict[str, str]:
    """{'E1001 – Arjun Mehta (Software Developer)': 'E1001', ...} sorted by ID."""
    choices = {}
    for employee_id in sorted(getattr(repo, "_employees", {})) or []:
        e = repo.get_employee(employee_id)
        role = repo.get_role(e.current_role_id)
        choices[f"{e.employee_id} – {e.full_name} ({role.title if role else e.current_role_id})"] = (
            e.employee_id
        )
    return choices


def role_choices(repo: LmsRepository) -> dict[str, str]:
    """{'Data Engineer (R004)': 'R004', ...} sorted by title."""
    return {f"{r.title} ({r.role_id})": r.role_id for r in sorted(repo.list_roles(), key=lambda r: r.title)}


# --- Home -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HomeStats:
    employees: int
    roles: int
    skills: int
    active_courses: int
    training_status: dict[str, int]  # Completed / In Progress / Enrolled / Dropped
    completion_rate: float  # completed / (completed + dropped), in %
    employees_with_goal: int
    average_gap_score: float  # toward the career goal, over employees with a goal
    role_ready: int  # employees with no gap for their goal
    top_gap_skills: pd.DataFrame  # skill, employees with a gap, of which mandatory
    top_recommended: pd.DataFrame  # course, title, times recommended first


def home_stats(repo: LmsRepository) -> HomeStats:
    employee_ids = sorted(getattr(repo, "_employees", {}))
    statuses = Counter(s for e in employee_ids for s in repo.get_training_status(e).values())
    finished = statuses["Completed"] + statuses["Dropped"]

    analysis, recommender = SkillAnalysisService(repo), TrainingRecommendationService(repo)
    gap_scores, gap_skills, mandatory_gaps, first_courses, ready = [], Counter(), Counter(), Counter(), 0
    courses = repo.get_courses()
    for employee_id in employee_ids:
        if repo.get_career_goal(employee_id) is None:
            continue
        result = analysis.analyze(employee_id)
        gap_scores.append(result.summary.gap_score)
        ready += result.role_ready
        for g in result.summary.gaps:
            gap_skills[g.skill_name] += 1
            mandatory_gaps[g.skill_name] += g.mandatory
        recs = recommender.recommend(employee_id, max_results=1).recommendations
        if recs:
            first_courses[recs[0].course.course_id] += 1

    top_gaps = pd.DataFrame(
        [(skill, n, mandatory_gaps[skill]) for skill, n in gap_skills.most_common(8)],
        columns=["Skill", "Employees with a gap", "Of which mandatory"],
    )
    top_courses = pd.DataFrame(
        [(cid, courses[cid].title, n) for cid, n in first_courses.most_common(8)],
        columns=["Course", "Title", "Times recommended first"],
    )
    return HomeStats(
        employees=len(employee_ids),
        roles=len(repo.list_roles()),
        skills=len(repo.get_skills()),
        active_courses=sum(c.is_active for c in courses.values()),
        training_status={k: statuses.get(k, 0) for k in ("Completed", "In Progress", "Enrolled", "Dropped")},
        completion_rate=round(100 * statuses["Completed"] / finished, 1) if finished else 0.0,
        employees_with_goal=len(gap_scores),
        average_gap_score=round(sum(gap_scores) / len(gap_scores), 1) if gap_scores else 0.0,
        role_ready=ready,
        top_gap_skills=top_gaps,
        top_recommended=top_courses,
    )


# --- Skills analysis ------------------------------------------------------------------------------


def skills_table(result: SkillAnalysisResult) -> pd.DataFrame:
    """One row per skill the target role requires, most urgent first (as API 1)."""
    return pd.DataFrame(
        [
            {
                "Skill": s.skill_name,
                "Category": s.category,
                "Current": s.current_level,
                "Required": s.required_level,
                "Gap": s.gap,
                "Mandatory": s.mandatory,
                "Status": STATUS_LABEL[s.status],
            }
            for s in result.summary.skills
        ],
        columns=["Skill", "Category", "Current", "Required", "Gap", "Mandatory", "Status"],
    )


def profile_table(result: SkillAnalysisResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Skill": p.skill_name, "Level": p.level, "Needed for target": p.required_for_target}
            for p in result.skill_profile
        ],
        columns=["Skill", "Level", "Needed for target"],
    )


def level_chart_data(result: SkillAnalysisResult) -> pd.DataFrame:
    """Current vs required level per skill, indexed by skill (for st.bar_chart)."""
    table = skills_table(result)
    return table.set_index("Skill")[["Current", "Required"]]


# --- Role matching --------------------------------------------------------------------------------


def role_matches_table(result: RoleMatchResult) -> pd.DataFrame:
    rows = []
    for m in result.matches:
        tags = [t for t, on in (("current role", m.is_current_role), ("career goal", m.is_career_goal)) if on]
        rows.append(
            {
                "Rank": m.rank,
                "Role": m.role.title,
                "Department": m.role.department,
                "Match %": m.match_percentage,
                "Readiness": m.readiness,
                "Mandatory gaps": m.mandatory_gaps,
                "Note": ", ".join(tags),
            }
        )
    return pd.DataFrame(
        rows, columns=["Rank", "Role", "Department", "Match %", "Readiness", "Mandatory gaps", "Note"]
    )


def role_skill_breakdown(match: RoleMatch) -> dict[str, list[str]]:
    """Matching, missing and to-improve skills of one role, as readable lines."""
    return {
        "Matching skills": [
            f"{s.skill_name} (level {s.current_level} of {s.required_level})" for s in match.skills_with(MET)
        ],
        "Missing skills": [
            f"{s.skill_name} (needs level {s.required_level})" for s in match.skills_with(MISSING)
        ],
        "Skills to improve": [
            f"{s.skill_name} ({s.current_level} → {s.required_level})" for s in match.skills_with(BELOW)
        ],
    }


# --- Recommendations ------------------------------------------------------------------------------


def recommendations_table(result: RecommendationResult) -> pd.DataFrame:
    rows = []
    for r in result.recommendations:
        rows.append(
            {
                "Rank": r.rank,
                "Course": r.course.course_id,
                "Title": r.course.title,
                "Skills": ", ".join(f"{c.skill_name} {c.level_from}→{c.level_to}" for c in r.contributions),
                "Difficulty": r.course.difficulty,
                "Hours": r.course.duration_hours,
                "Prerequisites": ", ".join(
                    f"{p.course_id} {'✓' if p.satisfied else '✗'}" for p in r.prerequisites
                )
                or "none",
                "Score": r.score,
                "Mandatory gap": r.addresses_mandatory_gap,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Rank",
            "Course",
            "Title",
            "Skills",
            "Difficulty",
            "Hours",
            "Prerequisites",
            "Score",
            "Mandatory gap",
        ],
    )


# --- Learning path --------------------------------------------------------------------------------


def path_table(path: LearningPath) -> pd.DataFrame:
    rows = [
        {
            "Step": s.step,
            "Course": s.course.course_id,
            "Title": s.course.title,
            "Raises": ", ".join(f"{r.skill_name} {r.level_from}→{r.level_to}" for r in s.raises),
            "Hours": s.course.duration_hours,
            "Status": s.status,
            "Why": "prerequisite"
            if s.purpose == "prerequisite"
            else ("mandatory gap" if s.mandatory else "optional gap"),
            "After step": ", ".join(map(str, s.after_steps)) or "–",
            "Can start now": s.ready_now,
        }
        for s in path.steps
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Step",
            "Course",
            "Title",
            "Raises",
            "Hours",
            "Status",
            "Why",
            "After step",
            "Can start now",
        ],
    )


def course_progress(path: LearningPath) -> tuple[int, int, float]:
    """(done, total, % done): completed courses that count for the target, plus the path's courses."""
    done = len(path.progress.completed_courses)
    total = done + len(path.steps)
    return done, total, round(100 * done / total, 1) if total else 100.0


# --- Assistant ------------------------------------------------------------------------------------


def sources_table(answer: ChatAnswer) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Source": s.label,
                "Document": s.source,
                "Section": s.section,
                "Page": s.page if s.page else "",
                "Score": round(s.score, 3),
            }
            for s in answer.sources
        ],
        columns=["Source", "Document", "Section", "Page", "Score"],
    )


# --- Documents and models -------------------------------------------------------------------------


def documents_table(manifest: dict | None) -> pd.DataFrame:
    columns = ["Document", "Title", "Origin", "Pages", "Chunks", "Fingerprint"]
    if not manifest:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        [
            {
                "Document": d["source"],
                "Title": d["title"],
                "Origin": d.get("origin", "base"),
                "Pages": d["pages"],
                "Chunks": d["chunks"],
                "Fingerprint": d["sha256"][:12],
            }
            for d in manifest["documents"]
        ],
        columns=columns,
    )


def model_versions_table(cards: list[dict], current: int | None) -> pd.DataFrame:
    rows = []
    for card in reversed(cards):  # newest first
        metrics = card.get("test_metrics", {})
        rows.append(
            {
                "Version": card["version"],
                "Current": card["version"] == current,
                "Algorithm": card.get("algorithm", ""),
                "Trained at": card.get("trained_at", ""),
                "Test ROC AUC": metrics.get("roc_auc"),
                "Accuracy": metrics.get("accuracy"),
                "Baseline accuracy": metrics.get("baseline_accuracy"),
                "Synthetic data": card.get("synthetic_data", True),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Version",
            "Current",
            "Algorithm",
            "Trained at",
            "Test ROC AUC",
            "Accuracy",
            "Baseline accuracy",
            "Synthetic data",
        ],
    )


def model_comparison_table(card: dict) -> pd.DataFrame:
    """The cross-validation comparison saved with a model version (best first)."""
    rows = card.get("cross_validation", [])
    table = pd.DataFrame(rows)
    return table.rename(
        columns={
            "model": "Algorithm",
            "cv_roc_auc": "CV ROC AUC",
            "cv_roc_auc_std": "± std",
            "cv_accuracy": "CV accuracy",
            "cv_f1": "CV F1",
        }
    )
