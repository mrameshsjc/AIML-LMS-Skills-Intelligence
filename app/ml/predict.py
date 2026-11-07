"""
Predicting course completion with the registered model (Phase 8).

PURPOSE
    Answer "how likely is employee E to complete course C?" with a
    probability between 0 and 1. The training-recommendation service (API 3)
    calls a CompletionPredictor for its completion_probability score part.

HOW
    1. FeatureBuilder computes the same features as in training, for "now"
       (all past enrolments count).
    2. The saved pipeline prepares them and returns predict_proba.
    Results are cached per (employee, course), because the same pair is asked
    for again on every request.

IF THERE IS NO MODEL
    from_files() returns None and API 3 works exactly as before (the weight of
    the missing part is shared among the others). The API never fails just
    because no model has been trained.
"""

from __future__ import annotations

from pathlib import Path

from app.data_processing.loader import load_all
from app.ml.features import FeatureBuilder
from app.ml.model_registry import load_current


class CompletionPredictor:
    def __init__(self, pipeline, metadata: dict, features: FeatureBuilder) -> None:
        self.pipeline = pipeline
        self.metadata = metadata
        self.features = features
        self._cache: dict[tuple[str, str], float] = {}

    @classmethod
    def from_files(
        cls, models_dir: str | Path = "models", data_dir: str | Path | None = None
    ) -> CompletionPredictor | None:
        loaded = load_current(models_dir)
        if loaded is None:
            return None
        pipeline, metadata = loaded
        return cls(pipeline, metadata, FeatureBuilder(load_all(data_dir)))

    @property
    def version(self) -> int:
        return int(self.metadata.get("version", 0))

    def predict_many(self, employee_id: str, course_ids: list[str]) -> dict[str, float]:
        todo = [c for c in course_ids if (employee_id, c) not in self._cache]
        if todo:
            rows = self.features.features_for(employee_id, todo)
            known = [c for c in todo if c in self.features.courses.index]
            if known:
                for course_id, p in zip(known, self.pipeline.predict_proba(rows)[:, 1], strict=True):
                    self._cache[(employee_id, course_id)] = round(float(p), 3)
        return {c: self._cache[(employee_id, c)] for c in course_ids if (employee_id, c) in self._cache}

    def __call__(self, employee_id: str, course_id: str) -> float | None:
        """The CompletionModel signature used by TrainingRecommendationService."""
        return self.predict_many(employee_id, [course_id]).get(course_id)
