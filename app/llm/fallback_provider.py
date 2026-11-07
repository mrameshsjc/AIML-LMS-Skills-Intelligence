"""
Fallback provider: answers WITHOUT a language model (Phase 11).

PURPOSE
    The engine must keep working when no LLM is available: Ollama not
    installed or not running, a laptop without enough memory, CI, or tests.
    The fallback returns the FACTS themselves as a short, readable list,
    clearly labelled "fallback - no LLM", so nobody mistakes it for a
    generated answer.

    Because it only repeats facts produced by the engine, it can never
    hallucinate. It is less fluent, never wrong about the data.
"""

from __future__ import annotations

import time

from app.llm.base import LLMProvider, LLMRequest, LLMResult, ProviderStatus
from app.llm.guardrails import redact

LABEL = "Fallback - no LLM: this answer lists the engine's facts directly."


class FallbackProvider(LLMProvider):
    name = "fallback"
    model = "none"

    def generate(self, request: LLMRequest) -> LLMResult:
        start = time.perf_counter()
        if request.context:
            body = "\n".join(f"- {redact(line)}" for line in request.context)
        else:
            body = "- No information is available for this question."
        return LLMResult(
            text=f"{LABEL}\n{body}",
            provider=self.name,
            model=self.model,
            is_fallback=True,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            self.name, self.model, True, "Always available; answers list the facts without an LLM."
        )
