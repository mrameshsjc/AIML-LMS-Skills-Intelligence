"""
11 - Train and compare models, register the best one.

LESSON
    Three algorithms are compared fairly with 5-fold CROSS-VALIDATION on the
    TRAINING data only:
        logistic_regression   weighted sum of features -> probability (easy to read)
        decision_tree         a short flowchart of yes/no questions
        random_forest         200 small trees voting together
    The training rows are cut into 5 parts; each model trains on 4 and is
    scored on the 5th, five times over. The highest average ROC AUC wins.

    The winner is trained on all training rows and saved as a NEW VERSION in
    the model registry (models/), so older versions remain for rollback.
    API 3 uses the current version for completion_probability (restart the
    server after training).

    Each model is a scikit-learn PIPELINE: scaling + one-hot encoding + model,
    so exactly the same preparation runs at training and prediction time.

HOW TO RUN (from the project folder)
    PS> python data_science/11_train_model.py

INPUT    data/processed/ml/train.csv (run script 10 first)
OUTPUT   models/completion_model_vN.joblib + .json, and the pointer models/completion_model.json
"""

import argparse
import sys
from datetime import UTC, datetime

import pandas as pd
from _common import explain, heading

from app.data_processing.loader import resolve_folder
from app.ml.evaluate import evaluate
from app.ml.features import FEATURES, LABEL
from app.ml.model_registry import save_model
from app.ml.train import SEED, compare_models, fit_model

parser = argparse.ArgumentParser(description="Lesson 11: train and register the completion model.")
parser.add_argument("--folder", default="data/processed/ml", help="folder with train.csv and test.csv")
parser.add_argument("--models", default="models", help="model registry folder (default models)")
args = parser.parse_args()

folder = resolve_folder(args.folder)
if not (folder / "train.csv").exists():
    sys.exit("train.csv not found. Run: python data_science/10_split_data.py")
train = pd.read_csv(folder / "train.csv")
test = pd.read_csv(folder / "test.csv")

heading("1. Compare three algorithms (5-fold cross-validation on the training rows)")
comparison = compare_models(train)
print(comparison.to_string(index=False))
best = comparison.loc[0, "model"]
explain(f"""
cv_roc_auc: 0.5 = coin flip, 1.0 = perfect ranking of completers above droppers. Higher is better.
cv_roc_auc_std: how much the score varied between the 5 folds (smaller = more stable).
Winner: {best}.
""")

heading(f"2. Train {best} on all {len(train)} training rows and register it")
pipeline = fit_model(best, train)
metrics = evaluate(pipeline, test)
metadata = {
    "algorithm": best,
    "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
    "synthetic_data": True,
    "rows": {"train": len(train), "test": len(test)},
    "features": FEATURES,
    "label": LABEL,
    "cross_validation": comparison.to_dict(orient="records"),
    "test_metrics": metrics,
    "seed": SEED,
}
path, version = save_model(pipeline, metadata, args.models)
print(f"Saved version {version}: {path}")
print(f"Current version pointer: {resolve_folder(args.models) / 'completion_model.json'}")
explain("""
Every run creates a NEW version; nothing is overwritten. To roll back:
  python -c "from app.ml.model_registry import set_current; set_current(1)"
Restart the API (uvicorn) to load the new model.  ->  next: python data_science/12_evaluate_model.py
""")
