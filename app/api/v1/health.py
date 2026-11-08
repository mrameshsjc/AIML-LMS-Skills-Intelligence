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
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import LLMProviderDep, get_index_manifest
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


class LlmStatusResponse(BaseModel):
    setting: str = Field(examples=["auto"], description="LLM_PROVIDER: auto, ollama or fallback.")
    provider: str = Field(
        examples=["ollama"], description="Who answers now: ollama, hosted, auto (= fallback) or fallback."
    )
    model: str = Field(examples=["llama3.2:3b"])
    available: bool = Field(description="True if requests needing the LLM can be answered.")
    detail: str = Field(description="Plain-language status, with the fix when something is missing.")
    models_installed: list[str] = Field(description="Models Ollama has installed (empty if unreachable).")


@router.get(
    "/health/llm",
    response_model=LlmStatusResponse,
    summary="Language model status",
    description=(
        "Is Ollama running, and is the configured model installed? Always answers 200; "
        "`available` and `detail` tell you what to fix. Kept separate from /health so Docker's "
        "health check never depends on the LLM."
    ),
)
def llm_status(llm: LLMProviderDep) -> LlmStatusResponse:
    status = llm.status()
    return LlmStatusResponse(
        setting=get_settings().llm_provider,
        provider=status.provider,
        model=status.model,
        available=status.available,
        detail=status.detail,
        models_installed=status.models_installed,
    )


class IndexedDocumentOut(BaseModel):
    source: str
    title: str
    pages: int
    chunks: int


class RagStatusResponse(BaseModel):
    ready: bool = Field(description="True if a knowledge index has been built for this tenant.")
    tenant: str
    detail: str
    embedder: str | None = Field(default=None, examples=["ollama"], description="ollama or tfidf.")
    embedding_model: str | None = Field(default=None, examples=["nomic-embed-text"])
    backend: str | None = Field(default=None, examples=["numpy"], description="numpy or faiss.")
    chunk_count: int = 0
    built_at: str | None = None
    documents: list[IndexedDocumentOut] = []


@router.get(
    "/health/rag",
    response_model=RagStatusResponse,
    summary="Knowledge index status",
    description=(
        "Which documents the AI assistant can search, and how the index was built. Always answers 200; "
        "build the index with `python scripts/build_index.py`."
    ),
)
def rag_status(manifest: Annotated[dict | None, Depends(get_index_manifest)]) -> RagStatusResponse:
    tenant = get_settings().rag_tenant
    if manifest is None:
        return RagStatusResponse(
            ready=False, tenant=tenant, detail="No index yet. Build it with: python scripts/build_index.py"
        )
    return RagStatusResponse(
        ready=True,
        tenant=tenant,
        detail=f"{len(manifest['documents'])} documents, {manifest['chunk_count']} chunks.",
        embedder=manifest["embedder"]["name"],
        embedding_model=manifest["embedder"]["model"],
        backend=manifest["backend"],
        chunk_count=manifest["chunk_count"],
        built_at=manifest["created_at"],
        documents=[
            IndexedDocumentOut(**{k: d[k] for k in ("source", "title", "pages", "chunks")})
            for d in manifest["documents"]
        ],
    )
