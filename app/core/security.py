"""
Administrator check for protected actions (Phase 16).

WHY NOW
    API 6 retrains the model the whole engine relies on. The requirements say:
    "Protect this endpoint with administrator authentication. Do not allow
    normal users to trigger retraining." Phase 17 adds full login with user
    and admin roles; until then, an ADMINISTRATOR KEY protects admin actions.

HOW
    The administrator sends the key in the header  X-Admin-Key: <key>.
    The server compares it with ADMIN_API_KEY from .env.
      - ADMIN_API_KEY not set      -> 403: admin actions are switched off (safe default)
      - header missing or wrong    -> 401
    hmac.compare_digest compares in constant time, so the response time does not
    reveal how many characters of a guess were right.

KEEP THE KEY SECRET
    Put it only in .env (git-ignored), never in code or Git. Generate one with:
        python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

from __future__ import annotations

import hmac

from app.core.errors import ForbiddenError, UnauthorizedError


def check_admin_key(provided: str | None, configured: str) -> str:
    """Raise unless provided matches the configured admin key. Returns who is acting (for the audit trail)."""
    if not configured:
        raise ForbiddenError(
            "ADMIN_ACTIONS_DISABLED",
            "Administrator actions are switched off: set ADMIN_API_KEY in .env and restart the server.",
        )
    if not provided or not hmac.compare_digest(provided.encode(), configured.encode()):
        raise UnauthorizedError(
            "ADMIN_AUTH_REQUIRED", "A valid administrator key is required (header X-Admin-Key)."
        )
    return "admin"
