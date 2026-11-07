"""Role matching: every job role ranked by how well the employee matches it (API 2)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_role_matching_service  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "Role matching", "All job roles ranked by match percentage, with matching and missing skills.", "🎯"
)
repo = ui.repository()
employee_id = ui.employee_picker(repo)
result = ui.safe(get_role_matching_service(repo).match, employee_id, top_n=20)
if result is None:
    st.stop()

st.info(result.summary)
st.dataframe(
    data.role_matches_table(result),
    hide_index=True,
    column_config={
        "Match %": st.column_config.ProgressColumn("Match %", min_value=0, max_value=100, format="%.1f %%")
    },
)

st.subheader("Skills for one role")
titles = [m.role.title for m in result.matches]
default = result.target.role.title if result.target else titles[0]
chosen = st.selectbox("Role", titles, index=titles.index(default))
match = next(m for m in result.matches if m.role.title == chosen)
st.caption(match.explanation)
for column, (heading, items) in zip(st.columns(3), data.role_skill_breakdown(match).items(), strict=True):
    with column:
        st.markdown(f"**{heading}**")
        for item in items or ["–"]:
            st.markdown(f"- {item}")

if result.related_roles:
    st.subheader(f"Roles similar to {result.related_to.title}")
    st.caption(
        "Similarity of the roles' required skills (TF-IDF + cosine similarity), and your match for each."
    )
    st.dataframe(
        [
            {
                "Role": r.similar.role.title,
                "Similarity": r.similar.similarity,
                "Your match %": r.employee_match,
                "Shared skills": ", ".join(r.shared_skill_names),
            }
            for r in result.related_roles
        ],
        hide_index=True,
    )
