"""Model management: versions, metrics, comparison, rollback and controlled retraining (Phase 15-16)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_completion_predictor, get_retraining_service  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.ml.evaluate import feature_importance  # noqa: E402
from app.ml.model_registry import current_version, list_cards, load_current, set_current  # noqa: E402
from app.ml.retraining import PROMOTED, read_history  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "ML model management",
    "The course-completion model used by recommendations (API 3): versions, test metrics, the algorithm "
    "comparison, rollback and controlled retraining. Trained on SYNTHETIC data: it shows the method, "
    "not real accuracy.",
    "🤖",
)
ui.admin_notice()
settings = get_settings()
cards = list_cards(settings.model_dir)
current = current_version(settings.model_dir)


def retrain_button(label: str) -> None:
    """The same controlled workflow as API 6: validate, train, evaluate, compare, quality gate, promote."""
    reason = st.text_input("Reason (kept in the history)", key=f"reason_{label}")
    if st.button(label, type="primary"):
        with st.spinner(
            "Validating data, comparing algorithms, training, evaluating, applying the quality gate ..."
        ):
            report = ui.safe(get_retraining_service().retrain, "dashboard admin", reason)
        if report is None:
            return
        if report.status == PROMOTED:
            get_completion_predictor.cache_clear()
            st.success(f"Version {report.new_version} passed the quality gate and is now current.")
        else:
            st.warning(
                f"Result: {report.status.replace('_', ' ')}. Current version: {report.current_version}."
            )
        gate = [{"Check": c.name, "Passed": c.passed, "Detail": c.detail} for c in report.gate]
        st.dataframe(gate, hide_index=True)
        for note in report.notes:
            st.caption(f"ⓘ {note}")
        st.caption(
            "The API (a separate process) loads a new current model after a restart, or at once via API 6."
        )


if not cards:
    st.info("No model has been trained yet. Recommendations work without one (the score uses three parts).")
    retrain_button("Train the first model")
    st.stop()

card = next((c for c in cards if c["version"] == current), cards[-1])
metrics = card["test_metrics"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current version", current)
c2.metric("Algorithm", card["algorithm"].replace("_", " "))
c3.metric(
    "Test ROC AUC", metrics["roc_auc"], f"{metrics['roc_auc'] - 0.5:+.3f} vs chance", help="0.5 = coin flip"
)
c4.metric(
    "Accuracy", metrics["accuracy"], f"{metrics['accuracy'] - metrics['baseline_accuracy']:+.3f} vs baseline"
)
in_use = "in use by the API" if settings.use_completion_model else "switched off (USE_COMPLETION_MODEL=false)"
st.caption(f"Trained {card['trained_at']} · status: {in_use}")

left, right = st.columns(2)
with left:
    st.subheader("Model comparison")
    st.caption("5-fold cross-validation on the training rows; the best ROC AUC wins.")
    st.dataframe(data.model_comparison_table(card), hide_index=True)
with right:
    st.subheader("What the model relies on")
    loaded = load_current(settings.model_dir)
    if loaded:
        importance = feature_importance(loaded[0]).head(10)
        st.bar_chart(importance.set_index(importance.columns[0]), horizontal=True)

st.subheader("Model versions")
st.dataframe(data.model_versions_table(cards, current), hide_index=True)
runs = read_history(settings.model_dir)
if runs:
    st.subheader("Retraining runs")
    st.dataframe(runs, hide_index=True)

st.subheader("Controls")
a, b = st.columns(2)
with a:
    versions = [c["version"] for c in reversed(cards)]
    chosen = st.selectbox(
        "Use version", versions, index=versions.index(current) if current in versions else 0
    )
    if st.button("Switch version (rollback)") and chosen != current:
        set_current(chosen, settings.model_dir)
        get_completion_predictor.cache_clear()
        st.success(f"Version {chosen} is now current. Restart the API so it uses it.")
with b:
    st.caption(
        f"Retraining saves a NEW version; nothing is overwritten. Quality gate: ROC AUC ≥ "
        f"{settings.ml_min_roc_auc}, no drop of more than {settings.ml_max_regression} vs the current model."
    )
    retrain_button("Retrain now")
