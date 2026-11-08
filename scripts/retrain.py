"""
Retrain the completion model from the command line (Phase 16).

The same controlled workflow as API 6 (POST /api/v1/ml/retrain): validate the
data, train, evaluate, compare with the current model, quality gate, register,
promote only if approved, log to MLflow. Someone who can run this script on the
server is already an administrator, so no admin key is needed.

HOW TO RUN (from the project folder)
    PS> python scripts/retrain.py --reason "New training history"
    PS> python scripts/retrain.py --no-promote          (register only; keep the current model)

EXIT CODE: 0 promoted or registered, 1 rejected
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.dependencies import get_retraining_service  # noqa: E402

parser = argparse.ArgumentParser(description="Retrain the course-completion model.")
parser.add_argument("--reason", default="", help="why retrain now (kept in the history)")
parser.add_argument(
    "--no-promote", action="store_true", help="register the new version but keep the current one"
)
args = parser.parse_args()

report = get_retraining_service().retrain("command line", args.reason, promote=not args.no_promote)
print(f"Status: {report.status}")
print(f"Versions: previous {report.previous_version} -> new {report.new_version}")
print(f"Current version now: {report.current_version}")
if report.data_errors:
    print(f"Data errors: {report.data_errors}")
    for issue in report.data_issues:
        print(f"  - {issue}")
if report.algorithm:
    current = (report.current_metrics or {}).get("roc_auc")
    print(
        f"Best algorithm: {report.algorithm}; test ROC AUC {report.new_metrics['roc_auc']}"
        + (f" (current model: {current})" if current else "")
    )
for check in report.gate:
    print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
mlflow = report.mlflow
if mlflow.get("enabled"):
    print(f"MLflow run {mlflow.get('run_id')}, registered version {mlflow.get('registered_version')}")
    print(f"MLflow store: {mlflow.get('tracking_uri')}  (view: mlflow ui --backend-store-uri <that URI>)")
for note in report.notes:
    print(f"note: {note}")
print(f"Took {report.duration_seconds:.1f} s. Restart the API so it loads a newly promoted model.")
sys.exit(0 if report.status in ("promoted", "registered_not_promoted") else 1)
