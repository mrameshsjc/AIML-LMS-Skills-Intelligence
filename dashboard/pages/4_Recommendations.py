"""Training recommendations: courses for the gaps, each with its score and reason (API 3)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_training_recommendation_service  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "Training recommendations",
    "Courses that close the gaps, ranked by a score with four visible parts, and the reason for each.",
    "📚",
)
repo = ui.repository()
employee_id = ui.employee_picker(repo)
goal = repo.get_career_goal(employee_id)
target = ui.role_picker(repo, "Target role", goal or repo.get_employee(employee_id).current_role_id)
max_results = st.slider("Number of courses", 1, 20, 5)

result = ui.safe(
    get_training_recommendation_service(repo).recommend, employee_id, target, max_results=max_results
)
if result is None:
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Match now", f"{result.match_percentage:g} %")
c2.metric("Skill gaps", len(result.gaps))
c3.metric("Courses found", len(result.recommendations))
for note in result.notes:
    st.caption(f"ⓘ {note}")

st.dataframe(
    data.recommendations_table(result),
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="%.2f")
    },
)

st.subheader("Why each course")
for r in result.recommendations:
    with st.expander(f"{r.rank}. {r.course.course_id} – {r.course.title}  ·  score {r.score:.2f}"):
        st.write(r.reason)
        parts = {k.replace("_", " "): v for k, v in r.components.items()}
        st.dataframe([parts], hide_index=True)
        st.caption(
            f"{r.course.difficulty} · {r.course.duration_hours} hours · {r.course.delivery_mode} · "
            f"{r.course.provider}"
            + (f" · you are {r.enrollment_status.lower()}" if r.enrollment_status else "")
        )
if result.uncovered_skills:
    st.warning("No available course closes: " + ", ".join(result.uncovered_skills))
