"""
The API's security checks, called directly (Phase 17): get_current_user,
require_admin and the chat rate limit. The full HTTP behaviour is tested in
tests/api/test_auth_api.py.
"""

from types import SimpleNamespace

import pytest

from app.api import dependencies as deps
from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.security.rate_limit import RateLimitedError
from app.security.tokens import create_token
from app.security.users import UserStore
from tests.conftest import TEST_ADMIN_KEY

SECRET = "s" * 48


def fake_request():
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), state=SimpleNamespace())


@pytest.fixture
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SECRET_KEY", SECRET)
    monkeypatch.setenv("USERS_FILE", str(tmp_path / "users.json"))
    get_settings.cache_clear()
    store = UserStore(tmp_path / "users.json")
    store.save("asha", "employee-pass-1", "employee", "E1001")
    store.save("root", "admin-pass-123", "admin")
    yield store
    monkeypatch.undo()
    get_settings.cache_clear()


def token_for(store, username):
    return create_token(store.get(username), SECRET, 30)[0]


def test_open_local_mode_gives_an_anonymous_user():
    request = fake_request()
    principal = deps.get_current_user(request, None)
    assert not principal.authenticated and principal.role == "anonymous"
    assert request.state.user == "anonymous"


def test_login_required_when_auth_is_on(auth_on):
    with pytest.raises(UnauthorizedError) as error:
        deps.get_current_user(fake_request(), None)
    assert error.value.code == "AUTH_REQUIRED"


def test_valid_token_identifies_the_user(auth_on):
    request = fake_request()
    principal = deps.get_current_user(request, token_for(auth_on, "asha"))
    assert (principal.username, principal.employee_id) == ("asha", "E1001")
    assert (request.state.user, request.state.role) == ("asha", "employee")


def test_token_of_a_deleted_account_stops_working(auth_on):
    token = token_for(auth_on, "asha")
    auth_on.path.write_text('{"users": []}')
    with pytest.raises(UnauthorizedError) as error:
        deps.get_current_user(fake_request(), token)
    assert error.value.code == "ACCOUNT_DISABLED"


def test_admin_key_works_in_both_modes(auth_on):
    assert deps.require_admin(fake_request(), None, TEST_ADMIN_KEY) == "admin"
    with pytest.raises(UnauthorizedError):
        deps.require_admin(fake_request(), None, "wrong")


def test_admin_login_is_accepted_but_not_an_employee(auth_on):
    assert deps.require_admin(fake_request(), token_for(auth_on, "root"), None) == "root"
    with pytest.raises(ForbiddenError) as error:
        deps.require_admin(fake_request(), token_for(auth_on, "asha"), None)
    assert error.value.code == "ADMIN_ONLY"
    with pytest.raises(UnauthorizedError) as error:
        deps.require_admin(fake_request(), None, None)
    assert error.value.code == "ADMIN_AUTH_REQUIRED"


def test_admin_actions_off_without_key_and_login(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ForbiddenError) as error:
            deps.require_admin(fake_request(), None, None)
        assert error.value.code == "ADMIN_ACTIONS_DISABLED"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_admin_attempts_are_rate_limited(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ADMIN_PER_HOUR", "3")
    get_settings.cache_clear()
    try:
        for _ in range(3):
            with pytest.raises(UnauthorizedError):
                deps.require_admin(fake_request(), None, "guess")
        with pytest.raises(RateLimitedError):  # guessing the key is slowed down too
            deps.require_admin(fake_request(), None, TEST_ADMIN_KEY)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_chat_has_its_own_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        anonymous = deps.get_current_user(fake_request(), None)
        deps.limit_chat(fake_request(), anonymous)
        deps.limit_chat(fake_request(), anonymous)
        with pytest.raises(RateLimitedError):
            deps.limit_chat(fake_request(), anonymous)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_unsafe_settings_are_reported(monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "public-demo")
    get_settings.cache_clear()
    try:
        assert any("AUTH_ENABLED" in p for p in get_settings().check_security())
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH_SECRET_KEY", "short")
        get_settings.cache_clear()
        assert any("32 characters" in p for p in get_settings().check_security())
        monkeypatch.setenv("AUTH_SECRET_KEY", SECRET)
        get_settings.cache_clear()
        assert get_settings().check_security() == []
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
