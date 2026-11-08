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
    assert any("No model has been trained yet" in i.value for i in app.info)


# --- Login (Phase 17) ----------------------------------------------------------------------------------
@pytest.fixture
def login_on(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SECRET_KEY", "d" * 48)
    monkeypatch.setenv("USERS_FILE", str(tmp_path / "users.json"))
    get_settings.cache_clear()
    from app.security.users import UserStore

    store = UserStore(tmp_path / "users.json")
    store.save("asha", "employee-pass-1", "employee", "E1001")
    store.save("root", "admin-pass-123", "admin")
    return store


def run_as(page: str, principal) -> AppTest:
    app = AppTest.from_file(str(DASHBOARD / page), default_timeout=120)
    if principal is not None:
        app.session_state["principal"] = principal
    app.run()
    assert not app.exception, app.exception
    return app


def test_login_is_required_when_switched_on(login_on):
    app = run_as("Home.py", None)
    assert "Please log in" in app.info[-1].value and not app.metric


def test_logging_in_with_the_form(login_on):
    app = run_as("Home.py", None)
    app.sidebar.text_input[0].set_value("asha")
    app.sidebar.text_input[1].set_value("employee-pass-1")
    app.sidebar.button[0].click().run()
    assert not app.exception and app.session_state["principal"].username == "asha"
    assert _metric(app, "Employees") == "100"


def test_employee_can_pick_only_themselves(login_on):
    from app.security.users import Principal

    app = run_as("pages/2_Skills_Analysis.py", Principal("asha", "employee", "E1001"))
    options = app.sidebar.selectbox[0].options
    assert len(options) == 1 and options[0].startswith("E1001")


def test_admin_pages_refuse_employees(login_on):
    from app.security.users import Principal

    app = run_as("pages/8_Model_Management.py", Principal("asha", "employee", "E1001"))
    assert "Administrators only" in app.error[0].value
    admin = run_as("pages/7_Document_Management.py", Principal("root", "admin", None))
    assert not admin.error


# --- Public demo: guests (Phase 19) --------------------------------------------------------------------
@pytest.fixture
def guest_on(login_on, monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS", "true")
    get_settings.cache_clear()
    return login_on


def test_guest_browses_without_logging_in(guest_on):
    app = run_as("pages/2_Skills_Analysis.py", None)
    assert len(app.sidebar.selectbox[0].options) == 100  # every synthetic employee
    assert _metric(app, "Gap score") == "37.5"


def test_guest_sees_documents_but_not_the_upload(guest_on, isolated):
    build_index("documents", isolated / "store" / "default", TfidfEmbedder(), NumpyVectorStore)
    app = run_as("pages/7_Document_Management.py", None)
    assert _metric(app, "Documents") == "8"
    assert "Administrators only" in app.error[0].value
    assert "Delete" not in [b.label for b in app.button]  # only the sidebar's admin login button remains


def test_fallback_answers_are_labelled(guest_on):
    app = run_as("pages/6_AI_Assistant.py", None)
    app.chat_input[0].set_value("Which skills are required for an AI Engineer?").run()
    assert not app.exception
    assert any("Fallback mode" in i.value for i in app.info)


# --- Streamlit Community Cloud secrets (Phase 19 fix) -------------------------------------------------
CLOUD_SECRETS = {
    "APP_PROFILE": "public-demo",
    "AUTH_ENABLED": "true",
    "GUEST_ACCESS": "true",
    "AUTH_SECRET_KEY": "c" * 48,
    "BOOTSTRAP_ADMIN_PASSWORD": "long-enough-pass-1",
}


def test_streamlit_secrets_switch_on_the_public_demo(monkeypatch, tmp_path):
    # Secrets reach the engine only through environment variables; restore them after the test.
    local = {"APP_PROFILE": "local", "AUTH_ENABLED": "false", "GUEST_ACCESS": "false"}
    for key in CLOUD_SECRETS:
        monkeypatch.setenv(key, local.get(key, ""))  # valid local values until the secrets apply
    monkeypatch.setenv("USERS_FILE", str(tmp_path / "users.json"))
    get_settings.cache_clear()
    app = AppTest.from_file(str(DASHBOARD / "pages/1_Data_Upload.py"), default_timeout=120)
    for key, value in CLOUD_SECRETS.items():
        app.secrets[key] = value
    app.run()
    assert not app.exception, app.exception
    assert any("Guest" in c.value for c in app.sidebar.caption)  # login on, guest access
    assert "Administrators only" in app.error[0].value  # the admin page is closed to guests
    get_settings.cache_clear()
