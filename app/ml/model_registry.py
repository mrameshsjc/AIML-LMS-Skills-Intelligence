"""
A small file-based model registry (Phase 8; MLflow replaces it in Phase 16).

PURPOSE
    Save every trained model as a new VERSION, never overwriting an old one,
    and keep a pointer to the version in use. That gives three things a
    production system needs:
      - traceability   each version has a JSON card: algorithm, date, data, metrics
      - rollback       older versions stay on disk; point back to one in seconds
      - safety         the API only loads what the pointer says

FILES (in the models/ folder, which is git-ignored)
    completion_model_v1.joblib   the trained pipeline (joblib = efficient Python object file)
    completion_model_v1.json     its card (metadata)
    completion_model.json        the pointer: {"current_version": 1, ...}

WHY NOT COMMIT MODELS TO GIT
    Model files are binary, change on every training run, and can be large.
    They are rebuilt from code + data with `python data_science/11_train_model.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib

from app.data_processing.loader import resolve_folder

MODEL_NAME = "completion_model"


def _pointer(models_dir: Path) -> Path:
    return models_dir / f"{MODEL_NAME}.json"


def list_versions(models_dir: str | Path = "models") -> list[int]:
    folder = resolve_folder(models_dir)
    return sorted(int(p.stem.rsplit("_v", 1)[1]) for p in folder.glob(f"{MODEL_NAME}_v*.joblib"))


def save_model(
    pipeline, metadata: dict, models_dir: str | Path = "models", make_current: bool = True
) -> tuple[Path, int]:
    """Save a new version (never overwrites). Returns (model path, version)."""
    folder = resolve_folder(models_dir)
    folder.mkdir(parents=True, exist_ok=True)
    version = max(list_versions(folder), default=0) + 1
    path = folder / f"{MODEL_NAME}_v{version}.joblib"
    joblib.dump(pipeline, path)
    card = {"name": MODEL_NAME, "version": version, **metadata}
    (folder / f"{MODEL_NAME}_v{version}.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    if make_current:
        set_current(version, folder)
    return path, version


def set_current(version: int, models_dir: str | Path = "models") -> None:
    """Point the API at a version (also how to roll back)."""
    folder = resolve_folder(models_dir)
    if version not in list_versions(folder):
        raise ValueError(f"{MODEL_NAME} version {version} does not exist in {folder}")
    _pointer(folder).write_text(
        json.dumps({"name": MODEL_NAME, "current_version": version}, indent=2), encoding="utf-8"
    )


def load_current(models_dir: str | Path = "models") -> tuple[object, dict] | None:
    """(pipeline, metadata card) of the current version, or None if no model is registered."""
    folder = resolve_folder(models_dir)
    pointer = _pointer(folder)
    if not pointer.exists():
        return None
    version = json.loads(pointer.read_text(encoding="utf-8"))["current_version"]
    pipeline = joblib.load(folder / f"{MODEL_NAME}_v{version}.joblib")
    card = json.loads((folder / f"{MODEL_NAME}_v{version}.json").read_text(encoding="utf-8"))
    return pipeline, card


def current_version(models_dir: str | Path = "models") -> int | None:
    """The version the API uses, or None if no model is registered."""
    pointer = _pointer(resolve_folder(models_dir))
    return json.loads(pointer.read_text(encoding="utf-8"))["current_version"] if pointer.exists() else None


def list_cards(models_dir: str | Path = "models") -> list[dict]:
    """Every saved version's model card (oldest first) - for the dashboard's model page."""
    folder = resolve_folder(models_dir)
    return [
        json.loads((folder / f"{MODEL_NAME}_v{v}.json").read_text(encoding="utf-8"))
        for v in list_versions(folder)
    ]
