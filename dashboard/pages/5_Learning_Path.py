"""Personalised learning path: the courses in order, progress and the next step (API 4)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import (  # noqa: E402
    get_explanation_service,
    get_learning_path_service,
    get_llm_provider,
)
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "Learning path", "The courses that close every gap, in an order you can follow, and what to do next.", "🗺️"
)
repo = ui.repository()
employee_id = ui.employee_picker(repo)
goal = repo.get_career_goal(employee_id)
left, right = st.columns([3, 1])
target = ui.role_picker(
    repo, "Target role", goal or repo.get_employee(employee_id).current_role_id, where=left
)
include_optional = right.toggle("Include optional skills", value=True)

path = ui.safe(get_learning_path_service(repo).build, employee_id, target, include_optional)
if path is None:
    st.stop()

done, total, percent = data.course_progress(path)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Match now", f"{path.progress.match_percentage:g} %")
c2.metric("Match after the path", f"{path.progress.projected_match_percentage:g} %")
c3.metric("Steps", path.progress.total_steps)
c4.metric("Hours", path.progress.total_hours)
st.progress(
    percent / 100, text=f"Course progress: {done} of {total} relevant courses completed ({percent:g} %)"
)
st.success(f"**Next:** {path.next_action}", icon="➡️")

if path.steps:
    st.dataframe(
        data.path_table(path),
        hide_index=True,
        column_config={"Can start now": st.column_config.CheckboxColumn("Can start now")},
    )
    with st.expander("Why each step"):
        for s in path.steps:
            st.markdown(f"**{s.step}. {s.course.course_id} – {s.course.title}**  \n{s.reason}")
if path.progress.completed_courses:
    st.caption("Completed: " + ", ".join(f"{c.course_id} {c.title}" for c in path.progress.completed_courses))
for note in path.notes:
    st.caption(f"ⓘ {note}")

st.divider()
if st.button("Explain this path in plain language", icon="💬"):
    with st.spinner("Asking the language model (the first answer can take up to a minute) ..."):
        explanation = ui.safe(get_explanation_service(get_llm_provider()).explain_path, path)
    if explanation:
        st.markdown(explanation.text)
        st.caption(
            f"Written by: {explanation.provider} {explanation.model} · {explanation.duration_ms / 1000:.1f} s"
        )
        for warning in explanation.grounding_warnings:
            st.warning(warning)
