"""
Shared FastAPI dependencies: how routers get their services.

WHAT IS A DEPENDENCY?
    A function FastAPI calls for us before the endpoint runs, e.g.
        def analyze(..., service: SkillAnalysisServiceDep)
    The endpoint just receives a ready-made service. `Annotated[Type, Depends(f)]`
    is FastAPI's recommended way to say "a Type, provided by f".

WHY
    - One place decides WHERE data comes from: the CSV files or the SQLite
      database (DATA_SOURCE setting), and later the LMS database. Routers
      never construct it themselves.
    - Tests can swap in another repository:
        app.dependency_overrides[get_repository] = lambda: FakeRepository()
    - @lru_cache loads the data once, on the first request, and reuses it.

SECURITY (Phase 17)
    CurrentUserDep   who is calling: the logged-in user (JWT), or an anonymous
                     local user when AUTH_ENABLED=false (local development).
    AdminDep         administrators only: an admin login OR the X-Admin-Key header.
    ChatLimitDep     the stricter rate limit for the (slow, costly) assistant.
"""

from functools import lru_cache, partial
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import check_admin_key
from app.llm.base import LLMProvider
from app.llm.factory import build_provider
from app.ml.model_registry import MODEL_NAME
from app.ml.predict import CompletionPredictor
from app.ml.retraining import RetrainingService
from app.ml.tracking import choose_tracker
from app.rag.factory import choose_embedder, load_index, min_score, tenant_folder
from app.rag.index import KnowledgeIndex, read_manifest
from app.rag.vector_store import choose_backend
from app.repositories.base import LmsRepository
from app.repositories.csv_repository import CsvLmsRepository
from app.repositories.sqlite_repository import SqliteLmsRepository
from app.security.access import check_tenant
from app.security.rate_limit import LIMITER
from app.security.tokens import decode_token
from app.security.users import Principal, UserStore
from app.services.chat_service import ChatService
from app.services.explanation_service import ExplanationService
from app.services.ingestion_service import IngestionService
from app.services.learning_path import LearningPathService
from app.services.role_matching import RoleMatchingService
from app.services.skill_analysis import SkillAnalysisService
from app.services.training_recommendation import TrainingRecommendationService


@lru_cache
def get_repository() -> LmsRepository:
    """The data source for every API request: CSV files (DATA_DIR) or the database (DATABASE_URL)."""
    settings = get_settings()
    if settings.data_source == "database":
        return SqliteLmsRepository(settings.database_url)
    return CsvLmsRepository(settings.data_dir)


RepositoryDep = Annotated[LmsRepository, Depends(get_repository)]


def get_skill_analysis_service(repository: RepositoryDep) -> SkillAnalysisService:
    return SkillAnalysisService(repository)


SkillAnalysisServiceDep = Annotated[SkillAnalysisService, Depends(get_skill_analysis_service)]


@lru_cache
def _role_matching_service(repository: LmsRepository) -> RoleMatchingService:
    # Cached per repository: the role similarity index is built once, not on every request.
    return RoleMatchingService(repository)


def get_role_matching_service(repository: RepositoryDep) -> RoleMatchingService:
    return _role_matching_service(repository)


RoleMatchingServiceDep = Annotated[RoleMatchingService, Depends(get_role_matching_service)]


@lru_cache
def get_completion_predictor() -> CompletionPredictor | None:
    """The registered completion model, or None (no model trained, or switched off in settings).

    Loaded once. After training a new model, restart the server to pick it up.
    """
    settings = get_settings()
    if not settings.use_completion_model:
        return None
    if settings.data_source == "database":
        return CompletionPredictor.from_database(settings.model_dir, settings.database_url)
    return CompletionPredictor.from_files(settings.model_dir, settings.data_dir)


def get_training_recommendation_service(repository: RepositoryDep) -> TrainingRecommendationService:
    # With a trained model, completion_probability is filled in; without one, the
    # score is built from the other three parts (the response says so).
    return TrainingRecommendationService(repository, completion_model=get_completion_predictor())


TrainingRecommendationServiceDep = Annotated[
    TrainingRecommendationService, Depends(get_training_recommendation_service)
]


def get_learning_path_service(repository: RepositoryDep) -> LearningPathService:
    # Uses the same completion model as API 3, so the two APIs show the same scores.
    return LearningPathService(repository, completion_model=get_completion_predictor())


LearningPathServiceDep = Annotated[LearningPathService, Depends(get_learning_path_service)]


@lru_cache
def get_llm_provider() -> LLMProvider:
    """The language model chosen by LLM_PROVIDER (auto / ollama / fallback). Created once."""
    return build_provider(get_settings())


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_explanation_service(llm: LLMProviderDep) -> ExplanationService:
    return ExplanationService(None, llm)  # API 4 passes the path it has already built


ExplanationServiceDep = Annotated[ExplanationService, Depends(get_explanation_service)]


def get_index_manifest() -> dict | None:
    """What the knowledge index for RAG_TENANT contains (None if it has not been built)."""
    return read_manifest(tenant_folder(get_settings()))


@lru_cache
def get_knowledge_index() -> KnowledgeIndex | None:
    """The document index, loaded once (None if it has not been built yet).

    Uploads and deletions (API 7) clear this cache, so the next question uses the new index.
    After running scripts/build_index.py by hand, restart the server.
    """
    settings = get_settings()
    if read_manifest(tenant_folder(settings)) is None:
        return None
    return load_index(settings)


def get_chat_service(repository: RepositoryDep, llm: LLMProviderDep) -> ChatService:
    settings = get_settings()
    return ChatService(
        repository,
        llm,
        index_loader=get_knowledge_index,
        min_score=partial(min_score, settings),
        top_k=settings.rag_top_k,
        completion_model=get_completion_predictor(),
        block_injection=settings.block_prompt_injection,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_ingestion_service() -> IngestionService:
    settings = get_settings()
    return IngestionService(
        settings.documents_dir,
        settings.rag_upload_dir,
        tenant_folder(settings),
        choose_embedder=partial(choose_embedder, settings),
        backend=choose_backend(settings.vector_backend),
        chunk_size=settings.rag_chunk_size,
        overlap=settings.rag_chunk_overlap,
        max_bytes=int(settings.rag_max_upload_mb * 1024 * 1024),
        on_change=get_knowledge_index.cache_clear,
        block_injection=settings.block_prompt_injection,
    )


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]


def get_retraining_service() -> RetrainingService:
    settings = get_settings()
    return RetrainingService(
        settings.data_dir,
        settings.model_dir,
        tracker_factory=partial(
            choose_tracker,
            settings.mlflow_enabled,
            settings.mlflow_tracking_uri,
            settings.mlflow_experiment,
            MODEL_NAME,
        ),
        min_roc_auc=settings.ml_min_roc_auc,
        max_regression=settings.ml_max_regression,
        min_rows=settings.ml_min_training_rows,
    )


RetrainingServiceDep = Annotated[RetrainingService, Depends(get_retraining_service)]


# --- Security (Phase 17) ---------------------------------------------------------------------------
# auto_error=False: a missing token is not an error by itself - with login switched off, or for the
# X-Admin-Key route, there is none. tokenUrl lets the Swagger UI "Authorize" button log in.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
TokenDep = Annotated[str | None, Depends(oauth2_scheme)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def get_user_store() -> UserStore:
    return UserStore(get_settings().users_file)


def _principal_from_token(token: str) -> Principal:
    """Check the token's signature and expiry, its tenant, and that the account is still active."""
    settings = get_settings()
    principal = decode_token(token, settings.auth_secret_key.get_secret_value())
    check_tenant(principal, settings.rag_tenant)
    user = get_user_store().get(principal.username)
    if user is None or user.disabled:  # deleted or disabled after the token was issued
        raise UnauthorizedError("ACCOUNT_DISABLED", "This account no longer exists or is disabled.")
    return principal


def get_current_user(request: Request, token: TokenDep) -> Principal:
    """Who is calling. With AUTH_ENABLED=false, an anonymous local user who may view everyone."""
    settings = get_settings()
    if not settings.auth_enabled:
        principal = Principal("anonymous", "anonymous", None, settings.rag_tenant, authenticated=False)
    elif not token:
        raise UnauthorizedError(
            "AUTH_REQUIRED",
            "Log in first: POST /api/v1/auth/token, then send the header Authorization: Bearer <token>.",
        )
    else:
        principal = _principal_from_token(token)
    request.state.user, request.state.role = principal.username, principal.role  # for the audit log
    return principal


CurrentUserDep = Annotated[Principal, Depends(get_current_user)]


def require_admin(
    request: Request,
    token: TokenDep,
    x_admin_key: Annotated[
        str | None, Header(description="The administrator key (ADMIN_API_KEY), instead of an admin login.")
    ] = None,
) -> str:
    """Administrators only (retraining, document uploads and deletions). Returns who is acting.

    Accepted: the X-Admin-Key header (scripts, CI), or - with login switched on - an admin's token.
    Every attempt counts towards the admin rate limit, so neither the key nor tokens can be guessed fast.
    """
    settings = get_settings()
    LIMITER.check("admin", client_ip(request), settings.rate_limit_admin_per_hour, 3600)
    if x_admin_key is not None:
        who = check_admin_key(x_admin_key, settings.admin_api_key.get_secret_value())
    elif settings.auth_enabled and token:
        principal = _principal_from_token(token)
        if not principal.is_admin:
            raise ForbiddenError("ADMIN_ONLY", "Only administrators may do this.")
        who = principal.username
    elif settings.auth_enabled:
        raise UnauthorizedError(
            "ADMIN_AUTH_REQUIRED", "Log in as an administrator, or send the header X-Admin-Key."
        )
    else:
        who = check_admin_key(None, settings.admin_api_key.get_secret_value())  # 403 off, or 401
    request.state.user, request.state.role = who, "admin"
    return who


AdminDep = Annotated[str, Depends(require_admin)]


def limit_chat(request: Request, principal: CurrentUserDep) -> None:
    """The assistant calls a language model: a stricter per-user (or per-IP) limit than other APIs."""
    who = principal.username if principal.authenticated else client_ip(request)
    LIMITER.check("chat", who, get_settings().rate_limit_chat_per_minute, 60)


ChatLimitDep = Annotated[None, Depends(limit_chat)]
