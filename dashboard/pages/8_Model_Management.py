"""Model management: versions, metrics, comparison, rollback and retraining of the completion model."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_completion_predictor  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.ml.evaluate import feature_importance  # noqa: E402
from app.ml.model_registry import current_version, list_cards, load_current, set_current  # noqa: E402
from app.ml.train import run_training  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "ML model management",
    "The course-completion model used by recommendations (API 3): versions, test metrics, the algorithm "
    "comparison, rollback and retraining. Trained on SYNTHETIC data: it shows the method, not real accuracy.",
    "🤖",
)
ui.admin_notice()
settings = get_settings()
cards = list_cards(settings.model_dir)
current = current_version(settings.model_dir)


def retrain_button(label: str) -> None:
    if st.button(label, type="primary"):
        with st.spinner("Building features, comparing three algorithms, training and evaluating ..."):
            report = run_training(settings.data_dir, settings.model_dir)
        get_completion_predictor.cache_clear()
        st.success(
            f"Saved version {report.version}: {report.best_model}, "
            f"test ROC AUC {report.test_metrics['roc_auc']}. Restart the API (uvicorn) so it uses it."
        )


if not cards:
    st.info("No model has been trained yet. Recommendations work without one (the score uses three parts).")
    retrain_button("Train the first model")
    st.stop()

card = next(c for c in cards if c["version"] == current)
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

st.subheader("Training history")
st.dataframe(data.model_versions_table(cards, current), hide_index=True)

st.subheader("Controls")
a, b = st.columns(2)
with a:
    versions = [c["version"] for c in reversed(cards)]
    chosen = st.selectbox("Use version", versions, index=versions.index(current))
    if st.button("Switch version (rollback)") and chosen != current:
        set_current(chosen, settings.model_dir)
        get_completion_predictor.cache_clear()
        st.success(f"Version {chosen} is now current. Restart the API so it uses it.")
with b:
    st.caption(
        "Retraining builds a NEW version; nothing is overwritten. Phase 16 adds API 6 and MLflow tracking."
    )
    retrain_button("Retrain now")
