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

from pydantic import Field, SecretStr, field_validator, model_validator
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
    # hosted = an OpenAI-compatible inference service (Phase 19, public demo), with the same fallback.
    llm_provider: Literal["auto", "ollama", "hosted", "fallback"] = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    llm_timeout_seconds: float = Field(default=120, gt=0, le=600)  # the first call loads the model: slow
    llm_temperature: float = Field(default=0.2, ge=0, le=2)  # low = factual and repeatable
    llm_max_tokens: int = Field(default=512, ge=16, le=4096)
    # Ollama must run on this machine (or the Compose network) unless an external host is approved.
    llm_allow_remote: bool = False
    # Hosted inference (Phase 19): any OpenAI-compatible /chat/completions service, e.g. the
    # Hugging Face router. Used ONLY with LLM_PROVIDER=hosted and LLM_ALLOW_REMOTE=true.
    hosted_llm_base_url: str = "https://router.huggingface.co/v1"
    hosted_llm_model: str = ""  # e.g. meta-llama/Llama-3.1-8B-Instruct (must be available on the service)
    hosted_llm_api_key: SecretStr = SecretStr("")  # a secret: Space secret / environment variable only

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

    # --- Administration and retraining (Phase 16) --------------------------------------
    # Key for admin actions (API 6), sent in the X-Admin-Key header. Empty = admin actions off.
    # SecretStr keeps it out of logs and error messages. Generate one:
    #   python -c "import secrets; print(secrets.token_urlsafe(32))"
    admin_api_key: SecretStr = SecretStr("")
    ml_min_roc_auc: float = Field(default=0.60, ge=0.5, le=1.0)  # quality gate: minimum test ROC AUC
    ml_max_regression: float = Field(default=0.01, ge=0, le=0.5)  # allowed drop vs the current model
    ml_min_training_rows: int = Field(default=200, ge=20)
    # MLflow: auto = used when installed. Empty URI = sqlite file mlruns/mlflow.db in the project.
    mlflow_enabled: Literal["auto", "true", "false"] = "auto"
    mlflow_tracking_uri: str = ""
    mlflow_experiment: str = "completion-model"

    # --- Security (Phase 17) --------------------------------------------------------
    # Login with roles. Off for local development; REQUIRED (enforced at start-up) when
    # APP_PROFILE=public-demo or APP_ENV=production.
    auth_enabled: bool = False
    auth_secret_key: SecretStr = SecretStr("")  # signs access tokens; at least 32 characters
    auth_token_minutes: int = Field(default=60, ge=5, le=24 * 60)
    users_file: str = "data/users.json"  # created by scripts/create_user.py (git-ignored)
    # Requests per minute per user (or IP address); 0 switches a limit off.
    rate_limit_per_minute: int = Field(default=120, ge=0)
    rate_limit_chat_per_minute: int = Field(default=20, ge=0)
    rate_limit_admin_per_hour: int = Field(default=10, ge=0)  # retraining and uploads
    audit_log_file: str = "logs/audit.jsonl"
    # Browser origins allowed to call the API (comma-separated), e.g. the LMS front end. Empty = none.
    cors_origins: str = ""
    block_prompt_injection: bool = True  # refuse questions/uploads that try to override the assistant's rules

    # --- Containers (Phase 18) ---
    # The container's start step (app/core/prepare.py) creates folders, the database (DATA_SOURCE=database)
    # and the document index if they are missing. Only ONE service should do it (the api); others set false.
    prepare_on_start: bool = True

    # --- Public demo (Phase 19) ---
    # guest_access: with login ON, visitors without an account browse the SYNTHETIC data read-only
    # (APIs 1-5, dashboard). Admin actions still need an admin login. Only for synthetic demo data.
    guest_access: bool = False
    # Creates this admin account at start-up if it does not exist (hosts whose disk resets on
    # restart, e.g. Hugging Face Spaces). The password comes from a secret, never from Git.
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr = SecretStr("")
    prepare_train_model: bool = False  # start step: train a first model if there is none (demo metrics)
    # Streamlit Community Cloud has no start command: the dashboard runs the start step itself, once
    # per process, when this is true (Phase 19). Off by default (Compose prepares in the api container).
    prepare_in_dashboard: bool = False
    # Sites allowed to show the app in a frame, e.g. https://huggingface.co (the Space page). Empty = none.
    frame_ancestors: str = ""

    # --- Database (Phase 9) -------------------------------------------------
    # SQLite is a single file and needs no server, which is ideal for the
    # first local version. MySQL (e.g. mysql+pymysql://user:password@host/lms_ai)
    # is planned for a later phase; this version accepts sqlite:/// URLs only.
    database_url: str = "sqlite:///./data/lms_ai.db"

    @model_validator(mode="before")
    @classmethod
    def _ignore_comment_only_values(cls, values):
        """A line like `KEY=   # note` in .env gives KEY the value "# note" (a .env rule).

        Older copies of .env.example had such lines. A value that is only a comment
        means "not set": the default is used instead of failing at start-up.
        """
        if isinstance(values, dict):
            return {
                k: v for k, v in values.items() if not (isinstance(v, str) and v.lstrip().startswith("#"))
            }
        return values

    @field_validator("rag_min_score", mode="before")
    @classmethod
    def _empty_means_default(cls, value):
        """RAG_MIN_SCORE= (empty, as in .env.example) means "choose by embedder", not an error."""
        return None if isinstance(value, str) and not value.strip() else value

    def check_security(self) -> list[str]:
        """Problems that must stop the server, plus warnings (returned as text, raised by main.py)."""
        problems = []
        exposed = self.app_profile == "public-demo" or self.app_env == "production"
        if exposed and not self.auth_enabled:
            problems.append("AUTH_ENABLED must be true for APP_PROFILE=public-demo or APP_ENV=production.")
        if self.auth_enabled and len(self.auth_secret_key.get_secret_value()) < 32:
            problems.append(
                "AUTH_SECRET_KEY must have at least 32 characters when AUTH_ENABLED=true "
                '(generate one: python -c "import secrets; print(secrets.token_urlsafe(48))").'
            )
        if self.guest_access and not self.auth_enabled:
            problems.append(
                "GUEST_ACCESS=true needs AUTH_ENABLED=true (otherwise every page is open anyway)."
            )
        password = self.bootstrap_admin_password.get_secret_value()
        if password and len(password) < 12:
            problems.append("BOOTSTRAP_ADMIN_PASSWORD must have at least 12 characters.")
        if self.llm_provider == "hosted" and not self.llm_allow_remote:
            problems.append(
                "LLM_PROVIDER=hosted sends prompts to an outside service: set LLM_ALLOW_REMOTE=true "
                "only if that is approved (synthetic demo data)."
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    """Return the application settings.

    `@lru_cache` means the `.env` file is read only once; every later call
    returns the same object. This is faster and keeps settings consistent
    across the whole application.

    In tests we can call `get_settings.cache_clear()` to reload settings.
    """
    return Settings()
