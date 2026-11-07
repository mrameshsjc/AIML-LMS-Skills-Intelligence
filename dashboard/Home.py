"""
Home page of the Streamlit dashboard (Phase 15).

HOW TO RUN (from the project folder)
    PS> streamlit run dashboard/Home.py
    then open http://localhost:8501 (Streamlit opens it for you)

Streamlit runs this file top to bottom on every click; the pages in pages/
appear in the sidebar automatically (sorted by their number).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # the project folder, so "import app" works
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "LMS Skills Intelligence",
    "Skills gaps, job-role matching, explainable training recommendations, learning paths and an AI "
    "assistant for an enterprise LMS. All data is synthetic.",
)


@st.cache_data(ttl=300, show_spinner="Calculating the summary ...")
def load_stats(_repo) -> data.HomeStats:  # the leading _ tells Streamlit not to hash the repository
    return data.home_stats(_repo)


stats = load_stats(ui.repository())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Employees", stats.employees)
c2.metric("Job roles", stats.roles)
c3.metric("Skills", stats.skills)
c4.metric("Active courses", stats.active_courses)

st.divider()
left, right = st.columns(2)
with left:
    st.subheader("Training completion")
    st.metric(
        "Completion rate", f"{stats.completion_rate:g} %", help="Completed ÷ (completed + dropped) enrolments"
    )
    status = pd.DataFrame({"Enrolments": stats.training_status}).rename_axis("Status")
    st.bar_chart(status, horizontal=True)
with right:
    st.subheader("Skill gaps toward career goals")
    g1, g2, g3 = st.columns(3)
    g1.metric("Employees with a goal", stats.employees_with_goal)
    g2.metric(
        "Average gap score", stats.average_gap_score, help="0 = role-ready, 100 = no required skill yet"
    )
    g3.metric("Role-ready", stats.role_ready)
    st.dataframe(stats.top_gap_skills, hide_index=True)

st.subheader("Recommendation statistics")
st.caption("The course recommended first (API 3) for each employee with a career goal.")
st.dataframe(stats.top_recommended, hide_index=True)

st.divider()
st.subheader("Explore")
links = [
    ("pages/2_Skills_Analysis.py", "Skills analysis", "🧭"),
    ("pages/3_Role_Matching.py", "Role matching", "🎯"),
    ("pages/4_Recommendations.py", "Recommendations", "📚"),
    ("pages/5_Learning_Path.py", "Learning path", "🗺️"),
    ("pages/6_AI_Assistant.py", "AI assistant", "💬"),
]
for column, (page, label, icon) in zip(st.columns(len(links)), links, strict=True):
    column.page_link(page, label=label, icon=icon)
