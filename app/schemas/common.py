"""Shapes shared by every endpoint: the error format and small references."""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(examples=["EMPLOYEE_NOT_FOUND"], description="Stable code a program can check.")
    message: str = Field(examples=["Employee E9999 does not exist."], description="Text to show a person.")
    request_id: str = Field(examples=["3f2a9c1e"], description="Find this request in the server logs.")


class ErrorResponse(BaseModel):
    """Every error from this API has this shape."""

    error: ErrorDetail


class RoleRef(BaseModel):
    role_id: str = Field(examples=["R004"])
    title: str = Field(examples=["Data Engineer"])
