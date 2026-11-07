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

from pydantic import Field
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

    # Where the API reads LMS data (Phase 9):
    #   csv       the CSV files in DATA_DIR (default; nothing to set up)
    #   database  the SQLite database at DATABASE_URL
    #             (create it first: python data_science/14_save_to_database.py)
    data_source: Literal["csv", "database"] = "csv"

    # --- Machine learning (Phase 8) ---------------------------------------------
    # Folder of the model registry, and whether API 3 should use the
    # completion model when one has been trained (python data_science/11_train_model.py).
    model_dir: str = "models"
    use_completion_model: bool = True

    # --- Language model (Phase 11) ----------------------------------------------
    # auto = Ollama when it is running, otherwise the no-LLM fallback (labelled).
    llm_provider: Literal["auto", "ollama", "fallback"] = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    llm_timeout_seconds: float = Field(default=120, gt=0, le=600)  # the first call loads the model: slow
    llm_temperature: float = Field(default=0.2, ge=0, le=2)  # low = factual and repeatable
    llm_max_tokens: int = Field(default=512, ge=16, le=4096)
    # Ollama must run on this machine (or the Compose network) unless an external host is approved.
    llm_allow_remote: bool = False

    # --- Knowledge documents and search (Phase 12) ---------------------------------
    documents_dir: str = "documents"  # the documents the assistant may use
    vector_store_dir: str = "vector_store"  # where indexes are saved (one folder per tenant)
    rag_tenant: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]+$")
    # auto = Ollama embeddings when the model is installed, else TF-IDF (no download).
    embedding_provider: Literal["auto", "ollama", "tfidf"] = "auto"
    ollama_embed_model: str = "nomic-embed-text"
    vector_backend: Literal["auto", "numpy", "faiss"] = "auto"  # auto = FAISS if installed
    rag_chunk_size: int = Field(default=800, ge=200, le=4000)  # characters per chunk
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_top_k: int = Field(default=4, ge=1, le=20)  # chunks returned per search
    # Phase 13: the assistant and document uploads
    rag_upload_dir: str = (
        "data/uploads/documents"  # uploaded documents (API 7); the approved folder stays read-only
    )
    rag_max_upload_mb: float = Field(default=10, gt=0, le=100)
    # Passages scoring below this are ignored. Empty = by embedder: TF-IDF 0.08, Ollama embeddings 0.45.
    rag_min_score: float | None = Field(default=None, ge=0, le=1)

    # --- Database (Phase 9) -------------------------------------------------
    # SQLite is a single file and needs no server, which is ideal for the
    # first local version. MySQL (e.g. mysql+pymysql://user:password@host/lms_ai)
    # is planned for a later phase; this version accepts sqlite:/// URLs only.
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
