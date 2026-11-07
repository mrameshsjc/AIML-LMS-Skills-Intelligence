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
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.factory import build_provider
from app.ml.predict import CompletionPredictor
from app.repositories.base import LmsRepository
from app.repositories.csv_repository import CsvLmsRepository
from app.repositories.sqlite_repository import SqliteLmsRepository
from app.services.explanation_service import ExplanationService
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
