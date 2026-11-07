"""
Training the course-completion model (Phase 8).

PURPOSE
    Learn from past enrolments to predict the probability that a learner
    completes a course. Three standard algorithms are compared fairly, the
    best is trained, checked on data it has never seen, and saved.

THE THREE CANDIDATES (all from scikit-learn)
    logistic_regression  a weighted sum of the features, squeezed into 0-1.
                         Simple, fast, and each weight is readable.
    decision_tree        a flowchart of yes/no questions ("level_jump >= 2?").
                         Easy to explain, but one tree overfits easily, so we
                         limit its depth.
    random_forest        200 small trees voting together. Usually more
                         accurate than one tree, less easy to read.

WHY A PIPELINE
    A Pipeline glues preparation and model together:
        StandardScaler   puts numbers on the same scale (needed by logistic regression)
        OneHotEncoder    turns a category like "Advanced" into 0/1 columns
        the model
    The exact same steps then run at training AND at prediction time, so they
    can never get out of step - a common source of bugs.

HOW THE BEST MODEL IS CHOSEN
    5-fold cross-validation on the TRAINING data only: the training rows are
    split into 5 parts, each model is trained on 4 and scored on the 5th, five
    times. The model with the highest average ROC AUC wins. The TEST data is
    kept aside until the very end (evaluate.py), so the final score is honest.

ROC AUC IN ONE SENTENCE
    The chance that the model gives a randomly chosen completed enrolment a
    higher probability than a randomly chosen dropped one: 0.5 = coin flip,
    1.0 = perfect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from app.data_processing.loader import load_all, resolve_folder
from app.ml.evaluate import evaluate
from app.ml.features import CATEGORICAL_FEATURES, FEATURES, LABEL, NUMERIC_FEATURES, FeatureBuilder
from app.ml.model_registry import save_model

SEED = 42  # fixed, so every run on every machine gives the same split and models


def candidate_models(seed: int = SEED) -> dict:
    return {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "decision_tree": DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, random_state=seed),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=seed
        ),
    }


def build_pipeline(estimator) -> Pipeline:
    prepare = ColumnTransformer(
        [
            ("numbers", StandardScaler(), NUMERIC_FEATURES),
            ("categories", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline([("prepare", prepare), ("model", estimator)])


def split_data(
    table: pd.DataFrame, test_size: float = 0.2, seed: int = SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified split: train and test keep the same share of completed enrolments."""
    return train_test_split(table, test_size=test_size, random_state=seed, stratify=table[LABEL])


def compare_models(train: pd.DataFrame, folds: int = 5, seed: int = SEED) -> pd.DataFrame:
    """Cross-validate every candidate on the training data. Best (highest ROC AUC) first."""
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    rows = []
    for name, estimator in candidate_models(seed).items():
        scores = cross_validate(
            build_pipeline(estimator),
            train[FEATURES],
            train[LABEL],
            cv=cv,
            scoring=["roc_auc", "accuracy", "f1"],
        )
        rows.append(
            {
                "model": name,
                "cv_roc_auc": round(scores["test_roc_auc"].mean(), 3),
                "cv_roc_auc_std": round(scores["test_roc_auc"].std(), 3),
                "cv_accuracy": round(scores["test_accuracy"].mean(), 3),
                "cv_f1": round(scores["test_f1"].mean(), 3),
            }
        )
    return pd.DataFrame(rows).sort_values("cv_roc_auc", ascending=False, ignore_index=True)


def fit_model(name: str, train: pd.DataFrame, seed: int = SEED) -> Pipeline:
    """Train one candidate on all training rows."""
    pipeline = build_pipeline(candidate_models(seed)[name])
    return pipeline.fit(train[FEATURES], train[LABEL])


@dataclass
class TrainingReport:
    comparison: pd.DataFrame
    best_model: str
    test_metrics: dict
    model_path: Path
    version: int
    rows: int


def run_training(
    data_dir: str | Path | None = None, models_dir: str | Path = "models", seed: int = SEED
) -> TrainingReport:
    """The whole workflow in one call: features -> split -> compare -> fit -> evaluate -> save.

    The scripts 09-13 show each step separately; this function is what an
    automated retraining job (Phase 16) calls.
    """
    table = FeatureBuilder(load_all(data_dir)).training_table()
    train, test = split_data(table, seed=seed)
    comparison = compare_models(train, seed=seed)
    best = comparison.loc[0, "model"]
    pipeline = fit_model(best, train, seed=seed)
    metrics = evaluate(pipeline, test)
    metadata = {
        "algorithm": best,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_dir": str(resolve_folder(data_dir)),
        "synthetic_data": True,
        "rows": {"total": len(table), "train": len(train), "test": len(test)},
        "features": FEATURES,
        "cross_validation": comparison.to_dict(orient="records"),
        "test_metrics": metrics,
        "seed": seed,
    }
    path, version = save_model(pipeline, metadata, models_dir)
    return TrainingReport(comparison, best, metrics, path, version, len(table))
