"""
Choosing the provider (Phase 11).

LLM_PROVIDER in .env decides:
    auto      try Ollama; if it cannot answer, use the fallback and say so (default)
    ollama    Ollama only; if it cannot answer, the request fails with a clear error
    fallback  never call a model (CI, tests, machines without Ollama)

"auto" is the friendly default for learning: the engine works on any
computer, and becomes smarter as soon as Ollama is running.
"""

from __future__ import annotations

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMRequest, LLMResult, LLMUnavailableError, ProviderStatus
from app.llm.fallback_provider import FallbackProvider
from app.llm.ollama_provider import OllamaProvider


class AutoProvider(LLMProvider):
    """The primary provider, with the fallback when the primary cannot answer."""

    name = "auto"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or FallbackProvider()
        self.model = primary.model

    def generate(self, request: LLMRequest) -> LLMResult:
        try:
            return self.primary.generate(request)
        except LLMUnavailableError as error:
            result = self.fallback.generate(request)
            note = f"{self.primary.name} unavailable, fallback used: {error}"
            return LLMResult(**{**result.__dict__, "notes": [*result.notes, note]})

    def status(self) -> ProviderStatus:
        primary = self.primary.status()
        if primary.available:
            return primary
        return ProviderStatus(
            "auto",
            primary.model,
            True,
            f"Using the fallback (no LLM) because: {primary.detail}",
            primary.models_installed,
        )


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fallback":
        return FallbackProvider()
    ollama = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        allow_remote=settings.llm_allow_remote,
    )
    return ollama if settings.llm_provider == "ollama" else AutoProvider(ollama)
