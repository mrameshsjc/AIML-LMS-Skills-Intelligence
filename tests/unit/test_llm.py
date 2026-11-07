"""
Tests for the language model layer (Phase 11). No Ollama needed.

A FAKE OLLAMA SERVER (tests/unit/conftest.py)
    Instead of a real model, a tiny HTTP server on a random local port answers
    /api/tags and /api/chat the way Ollama does. The real HTTP code of
    OllamaProvider is exercised (requests, JSON, errors, timeouts), but the
    tests are fast, repeatable and run anywhere, including GitHub Actions.

HOW TO RUN
    PS> pytest tests/unit/test_llm.py -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.llm.base import LLMRequest, LLMResult, LLMUnavailableError
from app.llm.factory import AutoProvider, build_provider
from app.llm.fallback_provider import LABEL, FallbackProvider
from app.llm.guardrails import check_grounding, redact
from app.llm.ollama_provider import OllamaProvider
from app.llm.prompts import SYSTEM_PROMPT, build_messages
from app.repositories.csv_repository import CsvLmsRepository
from app.services.explanation_service import ExplanationService, learning_path_facts
from app.services.learning_path import LearningPathService
from tests.unit.conftest import closed_port_url

ROOT = Path(__file__).resolve().parents[2]


class FixedProvider:
    """A stand-in LLM that returns a fixed text, for testing the services."""

    name, model = "fixed", "fixed-model"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LLMRequest] = []

    def generate(self, request):
        self.requests.append(request)
        return LLMResult(self.text, self.name, self.model)

    def status(self):
        raise NotImplementedError


# --- Ollama provider over real HTTP ------------------------------------------------------


def test_generate_sends_chat_request_and_reads_reply(fake_ollama):
    provider = OllamaProvider(fake_ollama.url, temperature=0.1, max_tokens=99)
    result = provider.generate(LLMRequest("Explain.", context=["SQL is level 2."]))
    assert result.text == "Hello from the fake model." and result.provider == "ollama"
    assert (result.prompt_tokens, result.output_tokens) == (120, 42) and not result.is_fallback
    sent = fake_ollama.requests[0]
    assert sent["model"] == "llama3.2:3b" and sent["stream"] is False
    assert sent["options"] == {"temperature": 0.1, "num_predict": 99}
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]
    assert "- SQL is level 2." in sent["messages"][1]["content"]


def test_request_can_override_temperature_and_length(fake_ollama):
    OllamaProvider(fake_ollama.url).generate(LLMRequest("x", temperature=0.9, max_tokens=10))
    assert fake_ollama.requests[0]["options"] == {"temperature": 0.9, "num_predict": 10}


def test_missing_model_explains_how_to_pull_it(fake_ollama):
    with pytest.raises(LLMUnavailableError, match="ollama pull qwen2.5:3b"):
        OllamaProvider(fake_ollama.url, model="qwen2.5:3b").generate(LLMRequest("x"))


def test_ollama_not_running():
    with pytest.raises(LLMUnavailableError, match="Is it running"):
        OllamaProvider(closed_port_url()).generate(LLMRequest("x"))


def test_timeout(fake_ollama):
    fake_ollama.delay = 1.5
    with pytest.raises(LLMUnavailableError, match="did not answer within 0.5 s"):
        OllamaProvider(fake_ollama.url, timeout_seconds=0.5).generate(LLMRequest("x"))


def test_empty_answer_is_an_error(fake_ollama):
    fake_ollama.reply = "   "
    with pytest.raises(LLMUnavailableError, match="empty"):
        OllamaProvider(fake_ollama.url).generate(LLMRequest("x"))


def test_status_lists_models_and_checks_the_configured_one(fake_ollama):
    fake_ollama.models = ["llama3.2:3b", "qwen2.5:3b"]
    ok = OllamaProvider(fake_ollama.url).status()
    assert ok.available and ok.models_installed == ["llama3.2:3b", "qwen2.5:3b"]
    missing = OllamaProvider(fake_ollama.url, model="phi3").status()
    assert not missing.available and "ollama pull phi3" in missing.detail
    assert not OllamaProvider(closed_port_url()).status().available


def test_model_without_tag_means_latest(fake_ollama):
    fake_ollama.models = ["llama3.2:latest"]
    assert OllamaProvider(fake_ollama.url, model="llama3.2").status().available
    assert not OllamaProvider(fake_ollama.url, model="llama3.2:3b").status().available


def test_remote_host_needs_approval():
    with pytest.raises(ValueError, match="LLM_ALLOW_REMOTE"):
        OllamaProvider("https://llm.example.com")
    assert OllamaProvider("https://llm.example.com", allow_remote=True).base_url == "https://llm.example.com"
    for local in ("http://localhost:11434", "http://host.docker.internal:11434", "http://ollama:11434"):
        OllamaProvider(local)


# --- Fallback and automatic choice ------------------------------------------------------------


def test_fallback_lists_the_facts_with_a_label():
    result = FallbackProvider().generate(LLMRequest("Explain.", context=["Fact one.", "Mail a@b.com"]))
    assert result.is_fallback and result.text.startswith(LABEL)
    assert "- Fact one." in result.text and "[email]" in result.text and "a@b.com" not in result.text
    assert FallbackProvider().status().available


def test_auto_uses_ollama_when_it_answers(fake_ollama):
    result = AutoProvider(OllamaProvider(fake_ollama.url)).generate(LLMRequest("x"))
    assert result.provider == "ollama" and not result.is_fallback


def test_auto_falls_back_and_says_why():
    auto = AutoProvider(OllamaProvider(closed_port_url()))
    result = auto.generate(LLMRequest("x", context=["A fact."]))
    assert result.is_fallback and "- A fact." in result.text
    assert "fallback used" in result.notes[0] and "Is it running" in result.notes[0]
    status = auto.status()
    assert status.available and status.provider == "auto" and "fallback" in status.detail


def test_build_provider_follows_the_setting():
    assert isinstance(build_provider(Settings(llm_provider="fallback")), FallbackProvider)
    assert isinstance(build_provider(Settings(llm_provider="ollama")), OllamaProvider)
    assert isinstance(build_provider(Settings(llm_provider="auto")), AutoProvider)


# --- Prompts and guardrails -------------------------------------------------------------------


def test_prompt_has_rules_facts_and_no_personal_contact_data():
    messages = build_messages(LLMRequest("Help user@corp.com", context=["Phone +91 98765 43210."]))
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    user = messages[1]["content"]
    assert user.startswith("<facts>") and "</facts>" in user
    assert "user@corp.com" not in user and "98765" not in user


@pytest.mark.parametrize(
    "text, expected",
    [
        ("mail anna.k@example.com now", "mail [email] now"),
        ("call +1 (555) 123-4567 today", "call [phone] today"),
        ("SQL level 4 in 21 hours", "SQL level 4 in 21 hours"),  # normal numbers stay
    ],
)
def test_redact(text, expected):
    assert redact(text) == expected


def test_grounding_check():
    facts = ["Step 1: C-SQL-201 (21 hours).", "Match now: 62.5%. After the path: 100%."]
    assert check_grounding("Start with C-SQL-201 (21 hours) to go from 62.5% to 100%, step 1.", facts) == []
    warnings = check_grounding("Then take C-SQL-301; it takes 12 weeks.", facts)
    assert "C-SQL-301" in warnings[0] and "12" in warnings[1]


# --- Explanation service ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def paths() -> LearningPathService:
    return LearningPathService(CsvLmsRepository())


def test_facts_describe_the_learning_path(paths):
    facts = learning_path_facts(paths.build("E1001"))
    text = "\n".join(facts)
    assert facts[0] == "Employee first name: Arjun."
    assert "Match with Data Engineer now: 62.5%. After completing the path: 100%." in text
    assert "Step 4: C-AWS-201" in text and "Take it after step 3." in text
    assert "The path has 5 steps and 90 hours in total." in text
    assert facts[-1].startswith("Next action: Enrol in C-SQL-201")
    assert "@" not in text  # no e-mail address is ever sent


def test_explanation_with_a_model_is_checked(paths):
    good = ExplanationService(paths, FixedProvider("Start with C-SQL-201: 21 hours, then reach 100%."))
    result = good.explain_learning_path("E1001")
    assert result.provider == "fixed" and result.grounding_warnings == []
    bad = ExplanationService(paths, FixedProvider("Take C-SPARK-999 for 40 weeks."))
    assert len(bad.explain_learning_path("E1001").grounding_warnings) == 2


def test_explanation_with_the_fallback(paths):
    result = ExplanationService(paths, FallbackProvider()).explain_learning_path("E1001")
    assert result.is_fallback and "Next action: Enrol in C-SQL-201" in result.text
    assert result.grounding_warnings == []  # the fallback only repeats facts


def test_ollama_only_setting_turns_an_outage_into_503(paths):
    service = ExplanationService(paths, OllamaProvider(closed_port_url()))
    with pytest.raises(ServiceUnavailableError) as error:
        service.explain_learning_path("E1001")
    assert error.value.code == "LLM_UNAVAILABLE" and error.value.status_code == 503


# --- The check script ---------------------------------------------------------------------------


def _run_check(url: str) -> subprocess.CompletedProcess:
    # Environment variables beat .env, so your own .env (e.g. another OLLAMA_MODEL) cannot change the test.
    env = {**os.environ, "OLLAMA_BASE_URL": url, "OLLAMA_MODEL": "llama3.2:3b", "LLM_TIMEOUT_SECONDS": "10"}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_llm.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_check_script_with_a_running_model(fake_ollama):
    result = _run_check(fake_ollama.url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK    Ollama is running with llama3.2:3b." in result.stdout
    assert "provider=ollama" in result.stdout


def test_check_script_without_ollama():
    result = _run_check(closed_port_url())
    assert result.returncode == 1
    assert "Fallback - no LLM" in result.stdout and "ollama pull llama3.2:3b" in result.stdout
