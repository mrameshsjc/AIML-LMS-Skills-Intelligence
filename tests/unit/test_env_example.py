"""
.env.example is copied to .env by every new user (and by Docker Compose's env_file):
it must load without errors and must not hide surprises.
"""

from pathlib import Path

from dotenv import dotenv_values

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
VALUES = dotenv_values(ROOT / ".env.example")


def test_no_value_is_actually_a_comment():
    # "KEY=   # note" makes the VALUE "# note": comments of empty values go on their own line.
    bad = {k: v for k, v in VALUES.items() if v and v.lstrip().startswith("#")}
    assert bad == {}


def test_no_secret_has_a_value():
    for key in ("ADMIN_API_KEY", "AUTH_SECRET_KEY"):
        assert VALUES.get(key, "") == "", key


def test_settings_load_from_the_example(monkeypatch):
    for key in VALUES:  # the example's values must win over anything set in this shell
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=ROOT / ".env.example")
    assert settings.rag_min_score is None and settings.auth_enabled is False


def test_empty_min_score_means_choose_by_embedder():
    assert Settings(rag_min_score="").rag_min_score is None
    assert Settings(rag_min_score="0.3").rag_min_score == 0.3


def test_a_comment_left_as_a_value_falls_back_to_the_default(tmp_path, monkeypatch):
    # what an older .env (copied before the fix) contains
    old = tmp_path / ".env"
    old.write_text(
        "RAG_MIN_SCORE=                 # empty = by embedder (TF-IDF 0.08, Ollama 0.45)\n"
        "MLFLOW_TRACKING_URI=           # empty = sqlite file mlruns/mlflow.db\n"
        "CORS_ORIGINS=                    # browser sites allowed\n",
        encoding="utf-8",
    )
    for key in ("RAG_MIN_SCORE", "MLFLOW_TRACKING_URI", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=old)
    assert settings.rag_min_score is None
    assert settings.mlflow_tracking_uri == "" and settings.cors_origins == ""
