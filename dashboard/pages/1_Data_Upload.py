"""Data upload: check an LMS CSV file before it is used (Phase 15, logic from Phase 4)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.data_processing.schemas import SCHEMAS  # noqa: E402
from app.data_processing.validators import issues_table  # noqa: E402
from app.services.data_upload_service import UploadError, save_upload, validate_upload  # noqa: E402
from dashboard.components import ui  # noqa: E402

ui.setup_page(
    "Data upload",
    "Check one of the 11 LMS CSV files: is it readable, which dataset is it, and is every value valid - "
    "including references to the other files? Valid files can be saved to data/uploads.",
    icon="📤",
)
ui.admin_page()  # Phase 17: changing LMS data is for administrators

uploaded = st.file_uploader("CSV file", type=["csv"], help="For example a new employee_skills.csv")
dataset = st.selectbox("Dataset", ["Detect automatically", *SCHEMAS])

if uploaded is not None:
    content = uploaded.getvalue()
    try:
        result = validate_upload(
            content, uploaded.name, None if dataset == "Detect automatically" else dataset
        )
    except UploadError as error:
        st.error(str(error))
        st.stop()

    status = {"valid": "✅ Valid", "valid_with_warnings": "⚠️ Valid with warnings", "invalid": "❌ Invalid"}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", status[result.status])
    c2.metric("Dataset", result.dataset, help=f"Detected by {result.detected_by}")
    c3.metric("Rows", result.rows)
    c4.metric("Errors / warnings", f"{len(result.errors)} / {len(result.warnings)}")

    st.subheader("Preview")
    st.dataframe(result.preview)
    if result.issues:
        st.subheader("Issues")
        st.dataframe(issues_table(result.issues), hide_index=True)
    if result.status != "invalid" and st.button("Save to data/uploads", type="primary"):
        path = save_upload(content, result)
        st.success(f"Saved: {path}")
else:
    st.info(
        "Choose a CSV file to check it. Try a file from data/sample, or the broken copies in data/raw/dirty."
    )
