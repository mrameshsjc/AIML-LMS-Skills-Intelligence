"""
Streamlit helpers shared by every page (Phase 15).

    setup_page(title, intro)   page config, title, and the sidebar status box
    employee_picker(repo)      the selected employee, remembered across pages
    role_picker(...)           a job-role select box
    safe(fn, ...)              run a service call and show an AppError as a red message
    current_user()             who is signed in (Phase 17); anonymous when login is off
    admin_page()               stop the page unless an administrator is signed in

LOGIN (Phase 17)
    With AUTH_ENABLED=true every page asks for a login in the sidebar (the same
    accounts as the API: scripts/create_user.py). Employees can pick only
    themselves, managers their team, administrators everyone; pages 1, 7 and 8
    are for administrators. With login off (local default) everything is open.

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
from app.security.access import can_view
from app.security.audit import AuditLog
from app.security.rate_limit import LIMITER, RateLimitedError
from app.security.users import Principal, UserStore
from dashboard.components import data

T = TypeVar("T")
DEFAULT_EMPLOYEE = "E1001"  # the worked example from the requirements


def setup_page(title: str, intro: str, icon: str = "🎓") -> None:
    st.set_page_config(page_title=f"{title} – LMS Skills Intelligence", page_icon=icon, layout="wide")
    st.title(title)
    st.caption(intro)
    _sidebar_status()
    _login_box()


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


def current_user() -> Principal | None:
    """The signed-in account; an anonymous local user when login is off; None if nobody signed in."""
    settings = get_settings()
    if not settings.auth_enabled:
        return Principal("anonymous", "anonymous", None, settings.rag_tenant, authenticated=False)
    return st.session_state.get("principal")


def audit(action: str, **details) -> None:
    """One line in the same audit log as the API (who did what from the dashboard)."""
    settings = get_settings()
    if not settings.audit_log_file:
        return
    user = current_user()
    try:
        AuditLog(settings.audit_log_file).write(
            source="dashboard", user=user.username if user else "anonymous", action=action, **details
        )
    except OSError:
        pass  # auditing must never break the page


def _login_box() -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        st.sidebar.caption("🔓 Login is off (AUTH_ENABLED=false): local mode, every page is open.")
        return
    store = UserStore(settings.users_file)
    principal = st.session_state.get("principal")
    if principal is not None:
        user = store.get(principal.username)
        if user is None or user.disabled:  # removed or disabled while signed in
            st.session_state.pop("principal", None)
            principal = None
    if principal is not None:
        linked = f", {principal.employee_id}" if principal.employee_id else ""
        st.sidebar.caption(f"🔐 Signed in as {principal.username} ({principal.role}{linked})")
        if st.sidebar.button("Log out"):
            audit("logout")
            st.session_state.clear()
            st.rerun()
        return
    with st.sidebar.form("login"):
        st.markdown("**Log in**")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        try:
            LIMITER.check("login", f"dashboard:{username}", 10, 60)
            user = store.authenticate(username, password)
        except RateLimitedError as error:
            st.sidebar.error(error.message)
            user = None
        else:
            if user is None or user.tenant != settings.rag_tenant:
                audit("login_failed", attempted=username[:64])
                st.sidebar.error("Wrong username or password.")
                user = None
        if user is not None:
            st.session_state["principal"] = Principal(user.username, user.role, user.employee_id, user.tenant)
            st.session_state.pop("employee_id", None)
            audit("login", role=user.role)
            st.rerun()
    st.info("Please log in (sidebar) to use the dashboard. Accounts are created with scripts/create_user.py.")
    st.stop()


def admin_page() -> None:
    """Administrators only (data upload, documents, model management)."""
    user = current_user()
    if user is None or not user.authenticated:
        st.info(
            "Administrator page. Login is switched off (local mode), so it is open; "
            "with AUTH_ENABLED=true only administrators can open it.",
            icon="🔒",
        )
    elif not user.is_admin:
        st.error(f"Administrators only. You are signed in as {user.username} ({user.role}).", icon="🔒")
        st.stop()


def repository() -> LmsRepository:
    return get_repository()


def employee_picker(repo: LmsRepository, where=None) -> str:
    """Select an employee; the choice is kept in session_state so every page starts with it."""
    user = current_user()
    choices = {
        label: employee_id
        for label, employee_id in data.employee_choices(repo).items()
        if user is not None and can_view(user, employee_id, repo)  # Phase 17: own / team only
    }
    if not choices:
        st.error("This account is not linked to an employee you may view.")
        st.stop()
    labels, ids = list(choices), list(choices.values())
    default = user.employee_id if user and user.employee_id else DEFAULT_EMPLOYEE
    current = st.session_state.get("employee_id", default)
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
