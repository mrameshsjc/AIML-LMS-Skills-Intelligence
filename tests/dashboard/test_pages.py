"""
Dashboard page tests with Streamlit's AppTest (Phase 15).

AppTest runs a page script headless - no browser - and lets the test read the
widgets and elements it produced, change inputs and run it again. Each test
uses temporary folders and the no-LLM fallback, so it never touches your
index, models or Ollama.

HOW TO RUN
    PS> pytest tests/dashboard -v
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from app.api import dependencies  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.rag.embeddings import TfidfEmbedder  # noqa: E402
from app.rag.index import build_index  # noqa: E402
from app.rag.vector_store import NumpyVectorStore  # noqa: E402

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"
PAGES = [DASHBOARD / "Home.py", *sorted((DASHBOARD / "pages").glob("*.py"))]
CACHES = [
    get_settings,
    dependencies.get_repository,
    dependencies.get_completion_predictor,
    dependencies.get_llm_provider,
    dependencies.get_knowledge_index,
]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for name, value in {
        "LLM_PROVIDER": "fallback",
        "USE_COMPLETION_MODEL": "false",
        "EMBEDDING_PROVIDER": "tfidf",
        "DATA_SOURCE": "csv",
        "VECTOR_STORE_DIR": str(tmp_path / "store"),
        "RAG_UPLOAD_DIR": str(tmp_path / "uploads"),
        "MODEL_DIR": str(tmp_path / "models"),
    }.items():
        monkeypatch.setenv(name, value)
    for cache in CACHES:
        cache.cache_clear()
    yield tmp_path
    for cache in CACHES:
        cache.cache_clear()


def run(page: str) -> AppTest:
    app = AppTest.from_file(str(DASHBOARD / page), default_timeout=120)
    app.run()
    assert not app.exception, app.exception
    return app


@pytest.mark.slow
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_runs_without_errors(page):
    run(str(page.relative_to(DASHBOARD)))


def _metric(app: AppTest, label: str) -> str:
    return next(m.value for m in app.metric if m.label == label)


def test_home_shows_the_totals():
    app = run("Home.py")
    assert _metric(app, "Employees") == "100" and _metric(app, "Job roles") == "13"
    assert _metric(app, "Completion rate") == "66.8 %"


def test_skills_analysis_for_e1001():
    app = run("pages/2_Skills_Analysis.py")
    assert app.sidebar.selectbox[0].value.startswith("E1001")
    assert _metric(app, "Gap score") == "37.5" and _metric(app, "Match") == "62.5 %"


def test_choosing_another_employee():
    app = run("pages/2_Skills_Analysis.py")
    option = next(o for o in app.sidebar.selectbox[0].options if o.startswith("E1003"))
    app.sidebar.selectbox[0].set_value(option).run()
    assert not app.exception and app.session_state["employee_id"] == "E1003"


def test_learning_path_next_action():
    app = run("pages/5_Learning_Path.py")
    assert "C-SQL-201" in app.success[0].value
    assert _metric(app, "Match after the path") == "100 %"


def test_assistant_answers_with_the_fallback():
    app = run("pages/6_AI_Assistant.py")
    app.chat_input[0].set_value("Which skills are required for an AI Engineer?").run()
    assert not app.exception
    assistant = [m for m in app.chat_message if m.name == "assistant"]
    assert assistant and "Prompt Engineering level 3" in assistant[-1].markdown[0].value


def test_documents_page_lists_the_index(isolated):
    build_index("documents", isolated / "store" / "default", TfidfEmbedder(), NumpyVectorStore)
    app = run("pages/7_Document_Management.py")
    assert _metric(app, "Index") == "Ready" and _metric(app, "Documents") == "8"


def test_model_page_without_a_model():
    app = run("pages/8_Model_Management.py")
    assert "No model has been trained yet" in app.info[-1].value
