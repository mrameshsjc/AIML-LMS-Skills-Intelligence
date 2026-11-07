"""
Shared FastAPI dependencies: how routers get their services.

WHAT IS A DEPENDENCY?
    A function FastAPI calls for us before the endpoint runs, e.g.
        def analyze(..., service: SkillAnalysisServiceDep)
    The endpoint just receives a ready-made service. `Annotated[Type, Depends(f)]`
    is FastAPI's recommended way to say "a Type, provided by f".

WHY
    - One place decides WHERE data comes from (the CSV repository today,
      the LMS database later). Routers never construct it themselves.
    - Tests can swap in another repository:
        app.dependency_overrides[get_repository] = lambda: FakeRepository()
    - @lru_cache loads the data once, on the first request, and reuses it.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.repositories.base import LmsRepository
from app.repositories.csv_repository import CsvLmsRepository
from app.services.role_matching import RoleMatchingService
from app.services.skill_analysis import SkillAnalysisService
from app.services.training_recommendation import TrainingRecommendationService


@lru_cache
def get_repository() -> LmsRepository:
    """The data source for every API request (folder from the DATA_DIR setting)."""
    return CsvLmsRepository(get_settings().data_dir)


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


def get_training_recommendation_service(repository: RepositoryDep) -> TrainingRecommendationService:
    # completion_model is added in Phase 8; until then the score uses the other three parts.
    return TrainingRecommendationService(repository)


TrainingRecommendationServiceDep = Annotated[
    TrainingRecommendationService, Depends(get_training_recommendation_service)
]
