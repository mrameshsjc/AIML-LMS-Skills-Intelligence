"""
Streamlit helpers shared by every page (Phase 15).

    setup_page(title, intro)   page config, title, and the sidebar status box
    employee_picker(repo)      the selected employee, remembered across pages
    role_picker(...)           a job-role select box
    safe(fn, ...)              run a service call and show an AppError as a red message

Services come from app.api.dependencies, the same wiring the API uses, so the
dashboard and Swagger always show the same numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import streamlit as st

from app.api.dependencies import get_llm_provider, get_repository
from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories.base import LmsRepository
from dashboard.components import data

T = TypeVar("T")
DEFAULT_EMPLOYEE = "E1001"  # the worked example from the requirements


def setup_page(title: str, intro: str, icon: str = "🎓") -> None:
    st.set_page_config(page_title=f"{title} – LMS Skills Intelligence", page_icon=icon, layout="wide")
    st.title(title)
    st.caption(intro)
    _sidebar_status()


@st.cache_data(ttl=60, show_spinner=False)
def _llm_status() -> tuple[str, bool, str]:
    status = get_llm_provider().status()
    return status.provider, status.available, status.detail


def _sidebar_status() -> None:
    settings = get_settings()
    with st.sidebar:
        st.markdown("**LMS Skills Intelligence Engine**")
        st.caption(f"Version {settings.app_version} · synthetic data only")
        provider, _, detail = _llm_status()
        llm = "Ollama " + settings.ollama_model if provider == "ollama" else "fallback (no LLM)"
        st.caption(f"Data: {settings.data_source} · LLM: {llm}")
        if provider != "ollama":
            st.caption(f"ⓘ {detail[:140]}")


def repository() -> LmsRepository:
    return get_repository()


def employee_picker(repo: LmsRepository, where=None) -> str:
    """Select an employee; the choice is kept in session_state so every page starts with it."""
    choices = data.employee_choices(repo)
    labels, ids = list(choices), list(choices.values())
    current = st.session_state.get("employee_id", DEFAULT_EMPLOYEE)
    index = ids.index(current) if current in ids else 0
    label = (where or st.sidebar).selectbox("Employee", labels, index=index)
    st.session_state["employee_id"] = choices[label]
    return choices[label]


def role_picker(repo: LmsRepository, label: str, default_role_id: str | None, where=None) -> str:
    choices = data.role_choices(repo)
    labels, ids = list(choices), list(choices.values())
    index = ids.index(default_role_id) if default_role_id in ids else 0
    return choices[(where or st).selectbox(label, labels, index=index)]


def safe(fn: Callable[..., T], *args, **kwargs) -> T | None:
    """Call a service; show its AppError (e.g. 'Employee E9999 does not exist.') instead of a crash."""
    try:
        return fn(*args, **kwargs)
    except AppError as error:
        st.error(f"{error.message} ({error.code})")
        return None


def admin_notice() -> None:
    st.info(
        "Administrator page. In this phase every page is open; Phase 17 adds login and limits this page "
        "to administrators.",
        icon="🔒",
    )
