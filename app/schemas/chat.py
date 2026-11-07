"""Request and response shapes for API 5: POST /api/v1/ai/chat."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000, examples=["What are my current skill gaps?"])
    employee_id: str | None = Field(
        default=None, pattern=r"^E\d{4}$", description="Needed for questions about your own skills and path."
    )
    history: list[ChatTurn] = Field(
        default_factory=list,
        max_length=20,
        description="Earlier turns of the conversation (the last 6 are used).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"question": "What are my current skill gaps?", "employee_id": "E1001"},
                {"question": "Which skills are required for an AI Engineer?"},
                {"question": "How many learning hours do I have per year?"},
                {"question": "Why was C-AWS-201 recommended?", "employee_id": "E1001"},
            ]
        }
    )


class SourceOut(BaseModel):
    label: str = Field(examples=["S1"], description="How the answer cites this passage, e.g. [S1].")
    source: str = Field(examples=["learning_policy.md"])
    title: str
    section: str
    page: int | None
    score: float = Field(description="Similarity to the question (higher = more relevant).")
    excerpt: str = Field(description="The passage, shortened to 300 characters.")


class ChatResponse(BaseModel):
    question: str
    answer: str
    provider: str = Field(
        description="ollama, fallback (no LLM), or none (no information found; no model called)."
    )
    model: str
    is_fallback: bool
    intents: list[str] = Field(
        description="What the question was understood to need: my_learning_path, role_requirements, "
        "skill_courses, course_details, documents."
    )
    sources: list[SourceOut] = Field(description="Document passages the answer may cite.")
    facts: list[str] = Field(description="LMS data given to the model (gaps, path, roles, courses).")
    grounding_warnings: list[str] = Field(description="Course IDs, numbers or citations not in the facts.")
    notes: list[str]
    duration_ms: int
    engine_version: str
