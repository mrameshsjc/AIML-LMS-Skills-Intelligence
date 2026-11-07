"""
Application configuration.

PURPOSE
    Keep every setting (app name, environment, log level, database URL, ...)
    in ONE place, loaded from environment variables or a `.env` file.

WHY THIS APPROACH
    - Settings are never hard-coded in the code, so the same code runs on your
      laptop, in Docker and later in production just by changing `.env`.
    - Secrets (passwords, tokens) stay out of Git: `.env` is git-ignored and
      only `.env.example` (with safe placeholder values) is committed.
    - `pydantic-settings` reads the variables AND validates their types.
      If someone writes `LOG_LEVEL=123`, the app fails at start-up with a clear
      message instead of failing later in a confusing way.

    Alternatives considered:
      * `os.getenv(...)` everywhere -> no validation, settings scattered.
      * a YAML/INI file -> works, but environment variables are the standard
        way Docker, Kubernetes and GitHub Actions pass configuration.

INPUT
    Environment variables (or `.env`), e.g. APP_ENV=development.
OUTPUT
    A `Settings` object. Use `get_settings()` to obtain it.

HOW TO TRY IT
    PS> python -c "from app.core.config import get_settings; print(get_settings())"
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings with safe defaults for local development.

    Each field name maps to an environment variable with the same name in
    UPPER CASE. Example: `app_env` is read from `APP_ENV`.
    """

    # `env_file=".env"` -> also read a local .env file if it exists.
    # `extra="ignore"`  -> unknown variables in .env do not crash the app.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    app_name: str = "LMS Skills Intelligence Engine"
    app_version: str = "0.1.0"

    # `Literal[...]` restricts the value to these options; anything else is
    # rejected at start-up with a validation error.
    app_env: Literal["development", "test", "production"] = "development"

    # Deployment profile from the blueprint: local laptop, Docker Compose,
    # or the public demo. Later phases change behaviour based on this.
    app_profile: Literal["local", "compose", "public-demo"] = "local"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- API ---------------------------------------------------------------
    # Every business endpoint will live under this prefix, e.g.
    # /api/v1/skills/analyze. Versioning lets us add /api/v2 later without
    # breaking existing clients (such as the future LMS integration).
    api_v1_prefix: str = "/api/v1"

    # --- Data (Phase 5) ------------------------------------------------------
    # Folder with the 11 LMS CSV files the API serves. data/sample is the
    # synthetic data; data/processed is the output of the cleaning script.
    data_dir: str = "data/sample"

    # --- Machine learning (Phase 8) ---------------------------------------------
    # Folder of the model registry, and whether API 3 should use the
    # completion model when one has been trained (python data_science/11_train_model.py).
    model_dir: str = "models"
    use_completion_model: bool = True

    # --- Database (used from Phase 9) --------------------------------------
    # SQLite is a single file and needs no server, which is ideal for the
    # first local version. Switching to MySQL later is only a URL change,
    # for example: mysql+pymysql://user:password@localhost:3306/lms_ai
    database_url: str = "sqlite:///./data/lms_ai.db"


@lru_cache
def get_settings() -> Settings:
    """Return the application settings.

    `@lru_cache` means the `.env` file is read only once; every later call
    returns the same object. This is faster and keeps settings consistent
    across the whole application.

    In tests we can call `get_settings.cache_clear()` to reload settings.
    """
    return Settings()
