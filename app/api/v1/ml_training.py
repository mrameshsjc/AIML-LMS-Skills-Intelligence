"""
API 6 - ML Model Retraining: POST /api/v1/ml/retrain   (administrators only)
plus GET /api/v1/ml/status (open: model versions and metrics, no personal data)

PURPOSE
    Run the controlled retraining workflow (app/ml/retraining.py): validate the
    data, train, evaluate, compare with the current model, apply the quality
    gate, register the version (and in MLflow), and promote it only if approved.

ADMIN ONLY
    Send the administrator key:  X-Admin-Key: <ADMIN_API_KEY from .env>
    Without ADMIN_API_KEY set on the server, retraining is switched off (403).

AFTER A PROMOTION
    The API loads the new model at once (the cached model is cleared): no restart.

ERRORS (shared format)
    401 ADMIN_AUTH_REQUIRED      403 ADMIN_ACTIONS_DISABLED
    409 RETRAINING_IN_PROGRESS   422 VALIDATION_ERROR
"""

from typing import Annotated

from fastapi import APIRouter, Header

from app.api.dependencies import RetrainingServiceDep, get_completion_predictor
from app.core.config import get_settings
from app.core.security import check_admin_key
from app.ml.model_registry import current_version, list_cards
from app.ml.retraining import PROMOTED, RetrainReport, read_history
from app.ml.tracking import default_tracking_uri, mlflow_installed
from app.schemas.common import ErrorResponse
from app.schemas.ml import (
    DataValidationOut,
    GateCheckOut,
    ModelStatusResponse,
    ModelVersionOut,
    RetrainRequest,
    RetrainResponse,
    TrainingOut,
)

router = APIRouter(prefix="/ml", tags=["6. ML Model Management"])


def to_response(r: RetrainReport) -> RetrainResponse:
    return RetrainResponse(
        status=r.status,
        gate_passed=r.gate_passed,
        previous_version=r.previous_version,
        new_version=r.new_version,
        current_version=r.current_version,
        requested_by=r.requested_by,
        reason=r.reason,
        started_at=r.started_at,
        data_validation=DataValidationOut(
            errors=r.data_errors, warnings=r.data_warnings, issues=r.data_issues
        ),
        training=TrainingOut(rows=r.rows, algorithm=r.algorithm, cross_validation=r.cross_validation),
        new_metrics=r.new_metrics,
        current_metrics=r.current_metrics,
        quality_gate=[GateCheckOut(name=c.name, passed=c.passed, detail=c.detail) for c in r.gate],
        mlflow=r.mlflow,
        duration_seconds=r.duration_seconds,
        notes=r.notes,
    )


@router.post(
    "/retrain",
    response_model=RetrainResponse,
    summary="Retrain the course-completion model (administrators only)",
    description=(
        "Validates the training data, builds features, compares three algorithms, and evaluates the "
        "best on unseen test rows. Compares it with the **current** model on the same rows and applies "
        "the **quality gate** (minimum ROC AUC, better than chance, no regression). Every run saves a "
        "new version; only an approved one becomes current. Runs are logged to MLflow when installed.\n\n"
        "Requires the header **X-Admin-Key**."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Missing or wrong administrator key"},
        403: {
            "model": ErrorResponse,
            "description": "Admin actions switched off (no ADMIN_API_KEY)",
        },
        409: {"model": ErrorResponse, "description": "Another retraining run is in progress"},
    },
)
def retrain(
    request: RetrainRequest,
    service: RetrainingServiceDep,
    x_admin_key: Annotated[str | None, Header(description="The administrator key (ADMIN_API_KEY).")] = None,
) -> RetrainResponse:
    who = check_admin_key(x_admin_key, get_settings().admin_api_key.get_secret_value())
    report = service.retrain(requested_by=who, reason=request.reason, promote=request.promote)
    if report.status == PROMOTED:
        get_completion_predictor.cache_clear()  # API 3 uses the new model from the next request
    return to_response(report)


@router.get(
    "/status",
    response_model=ModelStatusResponse,
    summary="Model versions, metrics and retraining history",
    description="The current model, every saved version with its gate status, the latest retraining runs.",
)
def model_status() -> ModelStatusResponse:
    settings = get_settings()
    current = current_version(settings.model_dir)
    versions = [
        ModelVersionOut(
            version=c["version"],
            current=c["version"] == current,
            status=c.get("status", "approved"),
            algorithm=c.get("algorithm", ""),
            trained_at=c.get("trained_at", ""),
            test_roc_auc=c.get("test_metrics", {}).get("roc_auc"),
            accuracy=c.get("test_metrics", {}).get("accuracy"),
        )
        for c in reversed(list_cards(settings.model_dir))
    ]
    return ModelStatusResponse(
        current_version=current,
        versions=versions,
        recent_runs=read_history(settings.model_dir),
        quality_gate={
            "min_roc_auc": settings.ml_min_roc_auc,
            "max_regression": settings.ml_max_regression,
            "min_training_rows": settings.ml_min_training_rows,
        },
        mlflow={
            "setting": settings.mlflow_enabled,
            "installed": mlflow_installed(),
            "tracking_uri": settings.mlflow_tracking_uri or default_tracking_uri(),
        },
        admin_actions_enabled=bool(settings.admin_api_key.get_secret_value()),
    )
