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

SECURITY (Phase 17) - added to every request by the middleware below
    - a global rate limit per IP address for /api/v1 (health checks excluded);
    - security headers (no MIME sniffing, no framing, no caching of personal data);
    - one audit-log line per API request (who, what, status - never bodies);
    - CORS only for the origins in CORS_ORIGINS (none by default);
    - the server refuses to start with unsafe settings (Settings.check_security),
      e.g. a public demo without login.

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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import (
    admin,
    ai_chat,
    auth,
    health,
    learning_path,
    ml_training,
    rag,
    roles,
    skills,
    trainings,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging_config import request_id_var, setup_logging
from app.security.audit import AuditLog
from app.security.rate_limit import LIMITER, RateLimitedError

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
AI engine for an enterprise LMS: skills-gap analysis, job-role matching,
training recommendations, personalised learning paths and an LLM + RAG assistant.

| # | Endpoint | Status |
| --- | --- | --- |
| 1 | `POST /api/v1/skills/analyze` | **live** (Phase 5) |
| 2 | `POST /api/v1/roles/match` | **live** (Phase 6) |
| 3 | `POST /api/v1/trainings/recommend` | **live** (Phase 7) |
| 4 | `GET /api/v1/learning-path/{employee_id}` | **live** (Phase 10) |
| 5 | `POST /api/v1/ai/chat` | **live** (Phase 13) |
| 6 | `POST /api/v1/ml/retrain` | **live** (Phase 16, administrators only) |
| 7 | `POST /api/v1/rag/ingest` | **live** (Phase 13, administrators only) |

**Login (Phase 17):** when the server runs with `AUTH_ENABLED=true`, use the **Authorize** button
(or `POST /api/v1/auth/token`). Employees see only their own data, managers their team, admins everyone.

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


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # the browser must not guess a file type (e.g. run JSON as script)
    "X-Frame-Options": "DENY",  # the API must not be shown inside another site's frame (clickjacking)
    "Referrer-Policy": "no-referrer",
}
API_ONLY_HEADERS = {  # JSON answers only: Swagger UI (/docs) needs scripts and styles from a CDN
    "Cache-Control": "no-store",  # answers can contain personal data: never keep them in a cache
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
NOT_RATE_LIMITED = ("/api/v1/health",)  # monitoring and Kubernetes probes call these all the time


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_startup_security(settings) -> None:
    """Refuse to start with unsafe settings; warn about the open local mode."""
    problems = settings.check_security()
    if problems:
        raise RuntimeError("Unsafe security settings:\n- " + "\n- ".join(problems))
    if not settings.auth_enabled:
        logger.warning(
            "Login is switched off (AUTH_ENABLED=false): every user can see every employee. "
            "Fine on your own PC with synthetic data; never for a shared or public server."
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.log_level)
    check_startup_security(settings)

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
        incoming = request.headers.get("X-Request-ID", "")[:64]  # capped: no huge log lines
        request_id = incoming or uuid.uuid4().hex[:8]
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()
        # Assume failure; overwritten when the endpoint returns normally.
        # If an unexpected error escapes, the generic handler returns a 500.
        status = 500
        current = get_settings()
        path = request.url.path
        is_api = path.startswith(current.api_v1_prefix)
        try:
            try:  # Phase 17: global rate limit per IP address (a middleware cannot use the error handlers)
                if is_api and not path.startswith(NOT_RATE_LIMITED):
                    LIMITER.check("api", _client_ip(request), current.rate_limit_per_minute, 60)
                response = await call_next(request)
            except RateLimitedError as error:
                response = JSONResponse(
                    status_code=429,
                    content=_error_body(error.code, error.message, request_id),
                    headers={"Retry-After": str(error.retry_after)},
                )
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers.update(SECURITY_HEADERS)
            if is_api:
                response.headers.update(API_ONLY_HEADERS)
            elif current.frame_ancestors:  # Phase 19: e.g. the Hugging Face page shows /docs in a frame
                del response.headers["X-Frame-Options"]
                response.headers["Content-Security-Policy"] = (
                    f"frame-ancestors 'self' {current.frame_ancestors}"
                )
            return response
        finally:
            # `finally` runs whether the request succeeded or failed, so every
            # request is logged exactly once with its status and duration.
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("%s %s -> %s (%.1f ms)", request.method, path, status, duration_ms)
            if is_api and current.audit_log_file and not path.startswith(NOT_RATE_LIMITED):
                try:  # who did what - never request bodies, passwords or tokens
                    AuditLog(current.audit_log_file).write(
                        request_id=request_id,
                        user=getattr(request.state, "user", "anonymous"),
                        role=getattr(request.state, "role", None),
                        method=request.method,
                        path=path,
                        status=status,
                        client=_client_ip(request),
                        ms=round(duration_ms, 1),
                    )
                except OSError:
                    logger.exception("Could not write the audit log")
            request_id_var.reset(token)

    # ------------------------------------------------------------------
    # Error handlers: turn every error into the same JSON format.
    # ------------------------------------------------------------------
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """Errors raised on purpose by services (unknown employee, unknown skill, ...)."""
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after)  # tells well-behaved clients when to come back
        elif exc.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"  # the HTTP standard for "log in with a token"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, getattr(request.state, "request_id", "-")),
            headers=headers,
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
    # ------------------------------------------------------------------
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(skills.router, prefix=settings.api_v1_prefix)
    app.include_router(roles.router, prefix=settings.api_v1_prefix)
    app.include_router(trainings.router, prefix=settings.api_v1_prefix)
    app.include_router(learning_path.router, prefix=settings.api_v1_prefix)
    app.include_router(ai_chat.router, prefix=settings.api_v1_prefix)
    app.include_router(rag.router, prefix=settings.api_v1_prefix)
    app.include_router(ml_training.router, prefix=settings.api_v1_prefix)
    app.include_router(admin.router, prefix=settings.api_v1_prefix)

    # CORS: which OTHER websites may call this API from a browser. None by default; the LMS
    # front end's address goes in CORS_ORIGINS (comma-separated) in the integration project.
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Admin-Key"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        """Friendly landing response pointing to the docs."""
        return {
            "message": f"{settings.app_name} is running.",
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    logger.info(
        "%s v%s started (env=%s, profile=%s, login=%s)",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.app_profile,
        "on" if settings.auth_enabled else "off",
    )
    return app


# The object uvicorn and Docker run: `uvicorn app.main:app`
app = create_app()
