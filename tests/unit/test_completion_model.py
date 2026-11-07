"""
Tests for the course-completion model (Phase 8). No web server needed.

The model is trained ONCE per test run into a temporary folder (about 4 s),
so these tests never touch your real models/ folder.

HOW TO RUN
    PS> pytest tests/unit/test_completion_model.py -v
"""

import json

import pandas as pd
import pytest

from app.data_processing.loader import load_all
from app.ml.evaluate import evaluate, feature_importance
from app.ml.features import FEATURES, ID_COLUMNS, LABEL, FeatureBuilder
from app.ml.model_registry import MODEL_NAME, list_versions, load_current, save_model, set_current
from app.ml.predict import CompletionPredictor
from app.ml.train import run_training, split_data
from app.repositories.csv_repository import CsvLmsRepository
from app.services.training_recommendation import TrainingRecommendationService


@pytest.fixture(scope="module")
def datasets():
    return load_all()


@pytest.fixture(scope="module")
def builder(datasets) -> FeatureBuilder:
    return FeatureBuilder(datasets)


@pytest.fixture(scope="module")
def table(builder) -> pd.DataFrame:
    return builder.training_table()


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    models_dir = tmp_path_factory.mktemp("models")
    return run_training(models_dir=models_dir), models_dir


# --- Features ----------------------------------------------------------------------


def test_training_table_has_one_row_per_finished_enrolment(table, datasets):
    history = datasets["training_history.csv"]
    finished = history[history["status"].isin(["Completed", "Dropped"])]
    assert len(table) == len(finished)
    assert list(table.columns) == ID_COLUMNS + FEATURES + [LABEL]
    assert table[FEATURES].notna().all().all()


def test_label_is_completed_one_dropped_zero(table, datasets):
    status = datasets["training_history.csv"].set_index("enrollment_id")["status"]
    expected = (status.loc[table["enrollment_id"]] == "Completed").astype(int).to_numpy()
    assert (table[LABEL].to_numpy() == expected).all()


def test_no_leakage_columns_are_features():
    for leaky in ["score", "attempts", "completed_date", "status"]:
        assert leaky not in FEATURES


def test_history_counts_only_earlier_enrolments(table, datasets):
    history = datasets["training_history.csv"]
    for row in table.sample(25, random_state=1).itertuples():
        mine = history[history["employee_id"] == row.employee_id]
        earlier = mine[mine["enrolled_date"] < pd.Timestamp(row.enrolled_date)]
        assert row.prior_completed == (earlier["status"] == "Completed").sum()
        assert row.prior_dropped == (earlier["status"] == "Dropped").sum()


def test_first_enrolment_has_no_history(table):
    first = table.sort_values("enrolled_date").groupby("employee_id").head(1)
    assert (first["prior_completed"] == 0).all() and (first["prior_dropped"] == 0).all()


def test_skills_too_advanced_counts_jumps_of_two_or_more(builder):
    row = builder.features_for("E1001", ["C-MLOPS-201", "C-SQL-201"])
    assert row.loc[0, "skills_too_advanced"] >= 1 and row.loc[0, "level_jump"] >= 2
    assert row.loc[1, "skills_too_advanced"] == 0


def test_features_for_skips_unknown_courses(builder):
    assert len(builder.features_for("E1001", ["C-SQL-201", "NOT-A-COURSE"])) == 1


# --- Split and training ---------------------------------------------------------------


def test_split_is_stratified_and_disjoint(table):
    train, test = split_data(table)
    assert len(train) + len(test) == len(table)
    assert len(test) == pytest.approx(0.2 * len(table), abs=1)
    assert not set(train["enrollment_id"]) & set(test["enrollment_id"])
    assert train[LABEL].mean() == pytest.approx(test[LABEL].mean(), abs=0.02)


def test_split_is_reproducible(table):
    first, _ = split_data(table)
    again, _ = split_data(table)
    assert list(first["enrollment_id"]) == list(again["enrollment_id"])


def test_model_beats_the_baseline(trained):
    report, _ = trained
    assert report.best_model in {"logistic_regression", "decision_tree", "random_forest"}
    assert report.test_metrics["roc_auc"] > 0.6 > report.test_metrics["baseline_roc_auc"]
    assert set(report.comparison["model"]) == {"logistic_regression", "decision_tree", "random_forest"}


def test_evaluate_and_importance_shapes(trained, table):
    _, models_dir = trained
    pipeline, _ = load_current(models_dir)
    metrics = evaluate(pipeline, table)
    cm = metrics["confusion_matrix"]
    assert sum(cm.values()) == len(table)
    assert 0 <= metrics["accuracy"] <= 1
    importance = feature_importance(pipeline)
    assert "skills_too_advanced" in set(importance["feature"])


# --- Registry ------------------------------------------------------------------------


def test_registry_versions_and_rollback(trained, tmp_path):
    _, models_dir = trained
    pipeline, card = load_current(models_dir)
    assert card["version"] == 1 and card["synthetic_data"] is True and card["features"] == FEATURES

    folder = tmp_path / "registry"
    assert load_current(folder) is None
    save_model(pipeline, {"algorithm": "a"}, folder)
    save_model(pipeline, {"algorithm": "b"}, folder)
    assert list_versions(folder) == [1, 2]
    assert load_current(folder)[1]["algorithm"] == "b"
    set_current(1, folder)  # roll back
    assert load_current(folder)[1]["algorithm"] == "a"
    assert json.loads((folder / f"{MODEL_NAME}.json").read_text())["current_version"] == 1
    with pytest.raises(ValueError):
        set_current(9, folder)


# --- Predictor and API 3 integration ----------------------------------------------------


def test_predictor_returns_probabilities(trained):
    _, models_dir = trained
    predictor = CompletionPredictor.from_files(models_dir)
    assert predictor.version == 1
    probs = predictor.predict_many("E1001", ["C-SQL-201", "C-AWS-101", "NOT-A-COURSE"])
    assert set(probs) == {"C-SQL-201", "C-AWS-101"}
    assert all(0.0 <= p <= 1.0 for p in probs.values())
    assert predictor("E1001", "NOT-A-COURSE") is None


def test_predictor_is_none_without_a_model(tmp_path):
    assert CompletionPredictor.from_files(tmp_path) is None


def test_too_advanced_courses_get_lower_probability(trained):
    predictor = CompletionPredictor.from_files(trained[1])
    assert predictor("E1001", "C-MLOPS-201") < predictor("E1001", "C-AWS-101")


def test_recommendations_use_the_model(trained):
    predictor = CompletionPredictor.from_files(trained[1])
    result = TrainingRecommendationService(CsvLmsRepository(), completion_model=predictor).recommend("E1001")
    assert "completion_probability" in result.weights_used
    for rec in result.recommendations:
        expected = predictor("E1001", rec.course.course_id)
        assert rec.components["completion_probability"] == pytest.approx(expected, abs=0.005)  # shown to 2 dp
    assert any("SYNTHETIC" in n for n in result.notes)
