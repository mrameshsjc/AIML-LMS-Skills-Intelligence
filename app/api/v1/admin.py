"""
Demo administration: POST /api/v1/admin/reset-demo   (administrators only, Phase 19)

PURPOSE
    The requirements ask for "a reset mechanism for demo data". After visitors
    and administrators have uploaded documents or retrained models, this puts
    the public demo back to its starting state:
        uploaded documents, model versions, the database and the index are
        removed and rebuilt from the synthetic sample (app/core/prepare.py).
    Accounts and the audit log are kept, so the reset itself stays on record.

    The same reset: dashboard (Model management page, admins) or
        python -m app.core.prepare --reset

ERRORS (shared format)
    401 ADMIN_AUTH_REQUIRED    403 ADMIN_ONLY / ADMIN_ACTIONS_DISABLED    429 RATE_LIMITED
"""

import threading

from fastapi import APIRouter

from app.api import dependencies
from app.api.dependencies import AdminDep
from app.core.config import get_settings
from app.core.errors import ConflictError
from app.core.prepare import reset_demo
from app.schemas.admin import ResetDemoResponse
from app.schemas.common import ADMIN_RESPONSES, ErrorResponse

router = APIRouter(prefix="/admin", tags=["8. Demo administration"])
_LOCK = threading.Lock()


def clear_caches() -> None:
    """Everything the API loaded from the old data: reload on the next request."""
    dependencies.get_repository.cache_clear()
    dependencies._role_matching_service.cache_clear()
    dependencies.get_completion_predictor.cache_clear()
    dependencies.get_knowledge_index.cache_clear()


@router.post(
    "/reset-demo",
    response_model=ResetDemoResponse,
    summary="Reset the demo data to its starting state (administrators only)",
    description=(
        "Removes uploaded documents, model versions, the database and the document index, then rebuilds "
        "them from the synthetic sample data. Accounts and the audit log are kept."
    ),
    responses={
        **ADMIN_RESPONSES,
        409: {"model": ErrorResponse, "description": "A reset is already running"},
    },
)
def reset(who: AdminDep) -> ResetDemoResponse:
    if not _LOCK.acquire(blocking=False):
        raise ConflictError("RESET_IN_PROGRESS", "A reset is already running; try again in a minute.")
    try:
        steps = reset_demo(get_settings())
        clear_caches()
    finally:
        _LOCK.release()
    return ResetDemoResponse(status="reset", requested_by=who, steps=steps)
