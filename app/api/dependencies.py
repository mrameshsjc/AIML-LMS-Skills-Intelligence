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
from app.services.skill_analysis import SkillAnalysisService


@lru_cache
def get_repository() -> LmsRepository:
    """The data source for every API request (folder from the DATA_DIR setting)."""
    return CsvLmsRepository(get_settings().data_dir)


RepositoryDep = Annotated[LmsRepository, Depends(get_repository)]


def get_skill_analysis_service(repository: RepositoryDep) -> SkillAnalysisService:
    return SkillAnalysisService(repository)


SkillAnalysisServiceDep = Annotated[SkillAnalysisService, Depends(get_skill_analysis_service)]
