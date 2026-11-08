"""
The hosted-inference adapter (Phase 19), against a fake OpenAI-compatible
server on this machine: no internet, no API key, no cost.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.config import Settings
from app.llm.base import LLMRequest, LLMUnavailableError
from app.llm.factory import AutoProvider, build_provider
from app.llm.hosted_provider import HostedProvider


@pytest.fixture
def fake_service():
    """Answers POST /v1/chat/completions like an OpenAI-compatible service."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            server.requests.append({"body": body, "auth": self.headers.get("Authorization")})
            status, reply = (
                server.status,
                {
                    "model": body["model"],
                    "choices": [{"message": {"role": "assistant", "content": server.reply}}],
                    "usage": {"prompt_tokens": 42, "completion_tokens": 7},
                },
            )
            data = json.dumps(reply if status == 200 else {"error": "nope"}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.reply, server.status = [], "Take C-SQL-201 first [S1].", 200
    server.url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def provider(url, key="secret-key", model="demo/model"):
    return HostedProvider(url, model, key, timeout_seconds=5)


def test_answer_from_the_service(fake_service):
    result = provider(fake_service.url).generate(LLMRequest("What next?", ["Gap: SQL 2 -> 4"]))
    assert result.text == "Take C-SQL-201 first [S1]." and result.provider == "hosted"
    assert not result.is_fallback and (result.prompt_tokens, result.output_tokens) == (42, 7)
    sent = fake_service.requests[0]
    assert sent["auth"] == "Bearer secret-key" and sent["body"]["model"] == "demo/model"
    assert sent["body"]["messages"][0]["role"] == "system"  # the same guarded prompt as Ollama
    assert "Gap: SQL 2 -> 4" in sent["body"]["messages"][-1]["content"]


@pytest.mark.parametrize("status, words", [(401, "refused"), (402, "quota"), (404, "does not offer")])
def test_service_errors_become_clear_unavailable_errors(fake_service, status, words):
    fake_service.status = status
    with pytest.raises(LLMUnavailableError) as error:
        provider(fake_service.url).generate(LLMRequest("Hi"))
    assert words in str(error.value) and "secret-key" not in str(error.value)


def test_missing_configuration_is_reported_without_a_call(fake_service):
    status = provider(fake_service.url, key="").status()
    assert not status.available and "HOSTED_LLM_API_KEY" in status.detail
    with pytest.raises(LLMUnavailableError):
        provider(fake_service.url, model="").generate(LLMRequest("Hi"))
    assert fake_service.requests == []


def test_failure_falls_back_with_a_label(fake_service):
    fake_service.status = 429
    result = AutoProvider(provider(fake_service.url)).generate(LLMRequest("Hi", ["fact"]))
    assert result.is_fallback and any("hosted unavailable" in n for n in result.notes)


def test_factory_needs_explicit_approval():
    with pytest.raises(ValueError):
        build_provider(Settings(llm_provider="hosted", llm_allow_remote=False))
    built = build_provider(Settings(llm_provider="hosted", llm_allow_remote=True, hosted_llm_model="m"))
    assert isinstance(built, AutoProvider) and isinstance(built.primary, HostedProvider)
    problems = Settings(llm_provider="hosted").check_security()
    assert any("LLM_ALLOW_REMOTE" in p for p in problems)
