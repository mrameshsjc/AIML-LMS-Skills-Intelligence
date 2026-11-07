"""
Health-check endpoint: GET /api/v1/health

PURPOSE
    Answer one question: "Is the service up and which version is running?"

WHO USES IT
    - You, in Swagger UI, to confirm the server started.
    - Docker / Docker Compose HEALTHCHECK, to mark the container healthy.
    - Kubernetes readiness/liveness probes (Phase 20).
    - The GitHub Actions smoke test after a deployment.

WHY A SEPARATE ROUTER FILE
    Each group of endpoints gets its own file (health.py now; skills.py,
    roles.py, trainings.py ... in later phases). main.py only plugs them in.
    This keeps files small and lets each be tested on its own.

INPUT
    None.
OUTPUT (HTTP 200)
    {
      "status": "ok",
      "app_name": "LMS Skills Intelligence Engine",
      "version": "0.1.0",
      "environment": "development",
      "profile": "local",
      "timestamp": "2026-11-07T05:00:00.123456+00:00"
    }
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Shape of the health response.

    Declaring the response as a Pydantic model means:
      - FastAPI validates what we return (a typo in a field name is caught);
      - Swagger UI shows the exact fields and an example automatically.
    """

    status: str = Field(examples=["ok"], description="Always 'ok' when the service responds.")
    app_name: str = Field(examples=["LMS Skills Intelligence Engine"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    profile: str = Field(examples=["local"])
    timestamp: datetime = Field(description="Server time in UTC when the check ran.")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns 'ok' with the running version. Used by Docker, CI and monitoring.",
)
def health() -> HealthResponse:
    """Return the current health status.

    This check is deliberately cheap: it does not touch the database or the
    LLM, so it stays fast and never fails because of a slow dependency.
    Deeper checks (database, vector store, Ollama) will be added as a separate
    'readiness' endpoint when those components exist.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        profile=settings.app_profile,
        timestamp=datetime.now(UTC),
    )
