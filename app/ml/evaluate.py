"""
Evaluating the completion model on data it has never seen (Phase 8).

THE METRICS, IN PLAIN WORDS (the model says "completes" when probability >= 0.5)
    accuracy    share of predictions that are right
    precision   of the enrolments predicted to complete, how many really did
    recall      of the enrolments that really completed, how many were found
    f1          one number balancing precision and recall
    roc_auc     how well the probabilities RANK completers above droppers
                (0.5 = coin flip, 1.0 = perfect). This is what the recommender
                uses, so it is our main metric.

ALWAYS COMPARE WITH A BASELINE
    About two thirds of enrolments are completed, so a "model" that always
    says "completes" is already about 67 % accurate. A model is only useful if
    it beats that - especially on ROC AUC, where the baseline is 0.5.

CONFUSION MATRIX
                     predicted dropped   predicted completed
    really dropped        true neg.          false pos.
    really completed      false neg.         true pos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from app.ml.features import FEATURES, LABEL


def evaluate(pipeline: Pipeline, test: pd.DataFrame) -> dict:
    """Metrics on the test rows, next to the always-'completes' baseline."""
    y_true = test[LABEL].to_numpy()
    proba = pipeline.predict_proba(test[FEATURES])[:, 1]
    y_pred = (proba >= 0.5).astype(int)
    majority = int(round(y_true.mean()))
    baseline = np.full_like(y_true, majority)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "test_rows": int(len(y_true)),
        "accuracy": round(accuracy_score(y_true, y_pred), 3),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 3),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 3),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 3),
        "roc_auc": round(roc_auc_score(y_true, proba), 3),
        "baseline_accuracy": round(accuracy_score(y_true, baseline), 3),
        "baseline_roc_auc": 0.5,
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


def feature_importance(pipeline: Pipeline) -> pd.DataFrame:
    """Which prepared features matter most.

    Logistic regression: the coefficient (positive = more likely to complete).
    Trees / forests: impurity-based importance (always positive; no direction).
    """
    names = pipeline.named_steps["prepare"].get_feature_names_out()
    names = [n.split("__", 1)[1] for n in names]  # "numbers__level_jump" -> "level_jump"
    model = pipeline.named_steps["model"]
    if hasattr(model, "coef_"):
        values, kind = model.coef_[0], "coefficient"
    else:
        values, kind = model.feature_importances_, "importance"
    table = pd.DataFrame({"feature": names, kind: np.round(values, 3)})
    return table.reindex(table[kind].abs().sort_values(ascending=False).index).reset_index(drop=True)
