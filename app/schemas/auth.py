"""Response shapes for login (POST /api/v1/auth/token) and GET /api/v1/auth/me (Phase 17)."""

from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str = Field(description="Send it as the header: Authorization: Bearer <access_token>.")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires; then log in again.")
    role: Literal["employee", "manager", "admin"]
    employee_id: str | None = Field(description="The employee this account belongs to (none for admins).")


class MeResponse(BaseModel):
    username: str
    role: str = Field(
        description="employee, manager, admin - anonymous when login is off, guest in the public demo."
    )
    employee_id: str | None
    tenant: str
    authenticated: bool = Field(description="False when AUTH_ENABLED=false (local development).")
    can_view: Literal["everyone", "team", "self", "nobody"] = Field(
        description="Whose data this account may see in APIs 1-5."
    )
    auth_enabled: bool
