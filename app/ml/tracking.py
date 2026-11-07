"""
Experiment tracking with MLflow (Phase 16).

WHAT MLFLOW ADDS
    The file registry (model_registry.py) keeps the model versions the API
    loads. MLflow keeps the EXPERIMENT RECORD around them:
      - every training run: parameters, metrics, the quality gate, the model file;
      - a model registry: approved versions, with the alias "champion" on the
        one in use;
      - a web UI to compare runs side by side:
            mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db
        then open http://127.0.0.1:5000

    The API keeps loading models from models/ (fast, no MLflow server needed);
    MLflow is the history and audit trail. Each MLflow model version carries the
    tag local_version, so the two always line up.

WHERE MLFLOW STORES DATA
    MLFLOW_TRACKING_URI, by default a SQLite file mlruns/mlflow.db in the project
    folder, with model files in mlruns/artifacts (git-ignored). A shared MLflow
    server (http://...) works the same way.

WITHOUT MLFLOW
    MLFLOW_ENABLED=auto (default) uses MLflow when the package is installed, and
    otherwise a NullTracker that records nothing - retraining still works, and
    the result says that MLflow was not used.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path

from app.data_processing.loader import PROJECT_ROOT


def mlflow_installed() -> bool:
    return importlib.util.find_spec("mlflow") is not None


def default_tracking_uri() -> str:
    """sqlite:///<project>/mlruns/mlflow.db - absolute, so the folder you start from does not matter."""
    return f"sqlite:///{(PROJECT_ROOT / 'mlruns' / 'mlflow.db').as_posix()}"


class NullTracker:
    """Tracks nothing. Used when MLflow is not installed or MLFLOW_ENABLED=false."""

    enabled = False
    tracking_uri = ""

    @contextmanager
    def run(self, name: str, tags: dict):
        yield self

    def log_params(self, params: dict) -> None: ...

    def log_metrics(self, metrics: dict) -> None: ...

    def log_dict(self, data: dict, file_name: str) -> None: ...

    def log_model(self, pipeline) -> None: ...

    def register(self, local_version: int) -> str | None:
        return None

    @property
    def run_id(self) -> str | None:
        return None


class MlflowTracker:
    """Logs each retraining run to MLflow and registers approved models."""

    enabled = True

    def __init__(self, tracking_uri: str, experiment: str, model_name: str) -> None:
        import mlflow  # imported here: only needed when MLflow is used

        self.mlflow = mlflow
        self.tracking_uri = tracking_uri
        self.model_name = model_name
        store = PROJECT_ROOT / "mlruns"
        if tracking_uri.startswith("sqlite:///"):  # model files go next to the database file
            store = Path(tracking_uri.removeprefix("sqlite:///")).parent
            store.mkdir(parents=True, exist_ok=True)
        mlflow.set_tracking_uri(tracking_uri)
        found = mlflow.get_experiment_by_name(experiment)
        if found is None:
            artifacts = (store / "artifacts").resolve()
            artifacts.mkdir(parents=True, exist_ok=True)
            self.experiment_id = mlflow.create_experiment(experiment, artifact_location=artifacts.as_uri())
        else:
            self.experiment_id = found.experiment_id
        self._run = None
        self._model_uri: str | None = None

    @contextmanager
    def run(self, name: str, tags: dict):
        with self.mlflow.start_run(experiment_id=self.experiment_id, run_name=name, tags=tags) as active:
            self._run = active
            yield self

    @property
    def run_id(self) -> str | None:
        return self._run.info.run_id if self._run else None

    def log_params(self, params: dict) -> None:
        self.mlflow.log_params({k: str(v)[:500] for k, v in params.items()})

    def log_metrics(self, metrics: dict) -> None:
        self.mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})

    def log_dict(self, data: dict, file_name: str) -> None:
        self.mlflow.log_dict(data, file_name)

    def log_model(self, pipeline) -> None:
        import mlflow.sklearn

        info = mlflow.sklearn.log_model(sk_model=pipeline, name="model")
        self._model_uri = info.model_uri

    def register(self, local_version: int) -> str | None:
        """Register the logged model; mark it as the champion (the version in use)."""
        if self._model_uri is None:
            return None
        version = self.mlflow.register_model(self._model_uri, self.model_name)
        client = self.mlflow.MlflowClient()
        client.set_model_version_tag(self.model_name, version.version, "local_version", str(local_version))
        client.set_registered_model_alias(self.model_name, "champion", version.version)
        return str(version.version)


def choose_tracker(
    setting: str, tracking_uri: str, experiment: str, model_name: str
) -> NullTracker | MlflowTracker:
    """MLFLOW_ENABLED: auto (MLflow if installed), true (must be installed), false (never)."""
    if setting == "false" or (setting == "auto" and not mlflow_installed()):
        return NullTracker()
    if not mlflow_installed():
        raise RuntimeError("MLFLOW_ENABLED=true, but MLflow is not installed. Run: pip install mlflow")
    return MlflowTracker(tracking_uri or default_tracking_uri(), experiment, model_name)
