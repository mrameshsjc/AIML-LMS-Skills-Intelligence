"""
Application errors with a user-friendly message and an HTTP status.

PURPOSE
    Services raise these when a request cannot be answered (for example, the
    employee does not exist). They contain no web code, so services stay
    usable from the dashboard and tests. The API layer (app/main.py) turns
    them into the shared error format:

        {"error": {"code": "EMPLOYEE_NOT_FOUND", "message": "...", "request_id": "..."}}

WHY NOT RAISE HTTPException IN SERVICES
    HTTPException belongs to FastAPI. A service that raised it would tie the
    business logic to one web framework - exactly what the layered design avoids.
"""


class AppError(Exception):
    """Base class: every application error has a code, a message and an HTTP status."""

    status_code = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(AppError):
    """Something the request refers to does not exist (HTTP 404)."""

    status_code = 404


class InvalidInputError(AppError):
    """The request is well-formed but its content cannot be used (HTTP 422)."""

    status_code = 422


class ServiceUnavailableError(AppError):
    """A component the request needs is not available right now, e.g. the LLM (HTTP 503)."""

    status_code = 503


class ConflictError(AppError):
    """The request conflicts with what exists, e.g. a document with that name (HTTP 409)."""

    status_code = 409


class PayloadTooLargeError(AppError):
    """An uploaded file is bigger than allowed (HTTP 413)."""

    status_code = 413


class UnauthorizedError(AppError):
    """The request needs credentials that were missing or wrong (HTTP 401)."""

    status_code = 401


class ForbiddenError(AppError):
    """The action is not allowed (HTTP 403)."""

    status_code = 403
