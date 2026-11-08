"""
Controlled retraining of the completion model (Phase 16, API 6).

PURPOSE
    Retrain the course-completion model on the current LMS data - but only let
    the new model into production if it is good enough. A model that quietly
    got worse would make every recommendation worse without anyone noticing.

THE WORKFLOW (requirements, section 17)
    1. Validate data     the same checks as scripts 03-06; any error stops here.
    2. Features          build the training table; enough rows and both outcomes?
    3. Train             compare three algorithms (5-fold CV), fit the best.
    4. Evaluate          metrics on test rows the model never saw.
    5. Compare           evaluate the CURRENT model on the SAME test rows,
                         so the comparison is fair.
    6. Quality gate      three checks, all must pass:
                           - ROC AUC at least ML_MIN_ROC_AUC (default 0.60);
                           - clearly better than chance (ROC AUC > 0.5);
                           - not worse than the current model by more than
                             ML_MAX_REGRESSION (default 0.01).
    7. Register          ALWAYS save the new version (rejected ones too, for the
                         record); existing versions are never touched.
    8. Promote           make it current ONLY if it passed the gate (and the
                         caller asked to promote). Otherwise the current model stays.
    9. Track             log the run to MLflow; register approved models there
                         with the alias "champion".
   10. History           append a line to models/retraining_history.jsonl.

    One retraining at a time: a second request while one is running is refused.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.core.errors import ConflictError
from app.data_processing.loader import load_all, resolve_folder
from app.data_processing.validators import run_checks
from app.ml.evaluate import evaluate
from app.ml.features import FEATURES, LABEL, FeatureBuilder
from app.ml.model_registry import MODEL_NAME, current_version, load_current, save_model, set_current
from app.ml.train import SEED, compare_models, fit_model, split_data

HISTORY_FILE = "retraining_history.jsonl"
_LOCK = threading.Lock()

PROMOTED = "promoted"  # passed the gate and is now the current model
NOT_PROMOTED = "registered_not_promoted"  # passed the gate, saved, but promote=false
REJECTED_GATE = "rejected_by_quality_gate"  # saved for the record, not used
REJECTED_DATA = "rejected_invalid_data"  # stopped before training


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class RetrainReport:
    status: str  # promoted | registered_not_promoted | rejected_by_quality_gate | rejected_invalid_data
    started_at: str
    requested_by: str
    reason: str
    previous_version: int | None
    new_version: int | None = None
    current_version: int | None = None
    data_errors: int = 0
    data_warnings: int = 0
    data_issues: list[str] = field(default_factory=list)  # the first few problems, readable
    rows: dict = field(default_factory=dict)  # total / train / test
    algorithm: str | None = None
    cross_validation: list[dict] = field(default_factory=list)
    new_metrics: dict = field(default_factory=dict)
    current_metrics: dict | None = None  # the current model on the same test rows
    gate: list[GateCheck] = field(default_factory=list)
    mlflow: dict = field(default_factory=dict)  # enabled, run_id, registered_version, tracking_uri
    duration_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def gate_passed(self) -> bool:
        return bool(self.gate) and all(c.passed for c in self.gate)


class RetrainingService:
    def __init__(
        self,
        data_dir: str | Path | None,
        models_dir: str | Path,
        tracker_factory,
        min_roc_auc: float = 0.60,
        max_regression: float = 0.01,
        min_rows: int = 200,
    ) -> None:
        self.data_dir = data_dir
        self.models_dir = models_dir
        self.tracker_factory = tracker_factory  # creates the MLflow (or null) tracker for one run
        self.min_roc_auc = min_roc_auc
        self.max_regression = max_regression
        self.min_rows = min_rows

    def retrain(self, requested_by: str = "admin", reason: str = "", promote: bool = True) -> RetrainReport:
        if not _LOCK.acquire(blocking=False):
            raise ConflictError(
                "RETRAINING_IN_PROGRESS", "A retraining run is already in progress; try again later."
            )
        try:
            return self._retrain(requested_by, reason, promote)
        finally:
            _LOCK.release()

    # --- the workflow --------------------------------------------------------------------------
    def _retrain(self, requested_by: str, reason: str, promote: bool) -> RetrainReport:
        start = time.perf_counter()
        report = RetrainReport(
            status=REJECTED_DATA,
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            requested_by=requested_by,
            reason=reason,
            previous_version=current_version(self.models_dir),
        )

        # 1. Validate the data
        issues = run_checks(self.data_dir)
        errors = [i for i in issues if i.severity == "error"]
        report.data_errors, report.data_warnings = len(errors), len(issues) - len(errors)
        report.data_issues = [f"{i.dataset} {i.column}: {i.message}" for i in errors[:5]]
        if errors:
            report.notes.append("Training data has errors: fix them (or clean the data) and retrain.")
            return self._finish(report, start)

        # 2. Features
        table = FeatureBuilder(load_all(self.data_dir)).training_table()
        share = table[LABEL].mean() if len(table) else 0.0
        if len(table) < self.min_rows or not 0.1 <= share <= 0.9:
            report.data_issues = [
                f"{len(table)} finished enrolments ({share:.0%} completed); need at least {self.min_rows} "
                "with both outcomes at 10 % or more."
            ]
            report.notes.append("Not enough usable training data.")
            return self._finish(report, start)

        # 3. Train and 4. evaluate
        train, test = split_data(table)
        comparison = compare_models(train)
        report.algorithm = str(comparison.loc[0, "model"])
        report.cross_validation = comparison.to_dict(orient="records")
        pipeline = fit_model(report.algorithm, train)
        report.new_metrics = evaluate(pipeline, test)
        report.rows = {"total": len(table), "train": len(train), "test": len(test)}

        # 5. Compare with the current model on the same test rows
        report.current_metrics = self._current_metrics(test, report)

        # 6. Quality gate
        report.gate = self._gate(report.new_metrics, report.current_metrics)

        # 7. Register (always) and 8. promote (only if approved)
        approved = report.gate_passed
        card = {
            "algorithm": report.algorithm,
            "trained_at": report.started_at,
            "data_dir": str(resolve_folder(self.data_dir)),
            "synthetic_data": True,
            "rows": report.rows,
            "features": FEATURES,
            "cross_validation": report.cross_validation,
            "test_metrics": report.new_metrics,
            "seed": SEED,
            "status": "approved" if approved else "rejected",
            "quality_gate": [asdict(c) for c in report.gate],
            "compared_with": {"version": report.previous_version, "metrics": report.current_metrics},
            "requested_by": requested_by,
            "reason": reason,
        }
        _, report.new_version = save_model(pipeline, card, self.models_dir, make_current=False)
        if approved and promote:
            set_current(report.new_version, self.models_dir)
            report.status = PROMOTED
        else:
            report.status = NOT_PROMOTED if approved else REJECTED_GATE
            if approved:
                report.notes.append("Approved but not promoted (promote=false): the current model stays.")
            else:
                report.notes.append(
                    "The new version is kept for the record, but the current model stays in use."
                )

        # 9. Track in MLflow
        self._track(report, pipeline, card, approved and promote)
        return self._finish(report, start)

    def _current_metrics(self, test: pd.DataFrame, report: RetrainReport) -> dict | None:
        loaded = load_current(self.models_dir)
        if loaded is None:
            report.notes.append("No current model: the new one is compared with the quality floor only.")
            return None
        pipeline, card = loaded
        if card.get("features") != FEATURES:
            report.notes.append(
                "The current model uses other features; it cannot be compared on the same rows."
            )
            return None
        return evaluate(pipeline, test)

    def _gate(self, new: dict, current: dict | None) -> list[GateCheck]:
        auc = new["roc_auc"]
        checks = [
            GateCheck(
                "minimum_quality",
                auc >= self.min_roc_auc,
                f"ROC AUC {auc} {'>=' if auc >= self.min_roc_auc else '<'} required {self.min_roc_auc}",
            ),
            GateCheck("better_than_chance", auc > 0.5, f"ROC AUC {auc} vs 0.5 for random guessing"),
        ]
        if current is None:
            checks.append(GateCheck("no_regression", True, "No current model to compare with."))
        else:
            delta = round(auc - current["roc_auc"], 3)
            checks.append(
                GateCheck(
                    "no_regression",
                    delta >= -self.max_regression,
                    f"ROC AUC {auc} vs current {current['roc_auc']} on the same test rows "
                    f"(change {delta:+.3f}; allowed down to -{self.max_regression})",
                )
            )
        return checks

    def _track(self, report: RetrainReport, pipeline, card: dict, champion: bool) -> None:
        try:
            tracker = self.tracker_factory()
            tags = {
                "status": report.status,
                "requested_by": report.requested_by,
                "local_version": str(report.new_version),
            }
            with tracker.run(f"{MODEL_NAME}_v{report.new_version}", tags):
                tracker.log_params(
                    {
                        "algorithm": report.algorithm,
                        "seed": SEED,
                        "features": ",".join(FEATURES),
                        **report.rows,
                    }
                )
                metrics = {
                    f"test_{k}": v for k, v in report.new_metrics.items() if isinstance(v, int | float)
                }
                metrics.update({f"cv_{r['model']}_roc_auc": r["cv_roc_auc"] for r in report.cross_validation})
                if report.current_metrics:
                    metrics["current_model_test_roc_auc"] = report.current_metrics["roc_auc"]
                tracker.log_metrics(metrics)
                tracker.log_dict(card, "model_card.json")
                tracker.log_model(pipeline)
                registered = tracker.register(report.new_version) if champion else None
            report.mlflow = {
                "enabled": tracker.enabled,
                "run_id": tracker.run_id,
                "registered_version": registered,
                "tracking_uri": tracker.tracking_uri,
            }
            if not tracker.enabled:
                report.notes.append("MLflow is not used (not installed, or MLFLOW_ENABLED=false).")
        except Exception as error:  # tracking must never undo a finished training run
            report.mlflow = {"enabled": True, "run_id": None, "registered_version": None, "error": str(error)}
            report.notes.append(f"MLflow tracking failed ({error}); the model itself was saved normally.")

    def _finish(self, report: RetrainReport, start: float) -> RetrainReport:
        report.current_version = current_version(self.models_dir)
        report.duration_seconds = round(time.perf_counter() - start, 2)
        folder = resolve_folder(self.models_dir)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / HISTORY_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(_summary(report)) + "\n")
        return report


def _summary(report: RetrainReport) -> dict:
    return {
        "started_at": report.started_at,
        "status": report.status,
        "requested_by": report.requested_by,
        "reason": report.reason,
        "previous_version": report.previous_version,
        "new_version": report.new_version,
        "current_version": report.current_version,
        "algorithm": report.algorithm,
        "test_roc_auc": report.new_metrics.get("roc_auc"),
        "current_model_roc_auc": (report.current_metrics or {}).get("roc_auc"),
        "gate_passed": report.gate_passed,
        "mlflow_run_id": report.mlflow.get("run_id"),
        "duration_seconds": report.duration_seconds,
    }


def read_history(models_dir: str | Path, limit: int = 20) -> list[dict]:
    """The latest retraining runs, newest first."""
    file = resolve_folder(models_dir) / HISTORY_FILE
    if not file.exists():
        return []
    lines = file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in reversed(lines[-limit:]) if line.strip()]
