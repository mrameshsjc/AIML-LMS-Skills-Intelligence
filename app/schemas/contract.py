"""
The API contract: what each business endpoint accepts and returns (Phase 14).

WHY
    The seven endpoints are a promise to their clients: the Streamlit
    dashboard now, and the PHP/F3 LMS backend in the integration project.
    Renaming a field, making an optional field required or removing a value
    from an allowed list would break those clients silently.

HOW
    ENDPOINTS lists every business endpoint with its request and response
    models (and query/form parameters). contract() turns them into a plain
    JSON structure - fields, types, required fields, allowed values, patterns,
    limits - WITHOUT descriptions and examples, so improving the documentation
    never counts as a contract change.

    docs/api_contract.json is the saved snapshot. A test compares it with the
    code (tests/integration/test_contract.py). For an INTENDED change:
        PS> python scripts/update_api_contract.py
    and review the diff in Git: it shows exactly what clients will notice.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import ErrorResponse
from app.schemas.learning_path import LearningPathResponse
from app.schemas.ml import ModelStatusResponse, RetrainRequest, RetrainResponse
from app.schemas.rag import DocumentListResponse, IngestResponse
from app.schemas.roles import RoleMatchRequest, RoleMatchResponse
from app.schemas.skills import SkillAnalysisRequest, SkillAnalysisResponse
from app.schemas.trainings import TrainingRecommendationRequest, TrainingRecommendationResponse

# (api number or "-", method, path, request model, response model, other parameters)
ENDPOINTS: list[tuple[str, str, str, type[BaseModel] | None, type[BaseModel], list[dict]]] = [
    ("1", "POST", "/api/v1/skills/analyze", SkillAnalysisRequest, SkillAnalysisResponse, []),
    ("2", "POST", "/api/v1/roles/match", RoleMatchRequest, RoleMatchResponse, []),
    (
        "3",
        "POST",
        "/api/v1/trainings/recommend",
        TrainingRecommendationRequest,
        TrainingRecommendationResponse,
        [],
    ),
    (
        "4",
        "GET",
        "/api/v1/learning-path/{employee_id}",
        None,
        LearningPathResponse,
        [
            {"name": "employee_id", "in": "path", "required": True},
            {"name": "target_role_id", "in": "query", "required": False},
            {"name": "include_optional", "in": "query", "required": False},
            {"name": "explain", "in": "query", "required": False},
        ],
    ),
    ("5", "POST", "/api/v1/ai/chat", ChatRequest, ChatResponse, []),
    (
        "6",
        "POST",
        "/api/v1/ml/retrain",
        RetrainRequest,
        RetrainResponse,
        [{"name": "x-admin-key", "in": "header", "required": False}],
    ),
    ("-", "GET", "/api/v1/ml/status", None, ModelStatusResponse, []),
    (
        "7",
        "POST",
        "/api/v1/rag/ingest",
        None,
        IngestResponse,
        [
            {"name": "file", "in": "form", "required": True},
            {"name": "overwrite", "in": "form", "required": False},
        ],
    ),
    ("-", "GET", "/api/v1/rag/documents", None, DocumentListResponse, []),
    (
        "-",
        "DELETE",
        "/api/v1/rag/documents/{source}",
        None,
        IngestResponse,
        [{"name": "source", "in": "path", "required": True}],
    ),
]

DOCUMENTATION_KEYS = {"title", "description", "examples"}


def _strip(value: Any, field_names: bool = False) -> Any:
    """Remove documentation-only keys, recursively; keep everything clients depend on.

    field_names=True means the keys ARE field names (inside "properties" or "$defs"): a field
    called "title" or "description" (a course title, say) is part of the contract and stays.
    """
    if isinstance(value, dict):
        return {
            k: _strip(v, field_names=k in ("properties", "$defs") and not field_names)
            for k, v in sorted(value.items())
            if field_names or k not in DOCUMENTATION_KEYS
        }
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def contract() -> dict:
    """The current contract, ready to compare with docs/api_contract.json."""
    endpoints = {}
    for api, method, path, request, response, params in ENDPOINTS:
        endpoints[f"{method} {path}"] = {
            "api": api,
            "request": _strip(request.model_json_schema(mode="validation")) if request else None,
            "response": _strip(response.model_json_schema(mode="serialization")),
            "parameters": params,
        }
    return {
        "endpoints": endpoints,
        "error": _strip(ErrorResponse.model_json_schema(mode="serialization")),
    }
