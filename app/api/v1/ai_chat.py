"""
API 5 - LMS AI Assistant: POST /api/v1/ai/chat

PURPOSE
    Answer questions about skills, roles, courses, learning paths and the
    learning policies, from LMS data and approved documents, with sources.
    All logic is in app/services/chat_service.py.

ERRORS (shared format)
    404 EMPLOYEE_NOT_FOUND / ROLE_NOT_FOUND
    422 VALIDATION_ERROR
    503 LLM_UNAVAILABLE (only with LLM_PROVIDER=ollama; "auto" falls back instead)
"""

from fastapi import APIRouter

from app.api.dependencies import ChatLimitDep, ChatServiceDep, CurrentUserDep, RepositoryDep
from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse, SourceOut
from app.schemas.common import AUTH_RESPONSES, ErrorResponse
from app.security.access import authorize_employee
from app.services.chat_service import ChatAnswer

router = APIRouter(prefix="/ai", tags=["5. AI Assistant"])


def to_response(a: ChatAnswer) -> ChatResponse:
    return ChatResponse(
        question=a.question,
        answer=a.answer,
        provider=a.provider,
        model=a.model,
        is_fallback=a.is_fallback,
        intents=a.intents,
        sources=[
            SourceOut(
                label=s.label,
                source=s.source,
                title=s.title,
                section=s.section,
                page=s.page,
                score=s.score,
                excerpt=s.text if len(s.text) <= 300 else s.text[:297] + "...",
            )
            for s in a.sources
        ],
        facts=a.facts,
        grounding_warnings=a.grounding_warnings,
        notes=a.notes,
        duration_ms=a.duration_ms,
        engine_version=get_settings().app_version,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the LMS AI assistant",
    description=(
        "Answers from two sources: **LMS data** (your gaps and learning path when `employee_id` is sent; "
        "any job role, skill or course ID named in the question) and **approved documents** (policies, FAQ, "
        "guides), cited as [S1], [S2]. If neither has relevant information, the assistant says so instead of "
        "guessing. `facts`, `sources` and `grounding_warnings` let you check every answer.\n\n"
        "Without a running language model, a labelled fallback lists the facts and passages."
    ),
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Employee or role not found"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        503: {"model": ErrorResponse, "description": "LLM unavailable (LLM_PROVIDER=ollama)"},
    },
)
def chat(
    request: ChatRequest,
    service: ChatServiceDep,
    principal: CurrentUserDep,
    repository: RepositoryDep,
    _: ChatLimitDep,
) -> ChatResponse:
    # A logged-in employee asking about "my gaps" means themselves, even without employee_id.
    employee_id = request.employee_id or (principal.employee_id if principal.authenticated else None)
    authorize_employee(principal, employee_id, repository)  # Phase 17: own / team data only
    history = [(turn.role, turn.content) for turn in request.history]
    return to_response(service.ask(request.question, employee_id, history))
