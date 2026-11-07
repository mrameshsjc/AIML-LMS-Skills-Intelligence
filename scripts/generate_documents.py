"""
Generate knowledge documents from the LMS data (Phase 12).

PURPOSE
    The AI assistant answers from documents. Two of them describe the LMS
    data itself, so they are GENERATED from the CSV files instead of written
    by hand: they can never disagree with the data the APIs use.

        documents/course_catalogue.md     every active course: level, hours, skills, prerequisites
        documents/job_role_profiles.md    every job role: department, seniority, required skills

    Re-run after changing data/sample. The hand-written documents (policy,
    FAQ, guides) are not touched.

HOW TO RUN (from the project folder)
    PS> python scripts/generate_documents.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.csv_repository import CsvLmsRepository  # noqa: E402

DELIVERY = {"Online": "online", "Blended": "as blended learning", "Classroom": "in a classroom"}
HEADER = (
    "*Generated from the LMS data by scripts/generate_documents.py. Synthetic data for demonstration only.*"
)


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def course_catalogue(repo: CsvLmsRepository) -> str:
    skills = repo.get_skills()
    courses = repo.get_courses()
    lines = ["# Course Catalogue", "", HEADER, ""]
    lines.append(
        "Each course raises one or more skills from an entry level to a target level on the 1-5 proficiency "
        "scale. Complete the prerequisites first, unless your skill level already covers them."
    )
    for course in sorted(courses.values(), key=lambda c: c.course_id):
        if not course.is_active:
            continue
        raises = "; ".join(
            f"{skills[cs.skill_id].name} from level {cs.level_from} to level {cs.level_to}"
            for cs in repo.get_course_skills(course.course_id)
        )
        prereqs = repo.get_prerequisites(course.course_id)
        prereq_text = ", ".join(f"{p} ({courses[p].title})" for p in prereqs) if prereqs else "none"
        lines += [
            "",
            f"## {course.course_id} – {course.title}",
            "",
            f"{course.title} ({course.course_id}) is {_article(course.difficulty)} "
            f"{course.difficulty.lower()} course of {course.duration_hours} hours, "
            f"delivered {DELIVERY.get(course.delivery_mode, course.delivery_mode)} by {course.provider}.",
            f"It raises {raises}.",
            f"Prerequisites: {prereq_text}.",
        ]
    return "\n".join(lines) + "\n"


def job_role_profiles(repo: CsvLmsRepository) -> str:
    skills = repo.get_skills()
    lines = ["# Job Role Profiles", "", HEADER, ""]
    lines.append(
        "Each role lists the skills it requires and the minimum level on the 1-5 proficiency scale. "
        "Mandatory skills must be met; optional skills improve the match."
    )
    for role in repo.list_roles():
        reqs = repo.get_role_requirements(role.role_id)
        mandatory = [f"{skills[r.skill_id].name} level {r.required_level}" for r in reqs if r.mandatory]
        optional = [f"{skills[r.skill_id].name} level {r.required_level}" for r in reqs if not r.mandatory]
        lines += [
            "",
            f"## {role.title} ({role.role_id})",
            "",
            f"The {role.title} role is a {role.seniority.lower()}-level role in the {role.department} "
            f"department ({role.job_family} job family).",
            f"Mandatory skills for {role.title}: {', '.join(mandatory) or 'none'}.",
            f"Optional skills for {role.title}: {', '.join(optional) or 'none'}.",
        ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    repo = CsvLmsRepository(ROOT / "data" / "sample")
    out = ROOT / "documents"
    for name, text in [
        ("course_catalogue.md", course_catalogue(repo)),
        ("job_role_profiles.md", job_role_profiles(repo)),
    ]:
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote documents/{name} ({len(text.splitlines())} lines)")
