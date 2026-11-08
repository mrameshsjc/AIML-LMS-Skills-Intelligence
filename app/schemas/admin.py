"""Response shape for POST /api/v1/admin/reset-demo (Phase 19)."""

from pydantic import BaseModel, Field


class ResetDemoResponse(BaseModel):
    status: str = Field(description="reset")
    requested_by: str
    steps: list[str] = Field(description="What was removed and rebuilt, in order.")
