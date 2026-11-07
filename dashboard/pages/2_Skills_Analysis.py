"""Skills analysis: one employee's gaps for a target role (API 1)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_skill_analysis_service  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "Skills analysis", "Current skills, the target role's requirements, and the gaps between them.", "🧭"
)
repo = ui.repository()
employee_id = ui.employee_picker(repo)
goal = repo.get_career_goal(employee_id)
target = ui.role_picker(repo, "Target role", goal or repo.get_employee(employee_id).current_role_id)
if goal:
    st.caption(f"Career goal: {repo.get_role(goal).title}")

result = ui.safe(get_skill_analysis_service(repo).analyze, employee_id, target)
if result is None:
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Match", f"{result.summary.match_percentage:g} %")
c2.metric("Gap score", result.summary.gap_score, help="0 = role-ready, 100 = none of the required skills")
c3.metric("Mandatory gaps", result.mandatory_gaps)
c4.metric("Role-ready", "Yes" if result.role_ready else "No")
st.info(result.explanation)

left, right = st.columns([3, 2])
with left:
    st.subheader(f"Requirements of {result.target_role.title}")
    st.dataframe(data.skills_table(result), hide_index=True)
    st.bar_chart(data.level_chart_data(result), stack=False, y_label="Level (1-5)")
with right:
    st.subheader(f"Current skills of {result.employee_name}")
    st.dataframe(
        data.profile_table(result),
        hide_index=True,
        column_config={
            "Level": st.column_config.ProgressColumn("Level", min_value=0, max_value=5, format="%d")
        },
    )
    if result.suggestions:
        st.subheader("Suggestions")
        for suggestion in result.suggestions:
            st.markdown(f"- {suggestion}")
