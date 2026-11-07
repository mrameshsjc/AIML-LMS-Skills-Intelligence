"""
The LLM provider interface (Phase 11).

PURPOSE
    Every language model the engine can use - local Ollama today, perhaps a
    hosted model for the public demo later - is wrapped in a class with the
    SAME two methods:

        generate(request) -> LLMResult    answer one request
        status()          -> ProviderStatus   is it reachable, which model?

    Services only know this interface, so changing the model or provider is a
    setting in .env, never a code change (the same idea as LmsRepository).

WHAT A REQUEST CONTAINS
    instruction  what to do, e.g. "Explain this learning path to the employee."
    context      the FACTS the answer must be based on: lines produced by the
                 engine (gaps, courses, steps) or, from Phase 13, retrieved
                 document passages. The model is told to use ONLY these.
    Keeping facts separate from the instruction is what makes "grounding"
    possible: the answer can be checked against the facts afterwards.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMUnavailableError(RuntimeError):
    """The model cannot answer right now (not running, model missing, timeout, ...)."""


@dataclass(frozen=True)
class LLMRequest:
    instruction: str
    context: list[str] = field(default_factory=list)
    temperature: float | None = None  # None = use the configured default
    max_tokens: int | None = None
    # Earlier turns of a conversation (Phase 13): [("user", "..."), ("assistant", "..."), ...]
    history: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str  # ollama | fallback
    model: str
    is_fallback: bool = False
    duration_ms: int = 0
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    model: str
    available: bool
    detail: str
    models_installed: list[str] = field(default_factory=list)


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResult:
        """Answer the request, or raise LLMUnavailableError."""

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Cheap check: can this provider answer right now? Never raises."""
