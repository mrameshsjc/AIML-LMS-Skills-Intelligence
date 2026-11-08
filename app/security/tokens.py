"""
Access tokens (JWT) (Phase 17).

HOW LOGIN WORKS
    1. POST /api/v1/auth/token with username + password.
    2. The server checks the password and returns a signed ACCESS TOKEN.
    3. Every later request sends it:  Authorization: Bearer <token>
    The server checks the signature and the expiry time - no database lookup,
    no session to store.

WHAT IS A JWT?
    A JSON Web Token: three base64 parts, header.payload.signature. The payload
    says who the user is (sub, role, employee_id, tenant) and when the token
    expires (exp). The signature (HMAC-SHA256 with AUTH_SECRET_KEY) proves the
    server issued it: changing "role": "employee" to "admin" breaks the
    signature, and the token is refused.

    The payload is only ENCODED, not encrypted - anyone can read it - so it
    never contains a password or personal data. Tokens must travel over HTTPS
    outside localhost (Phase 19).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.core.errors import UnauthorizedError
from app.security.users import Principal, User

ALGORITHM = "HS256"


def create_token(user: User, secret: str, minutes: int) -> tuple[str, int]:
    """A signed token for the user, and its lifetime in seconds."""
    now = datetime.now(UTC)
    payload = {
        "sub": user.username,
        "role": user.role,
        "employee_id": user.employee_id,
        "tenant": user.tenant,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM), minutes * 60


def decode_token(token: str, secret: str) -> Principal:
    try:
        claims = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "role"]}
        )
    except jwt.ExpiredSignatureError as error:
        raise UnauthorizedError("TOKEN_EXPIRED", "The access token has expired: log in again.") from error
    except jwt.InvalidTokenError as error:
        raise UnauthorizedError("INVALID_TOKEN", "The access token is not valid.") from error
    return Principal(
        claims["sub"], claims["role"], claims.get("employee_id"), claims.get("tenant", "default")
    )
