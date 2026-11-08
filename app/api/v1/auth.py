"""
Login: POST /api/v1/auth/token  and  GET /api/v1/auth/me   (Phase 17)

HOW TO LOG IN
    1. Ask an administrator for an account (python scripts/create_user.py).
    2. POST /api/v1/auth/token as a form: username=...&password=...
       (in Swagger UI: the "Authorize" button does this for you)
    3. Send the returned token on every request:  Authorization: Bearer <token>

    With AUTH_ENABLED=false (the local default) there is nothing to log in to:
    every endpoint is open, and /auth/me says so.

WHY A FORM, NOT JSON
    OAuth2's "password flow" standard sends username and password as a form;
    following it is what makes Swagger UI's Authorize button work.

PROTECTION
    Wrong passwords get the same answer whether or not the user exists, and
    login attempts are rate limited per IP address (10 a minute).

ERRORS (shared format)
    401 INVALID_CREDENTIALS / AUTH_REQUIRED / INVALID_TOKEN / TOKEN_EXPIRED
    403 AUTH_DISABLED / WRONG_TENANT        429 RATE_LIMITED
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import CurrentUserDep, client_ip, get_user_store
from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.schemas.auth import MeResponse, TokenResponse
from app.schemas.common import ErrorResponse
from app.security.rate_limit import LIMITER
from app.security.tokens import create_token

router = APIRouter(prefix="/auth", tags=["0. Login"])
LOGIN_ATTEMPTS_PER_MINUTE = 10


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Log in: exchange a username and password for an access token",
    description=(
        "Send **username** and **password** as a form (OAuth2 password flow). The token is valid for "
        "AUTH_TOKEN_MINUTES. Only available when AUTH_ENABLED=true."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Wrong username or password"},
        403: {"model": ErrorResponse, "description": "Login switched off, or another organisation"},
        429: {"model": ErrorResponse, "description": "Too many login attempts"},
    },
)
def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    settings = get_settings()
    if not settings.auth_enabled:
        raise ForbiddenError(
            "AUTH_DISABLED", "Login is switched off (AUTH_ENABLED=false): this local server is open."
        )
    LIMITER.check("login", client_ip(request), LOGIN_ATTEMPTS_PER_MINUTE, 60)
    user = get_user_store().authenticate(form.username, form.password)
    request.state.user = form.username[:64]  # the audit log records who tried, never the password
    if user is None:
        raise UnauthorizedError("INVALID_CREDENTIALS", "Wrong username or password.")
    if user.tenant != settings.rag_tenant:
        raise ForbiddenError("WRONG_TENANT", "This account belongs to another organisation.")
    token, seconds = create_token(
        user, settings.auth_secret_key.get_secret_value(), settings.auth_token_minutes
    )
    request.state.role = user.role
    return TokenResponse(access_token=token, expires_in=seconds, role=user.role, employee_id=user.employee_id)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Who am I? The current account and what it may see",
    responses={401: {"model": ErrorResponse, "description": "Not logged in, or the token is not valid"}},
)
def me(principal: CurrentUserDep) -> MeResponse:
    if not principal.authenticated or principal.is_admin:  # local mode, guest (synthetic demo), admin
        scope = "everyone"
    elif principal.employee_id is None:
        scope = "nobody"
    else:
        scope = "team" if principal.role == "manager" else "self"
    return MeResponse(
        username=principal.username,
        role=principal.role,
        employee_id=principal.employee_id,
        tenant=principal.tenant,
        authenticated=principal.authenticated,
        can_view=scope,
        auth_enabled=get_settings().auth_enabled,
    )
