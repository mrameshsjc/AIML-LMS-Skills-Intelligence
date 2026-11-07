"""
Application entry point: creates the FastAPI app.

PURPOSE
    Build the web application, plug in the API routers, and add the parts
    every request needs: request IDs, timing logs and a consistent error format.

HOW TO RUN (PowerShell, from the project folder, venv activated)
    PS> uvicorn app.main:app --reload
    Then open http://127.0.0.1:8000/docs  (Swagger UI)

    `app.main:app` means: in the file app/main.py, use the variable `app`.
    `--reload` restarts the server when you save a file (development only).

WHY FASTAPI
    - Generates Swagger UI (/docs) automatically from the code.
    - Validates requests and responses with Pydantic type hints.
    - Fast and widely used for ML/AI services in Python.
    Alternatives: Flask (simpler, but no built-in validation or docs) and
    Django (full web framework, far more than an API service needs).

WHY A `create_app()` FUNCTION ("application factory")
    Tests can create a fresh app with test settings, and later phases can add
    routers in one place. `app = create_app()` at the bottom is what uvicorn
    and Docker use.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import health, skills
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging_config import request_id_var, setup_logging

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
AI engine for an enterprise LMS: skills-gap analysis, job-role matching,
training recommendations, personalised learning paths and an LLM + RAG assistant.

| # | Endpoint | Status |
| --- | --- | --- |
| 1 | `POST /api/v1/skills/analyze` | **live** (Phase 5) |
| 2 | `POST /api/v1/roles/match` | Phase 6 |
| 3 | `POST /api/v1/trainings/recommend` | Phase 7 |
| 4 | `GET /api/v1/learning-path/{employee_id}` | Phase 10 |
| 5 | `POST /api/v1/ai/chat` | Phase 13 |
| 6 | `POST /api/v1/ml/retrain` | Phase 16 |
| 7 | `POST /api/v1/rag/ingest` | Phase 13 |

All data is synthetic. Try `POST /api/v1/skills/analyze` with
`{"employee_id": "E1001", "target_role_id": "R004"}`.
"""


def _error_body(code: str, message: str, request_id: str, details: object = None) -> dict:
    """Build the error format shared by every endpoint.

    One format for all errors means API clients (the dashboard now, the LMS
    later) need only one piece of code to show errors to users.
    """
    body: dict = {"error": {"code": code, "message": message, "request_id": request_id}}
    if details is not None:
        body["error"]["details"] = details
    return body


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        docs_url="/docs",  # Swagger UI
        redoc_url="/redoc",  # alternative read-only docs
    )

    # ------------------------------------------------------------------
    # Middleware: runs before and after EVERY request.
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def add_request_id_and_log(request: Request, call_next):
        """Give each request an ID, log its result and duration.

        If the caller already sent an `X-Request-ID` header (the LMS will do
        this later), we reuse it so one ID follows the request across systems.
        Otherwise we create a short random one.
        """
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()
        # Assume failure; overwritten when the endpoint returns normally.
        # If an unexpected error escapes, the generic handler returns a 500.
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # `finally` runs whether the request succeeded or failed, so every
            # request is logged exactly once with its status and duration.
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("%s %s -> %s (%.1f ms)", request.method, request.url.path, status, duration_ms)
            request_id_var.reset(token)

    # ------------------------------------------------------------------
    # Error handlers: turn every error into the same JSON format.
    # ------------------------------------------------------------------
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """Errors raised on purpose by services (unknown employee, unknown skill, ...)."""
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, getattr(request.state, "request_id", "-")),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        """Errors raised on purpose (404 not found, 403 forbidden, ...)."""
        code = {404: "NOT_FOUND", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, str(exc.detail), getattr(request.state, "request_id", "-")),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """The request body or parameters do not match the expected schema.

        `details` lists every problem field, so the caller can fix them all
        at once instead of one by one.
        """
        details = [{"field": ".".join(map(str, e["loc"])), "problem": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "VALIDATION_ERROR",
                "Request is not valid.",
                getattr(request.state, "request_id", "-"),
                details,
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        """Any bug we did not foresee.

        The full error goes to the log for developers; the caller gets a short,
        safe message without internal details (stack traces can leak secrets).
        """
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content=_error_body(
                "INTERNAL_ERROR", "Unexpected server error.", getattr(request.state, "request_id", "-")
            ),
        )

    # ------------------------------------------------------------------
    # Routers: each business area is plugged in here, under /api/v1.
    # Later phases add: skills, roles, trainings, learning_path, ai_chat,
    # ml_training and rag.
    # ------------------------------------------------------------------
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(skills.router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        """Friendly landing response pointing to the docs."""
        return {
            "message": f"{settings.app_name} is running.",
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    logger.info(
        "%s v%s started (env=%s, profile=%s)",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.app_profile,
    )
    return app


# The object uvicorn and Docker run: `uvicorn app.main:app`
app = create_app()
