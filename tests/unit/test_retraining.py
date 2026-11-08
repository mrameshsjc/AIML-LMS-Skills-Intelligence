"""
Tests for controlled retraining (Phase 16): the workflow, the quality gate,
version safety, the history, the admin key and MLflow tracking.

Models are trained into temporary folders. The MLflow test runs only when
MLflow is installed and uses a temporary SQLite store.

HOW TO RUN
    PS> pytest tests/unit/test_retraining.py -v
"""

import importlib.util
import threading
from pathlib import Path

import pytest

from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import check_admin_key
from app.ml.model_registry import current_version, list_cards, set_current
from app.ml.retraining import (
    _LOCK,
    NOT_PROMOTED,
    PROMOTED,
    REJECTED_DATA,
    REJECTED_GATE,
    RetrainingService,
    read_history,
)
from app.ml.tracking import NullTracker, choose_tracker, mlflow_installed

ROOT = Path(__file__).resolve().parents[2]


class RecordingTracker(NullTracker):
    """Behaves like MLflow, but only remembers what it was given."""

    enabled = True
    tracking_uri = "memory://"
    calls: list = []

    def run(self, name, tags):
        RecordingTracker.calls.append(("run", name, tags))
        return super().run(name, tags)

    def log_params(self, params):
        RecordingTracker.calls.append(("params", params))

    def log_metrics(self, metrics):
        RecordingTracker.calls.append(("metrics", metrics))

    def log_model(self, pipeline):
        RecordingTracker.calls.append(("model", type(pipeline).__name__))

    def register(self, local_version):
        RecordingTracker.calls.append(("register", local_version))
        return "7"

    @property
    def run_id(self):
        return "run-123"


@pytest.fixture
def models(tmp_path):
    RecordingTracker.calls = []
    return tmp_path / "models"


def service(models, **kwargs) -> RetrainingService:
    return RetrainingService(None, models, RecordingTracker, **kwargs)


@pytest.mark.slow
def test_first_model_is_promoted(models):
    report = service(models).retrain("admin", "first")
    assert report.status == PROMOTED and report.gate_passed
    assert (report.previous_version, report.new_version, report.current_version) == (None, 1, 1)
    assert report.algorithm == "logistic_regression" and report.new_metrics["roc_auc"] > 0.6
    assert report.current_metrics is None and report.rows["total"] == 443
    assert list_cards(models)[0]["status"] == "approved"
    assert report.mlflow == {
        "enabled": True,
        "run_id": "run-123",
        "registered_version": "7",
        "tracking_uri": "memory://",
    }


@pytest.mark.slow
def test_retraining_is_compared_with_the_current_model_on_the_same_rows(models):
    service(models).retrain()
    report = service(models).retrain()
    assert report.current_metrics is not None
    assert report.current_metrics["test_rows"] == report.new_metrics["test_rows"]
    no_regression = next(c for c in report.gate if c.name == "no_regression")
    assert no_regression.passed and "vs current" in no_regression.detail
    assert report.status == PROMOTED and current_version(models) == 2


@pytest.mark.slow
def test_quality_gate_failure_keeps_the_current_model(models):
    service(models).retrain()
    report = service(models, min_roc_auc=0.95).retrain()
    assert report.status == REJECTED_GATE and not report.gate_passed
    assert report.new_version == 2 and report.current_version == 1  # saved for the record, not used
    assert [c["status"] for c in list_cards(models)] == ["approved", "rejected"]
    assert ("register", 2) not in RecordingTracker.calls  # rejected models are not registered in MLflow


@pytest.mark.slow
def test_regression_is_caught(models):
    service(models).retrain()
    card = list_cards(models)[0]
    worse = service(models, max_regression=0.0)
    # pretend the current model was much better on the same rows
    worse._current_metrics = lambda test, report: {**card["test_metrics"], "roc_auc": 0.99}
    report = worse.retrain()
    assert report.status == REJECTED_GATE
    assert not next(c for c in report.gate if c.name == "no_regression").passed


@pytest.mark.slow
def test_register_without_promoting(models):
    service(models).retrain()
    report = service(models).retrain(promote=False)
    assert report.status == NOT_PROMOTED and report.current_version == 1 and report.new_version == 2


def test_invalid_data_stops_before_training(models, tmp_path):
    spec = importlib.util.spec_from_file_location("make_dirty_data", ROOT / "scripts" / "make_dirty_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.make_dirty(tmp_path / "dirty")
    report = RetrainingService(tmp_path / "dirty", models, RecordingTracker).retrain()
    assert report.status == REJECTED_DATA and report.data_errors > 0 and report.data_issues
    assert report.new_version is None and list_cards(models) == [] and RecordingTracker.calls == []


def test_too_little_data_stops_before_training(models):
    report = service(models, min_rows=10_000).retrain()
    assert report.status == REJECTED_DATA and "need at least 10000" in report.data_issues[0]


@pytest.mark.slow
def test_history_records_every_run(models):
    service(models).retrain("admin", "first")
    service(models, min_roc_auc=0.95).retrain("admin", "strict")
    history = read_history(models)
    assert [h["status"] for h in history] == [REJECTED_GATE, PROMOTED]  # newest first
    assert history[1]["reason"] == "first" and history[1]["mlflow_run_id"] == "run-123"


def test_only_one_run_at_a_time(models):
    _LOCK.acquire()
    try:
        with pytest.raises(ConflictError) as error:
            service(models).retrain()
        assert error.value.code == "RETRAINING_IN_PROGRESS"
    finally:
        _LOCK.release()


@pytest.mark.slow
def test_mlflow_failure_does_not_lose_the_model(models):
    class BrokenTracker(NullTracker):
        enabled = True

        def log_model(self, pipeline):
            raise RuntimeError("MLflow server down")

    report = RetrainingService(None, models, BrokenTracker).retrain()
    assert report.status == PROMOTED and current_version(models) == 1
    assert "MLflow server down" in report.mlflow["error"]


@pytest.mark.slow
def test_rollback_after_retraining(models):
    service(models).retrain()
    service(models).retrain()
    set_current(1, models)
    assert current_version(models) == 1 and len(list_cards(models)) == 2


# --- Administrator key -------------------------------------------------------------------------------


def test_admin_key():
    assert check_admin_key("s3cret", "s3cret") == "admin"
    with pytest.raises(UnauthorizedError):
        check_admin_key(None, "s3cret")
    with pytest.raises(UnauthorizedError):
        check_admin_key("guess", "s3cret")
    with pytest.raises(ForbiddenError) as error:
        check_admin_key("anything", "")  # no key configured: admin actions are off
    assert error.value.code == "ADMIN_ACTIONS_DISABLED"


# --- Choosing the tracker ------------------------------------------------------------------------------


def test_choose_tracker():
    assert isinstance(choose_tracker("false", "", "x", "m"), NullTracker)
    if not mlflow_installed():
        assert isinstance(choose_tracker("auto", "", "x", "m"), NullTracker)
        with pytest.raises(RuntimeError, match="pip install mlflow"):
            choose_tracker("true", "", "x", "m")


@pytest.mark.slow
@pytest.mark.skipif(not mlflow_installed(), reason="MLflow is not installed")
def test_real_mlflow_run_and_registry(models, tmp_path):
    import mlflow

    uri = f"sqlite:///{(tmp_path / 'mlflow' / 'mlflow.db').as_posix()}"
    report = RetrainingService(
        None, models, lambda: choose_tracker("true", uri, "test-experiment", "completion_model")
    ).retrain()
    assert (
        report.status == PROMOTED and report.mlflow["enabled"] and report.mlflow["registered_version"] == "1"
    )
    client = mlflow.MlflowClient(tracking_uri=uri)
    run = client.get_run(report.mlflow["run_id"])
    assert float(run.data.metrics["test_roc_auc"]) == report.new_metrics["roc_auc"]
    assert run.data.tags["status"] == PROMOTED
    champion = client.get_model_version_by_alias("completion_model", "champion")
    # MLflow 3.18 returns the version number as an int (older versions: a string), so compare as text
    assert str(champion.version) == "1" and champion.tags["local_version"] == "1"
    assert (tmp_path / "mlflow" / "artifacts").is_dir()  # model files next to the database


def test_concurrent_requests_do_not_both_train(models, monkeypatch):
    started, release = threading.Event(), threading.Event()
    svc = service(models)

    def slow(*args, **kwargs):
        started.set()
        release.wait(5)
        raise RuntimeError("stopped")

    monkeypatch.setattr(svc, "_retrain", slow)
    worker = threading.Thread(target=lambda: pytest.raises(RuntimeError, svc.retrain))
    worker.start()
    started.wait(5)
    with pytest.raises(ConflictError):
        service(models).retrain()
    release.set()
    worker.join(5)
