"""Request and response shapes for API 6 (POST /api/v1/ml/retrain) and GET /api/v1/ml/status."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetrainRequest(BaseModel):
    reason: str = Field(default="", max_length=500, description="Why retrain now (kept in the audit trail).")
    promote: bool = Field(
        default=True,
        description="Make the new model current if it passes the quality gate. false = register only.",
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"reason": "New training history uploaded"}, {"promote": False}]}
    )


class GateCheckOut(BaseModel):
    name: str = Field(examples=["no_regression"])
    passed: bool
    detail: str


class DataValidationOut(BaseModel):
    errors: int
    warnings: int
    issues: list[str] = Field(description="The first problems found (training stops on any error).")


class TrainingOut(BaseModel):
    rows: dict[str, int] = Field(description="total, train and test rows (finished enrolments).")
    algorithm: str | None = Field(description="The algorithm that won the cross-validation.")
    cross_validation: list[dict[str, Any]]


class RetrainResponse(BaseModel):
    status: str = Field(
        examples=["promoted"],
        description="promoted, registered_not_promoted, rejected_by_quality_gate or rejected_invalid_data.",
    )
    gate_passed: bool
    previous_version: int | None = Field(description="The current model before this run.")
    new_version: int | None = Field(
        description="The version saved by this run (None if stopped before training)."
    )
    current_version: int | None = Field(description="The model the API uses after this run.")
    requested_by: str
    reason: str
    started_at: str
    data_validation: DataValidationOut
    training: TrainingOut
    new_metrics: dict[str, Any] = Field(description="Test metrics of the new model.")
    current_metrics: dict[str, Any] | None = Field(description="The previous model on the SAME test rows.")
    quality_gate: list[GateCheckOut]
    mlflow: dict[str, Any] = Field(description="enabled, run_id, registered_version, tracking_uri.")
    duration_seconds: float
    notes: list[str]


class ModelVersionOut(BaseModel):
    version: int
    current: bool
    status: str = Field(description="approved or rejected by the quality gate (approved for Phase 8 models).")
    algorithm: str
    trained_at: str
    test_roc_auc: float | None
    accuracy: float | None


class ModelStatusResponse(BaseModel):
    current_version: int | None
    versions: list[ModelVersionOut] = Field(description="Every saved version, newest first.")
    recent_runs: list[dict[str, Any]] = Field(description="The latest retraining runs, newest first.")
    quality_gate: dict[str, float | int]
    mlflow: dict[str, Any]
    admin_actions_enabled: bool = Field(description="False until ADMIN_API_KEY is set.")
