"""
Ollama provider: a language model running on YOUR computer (Phase 11).

WHAT IS OLLAMA?
    A free program that downloads open models (Llama, Qwen, Phi, ...) and
    serves them over a small HTTP API on http://localhost:11434. Nothing
    leaves your machine, which is why it suits employee data.

    Install: https://ollama.com/download
    Get a model:  ollama pull llama3.2:3b     (about 2 GB, runs on a normal laptop CPU)
    Check:        ollama list

THE TWO OLLAMA ENDPOINTS USED
    GET  /api/tags   which models are installed       -> status()
    POST /api/chat   answer a list of chat messages    -> generate()
         body: {"model": "llama3.2:3b", "messages": [...], "stream": false,
                "options": {"temperature": 0.2, "num_predict": 512}}
         reply: {"message": {"role": "assistant", "content": "..."},
                 "prompt_eval_count": 210, "eval_count": 95, "total_duration": 4100000000}

WHY PYTHON'S BUILT-IN urllib (and no proxy)
    No extra library is needed for two simple JSON calls. Proxies are switched
    off for these requests: a company proxy must never see LLM traffic that is
    meant to stay on this machine (and could not reach localhost anyway).

LOCAL ONLY, UNLESS APPROVED
    The base URL must point to this machine or the Docker Compose network
    (localhost, 127.0.0.1, host.docker.internal, ollama). Any other host is
    refused unless LLM_ALLOW_REMOTE=true, because the requirements forbid
    sending employee data to an external AI service without approval.

SPEED
    The first request loads the model into memory and can take 10-60 s on a
    CPU; later requests are much faster. The timeout (LLM_TIMEOUT_SECONDS)
    is generous for that reason.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.llm.base import LLMProvider, LLMRequest, LLMResult, LLMUnavailableError, ProviderStatus
from app.llm.prompts import build_messages

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}

# An opener with an EMPTY proxy table: requests go straight to Ollama, never through a proxy.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout_seconds: float = 120,
        temperature: float = 0.2,
        max_tokens: int = 512,
        allow_remote: bool = False,
    ) -> None:
        host = urlparse(base_url).hostname or ""
        if host not in LOCAL_HOSTS and not allow_remote:
            raise ValueError(
                f"OLLAMA_BASE_URL host '{host}' is not on this machine. Employee data must not leave it "
                "without approval; set LLM_ALLOW_REMOTE=true only if that has been approved."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    # --- HTTP -----------------------------------------------------------------------
    def _call(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with _DIRECT.open(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:  # Ollama answered, with an error status
            message = _error_message(error)
            if error.code == 404 and "not found" in message.lower():
                raise LLMUnavailableError(
                    f"Ollama does not have the model '{self.model}'. Run: ollama pull {self.model}"
                ) from error
            raise LLMUnavailableError(f"Ollama returned HTTP {error.code}: {message}") from error
        except TimeoutError as error:  # socket.timeout is the same class since Python 3.10
            raise LLMUnavailableError(
                f"Ollama did not answer within {timeout or self.timeout:g} s. The first request loads the "
                "model and is slow; try again, use a smaller model, or raise LLM_TIMEOUT_SECONDS."
            ) from error
        except urllib.error.URLError as error:  # nothing listening, DNS failure, ...
            if isinstance(error.reason, TimeoutError):
                raise LLMUnavailableError(
                    f"Ollama did not answer within {timeout or self.timeout:g} s; "
                    "try again or raise LLM_TIMEOUT_SECONDS."
                ) from error
            raise LLMUnavailableError(
                f"Cannot reach Ollama at {self.base_url} ({error.reason}). "
                "Is it running? Start the Ollama app, or run: ollama serve"
            ) from error
        except json.JSONDecodeError as error:
            raise LLMUnavailableError(f"Ollama sent a reply that is not JSON: {error}") from error

    # --- Interface ----------------------------------------------------------------------
    def generate(self, request: LLMRequest) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": build_messages(request),
            "stream": False,  # one complete reply; streaming word by word comes with the chat UI
            "options": {
                "temperature": self.temperature if request.temperature is None else request.temperature,
                "num_predict": self.max_tokens if request.max_tokens is None else request.max_tokens,
            },
        }
        start = time.perf_counter()
        reply = self._call("/api/chat", payload)
        text = (reply.get("message") or {}).get("content", "").strip()
        if not text:
            raise LLMUnavailableError("Ollama returned an empty answer.")
        return LLMResult(
            text=text,
            provider=self.name,
            model=reply.get("model", self.model),
            is_fallback=False,
            duration_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=reply.get("prompt_eval_count"),
            output_tokens=reply.get("eval_count"),
        )

    def status(self) -> ProviderStatus:
        try:
            tags = self._call("/api/tags", timeout=min(5.0, self.timeout))
        except LLMUnavailableError as error:
            return ProviderStatus(self.name, self.model, False, str(error))
        installed = sorted(m.get("name", "") for m in tags.get("models", []))
        if not _has_model(installed, self.model):
            return ProviderStatus(
                self.name,
                self.model,
                False,
                f"Ollama is running, but the model '{self.model}' is not installed. "
                f"Run: ollama pull {self.model}",
                installed,
            )
        return ProviderStatus(self.name, self.model, True, f"Ollama is running with {self.model}.", installed)


def _has_model(installed: list[str], model: str) -> bool:
    """'llama3.2' matches 'llama3.2:latest'; 'llama3.2:3b' must match exactly."""
    wanted = model if ":" in model else f"{model}:latest"
    return wanted in installed


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        return json.loads(error.read().decode("utf-8")).get("error", error.reason)
    except (ValueError, AttributeError):
        return str(error.reason)
