"""
Hosted inference: any OpenAI-compatible chat service (Phase 19, public demo).

WHY
    The free hosting tiers that run the demo (Hugging Face Spaces, Render, ...)
    have no GPU and too little memory for Ollama. The requirements say: "If the
    LLM cannot be hosted on the same free tier, separate it from the
    application" and allow "hosted inference for public demonstration where
    appropriate" through "an explicitly configured adapter". This is that adapter.

WHAT IT TALKS TO
    The OpenAI-compatible endpoint POST {base_url}/chat/completions, which many
    services offer - for example the Hugging Face router
    (https://router.huggingface.co/v1, token from huggingface.co/settings/tokens).
    It sends the same messages as Ollama: system rules, redacted facts, question.

EXPLICITLY CONFIGURED - never by accident
    LLM_PROVIDER=hosted, HOSTED_LLM_MODEL and HOSTED_LLM_API_KEY must all be set,
    AND LLM_ALLOW_REMOTE=true (prompts leave the machine: synthetic demo data
    only). The server refuses to start with hosted and without that approval.

FAILURE
    Any problem (no key, quota used up, timeout, model not offered) raises
    LLMUnavailableError; with LLM_PROVIDER=hosted the labelled fallback answers
    instead ("Fallback - no LLM"), exactly as when Ollama is down locally.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from app.llm.base import LLMProvider, LLMRequest, LLMResult, LLMUnavailableError, ProviderStatus
from app.llm.prompts import build_messages


class HostedProvider(LLMProvider):
    name = "hosted"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key  # never logged, never returned in an error message
        self.timeout = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _missing(self) -> str | None:
        if not self.model:
            return "HOSTED_LLM_MODEL is not set."
        if not self._api_key:
            return "HOSTED_LLM_API_KEY is not set."
        return None

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            hint = {
                401: "the API key was refused",
                402: "the free quota is used up",
                403: "the API key may not use this model",
                404: f"the service does not offer the model '{self.model}'",
                429: "too many requests (rate limit of the service)",
            }.get(error.code, "the service reported an error")
            raise LLMUnavailableError(f"Hosted LLM returned HTTP {error.code}: {hint}.") from error
        except TimeoutError as error:
            raise LLMUnavailableError(f"Hosted LLM did not answer within {self.timeout:g} s.") from error
        except urllib.error.URLError as error:
            raise LLMUnavailableError(
                f"Cannot reach the hosted LLM at {self.base_url} ({error.reason})."
            ) from error
        except json.JSONDecodeError as error:
            raise LLMUnavailableError("The hosted LLM sent a reply that is not JSON.") from error

    def generate(self, request: LLMRequest) -> LLMResult:
        missing = self._missing()
        if missing:
            raise LLMUnavailableError(f"Hosted LLM not configured: {missing}")
        payload = {
            "model": self.model,
            "messages": build_messages(request),
            "temperature": self.temperature if request.temperature is None else request.temperature,
            "max_tokens": self.max_tokens if request.max_tokens is None else request.max_tokens,
            "stream": False,
        }
        start = time.perf_counter()
        reply = self._post(payload)
        try:
            text = (reply["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as error:
            raise LLMUnavailableError("The hosted LLM reply has no answer text.") from error
        if not text:
            raise LLMUnavailableError("The hosted LLM returned an empty answer.")
        usage = reply.get("usage") or {}
        return LLMResult(
            text=text,
            provider=self.name,
            model=reply.get("model") or self.model,
            is_fallback=False,
            duration_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    def status(self) -> ProviderStatus:
        """Configuration check only: a test call would spend the (small) free quota on every page view."""
        missing = self._missing()
        if missing:
            return ProviderStatus(self.name, self.model, False, f"Hosted LLM not configured: {missing}")
        return ProviderStatus(
            self.name,
            self.model,
            True,
            f"Hosted LLM {self.model} at {self.base_url} (answers fall back to 'no LLM' if it fails).",
        )
