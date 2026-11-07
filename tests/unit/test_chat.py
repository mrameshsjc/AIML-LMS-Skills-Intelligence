"""
Tests for the LMS AI assistant (Phase 13). No Ollama needed: a stand-in
model records what it was given, and the fallback is used for full answers.

HOW TO RUN
    PS> pytest tests/unit/test_chat.py -v
"""

import pytest

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.llm.base import LLMResult
from app.llm.fallback_provider import FallbackProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.prompts import build_messages
from app.rag.embeddings import TfidfEmbedder
from app.rag.index import IndexNotReadyError, KnowledgeIndex, build_index
from app.rag.vector_store import NumpyVectorStore
from app.repositories.csv_repository import CsvLmsRepository
from app.services.chat_service import NO_INFORMATION, ChatService
from tests.unit.conftest import closed_port_url


class RecordingModel:
    """Answers with a fixed text and keeps every request, so tests can see what the model received."""

    name, model = "ollama", "test-model"

    def __init__(self, text: str = "Answer.") -> None:
        self.text = text
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return LLMResult(self.text, self.name, self.model)

    def status(self):
        raise NotImplementedError


@pytest.fixture(scope="module")
def repo():
    return CsvLmsRepository()


@pytest.fixture(scope="module")
def index(tmp_path_factory) -> KnowledgeIndex:
    target = tmp_path_factory.mktemp("store") / "default"
    build_index("documents", target, TfidfEmbedder(), NumpyVectorStore)
    return KnowledgeIndex.load(target)


def make(repo, index=None, model=None, min_score=0.08):
    model = model or RecordingModel()
    return ChatService(repo, model, lambda: index, lambda i: min_score), model


# --- Understanding the question ------------------------------------------------------------


def test_personal_question_uses_the_learning_path(repo, index):
    chat, model = make(repo, index)
    answer = chat.ask("What are my current skill gaps?", "E1001")
    assert "my_learning_path" in answer.intents
    assert "Gap (mandatory): SQL is level 2, Data Engineer needs level 4." in answer.facts
    assert answer.facts[0] == "Employee first name: Arjun."
    assert model.requests[0].context[: len(answer.facts)] == answer.facts


def test_named_role_becomes_the_target_of_my_path(repo, index):
    chat, _ = make(repo, index)
    answer = chat.ask("What skills do I need to become an AI Engineer?", "E1001")
    assert any("Target role: AI Engineer" in f for f in answer.facts)
    assert "role_requirements" not in answer.intents  # covered by the path itself


def test_role_requirements_without_employee(repo, index):
    chat, _ = make(repo, index)
    answer = chat.ask("Which skills are required for an AI Engineer?")
    assert answer.intents[0] == "role_requirements"
    assert (
        "AI Engineer mandatory skills: Python level 4, LLM Applications level 4, Prompt Engineering level 3."
        in (answer.facts)
    )


def test_role_question_stays_about_the_role_when_an_employee_asks(repo, index):
    """Found by the dashboard test: the assistant page sends employee_id with every question."""
    chat, _ = make(repo, index)
    answer = chat.ask("Which skills are required for an AI Engineer?", "E1001")
    assert answer.intents[0] == "role_requirements" and "my_learning_path" not in answer.intents
    assert any("Prompt Engineering level 3" in f for f in answer.facts)
    assert "my_learning_path" in chat.ask("Which courses are recommended next?", "E1001").intents


def test_longest_role_name_wins(repo):
    chat, _ = make(repo)
    facts = chat.ask("What does a Senior Software Developer need?").facts
    assert facts[0].startswith("Job role Senior Software Developer")
    assert not any(f.startswith("Job role Software Developer") for f in facts)


def test_skill_question_lists_courses_above_my_level(repo, index):
    chat, _ = make(repo, index)
    answer = chat.ask("What training should I complete to improve my Python skills?", "E1001")
    assert "skill_courses" in answer.intents
    assert "The employee's current Python level: 3." in answer.facts
    python_courses = [f for f in answer.facts if f.startswith("Course C-PY")]
    assert python_courses and all("C-PY-101" not in f.split("'")[0] for f in python_courses)  # completed


def test_why_question_includes_the_reason(repo, index):
    chat, _ = make(repo, index)
    answer = chat.ask("Why was C-AWS-201 recommended?", "E1001")
    assert {"my_learning_path", "course_details"} <= set(answer.intents)
    why = [f for f in answer.facts if f.startswith("Why step")]
    assert len(why) == 1 and "Complete first: C-AWS-101" in why[0]


def test_personal_question_without_employee_gets_a_note(repo, index):
    chat, _ = make(repo, index)
    answer = chat.ask("What are my current skill gaps?")
    assert "my_learning_path" not in answer.intents
    assert any("send employee_id" in n for n in answer.notes)
    assert not any("employee_id" in n for n in chat.ask("How many learning hours do I get?").notes)


def test_unknown_employee(repo):
    with pytest.raises(NotFoundError):
        make(repo)[0].ask("What are my gaps?", "E9999")


# --- Documents and citations ---------------------------------------------------------------------


def test_document_question_cites_sources(repo, index):
    chat, model = make(repo, index)
    answer = chat.ask("How much of the certification exam fee is reimbursed?")
    assert answer.intents == ["documents"] and answer.facts == []
    assert answer.sources[0].source == "certification_reimbursement_policy.pdf"
    assert [s.label for s in answer.sources] == [f"S{i}" for i in range(1, len(answer.sources) + 1)]
    context = model.requests[0].context
    assert context[0].startswith("[S1] Certification Reimbursement Policy, section '")


def test_weak_passages_are_dropped(repo, index):
    answer = make(repo, index)[0].ask("Which skills are required for an AI Engineer?")
    assert [s.source for s in answer.sources] == ["job_role_profiles.md"]  # others are far below the best
    assert all(s.score >= 0.5 * answer.sources[0].score for s in answer.sources)


def test_nothing_relevant_means_no_model_call(repo, index):
    chat, model = make(repo, index)
    answer = chat.ask("What is the capital of France?")
    assert answer.answer == NO_INFORMATION and answer.provider == "none" and model.requests == []


def test_invented_citation_is_flagged(repo, index):
    chat, _ = make(repo, index, RecordingModel("You get 40 hours per year [S1][S7]."))
    answer = chat.ask("How many learning hours do I get per year?")
    assert any("S7" in w for w in answer.grounding_warnings)
    assert not any("40" in w for w in answer.grounding_warnings)


def test_fallback_lists_facts_and_passages(repo, index):
    chat = ChatService(repo, FallbackProvider(), lambda: index, lambda i: 0.08)
    answer = chat.ask("How many learning hours do I get per year?")
    assert answer.is_fallback and "40 hours" in answer.answer and answer.grounding_warnings == []


def test_without_an_index_the_engine_data_still_answers(repo):
    chat, _ = make(repo, None)
    answer = chat.ask("What are my skill gaps?", "E1001")
    assert "my_learning_path" in answer.intents and answer.sources == []
    assert any("No document index" in n for n in answer.notes)


def test_broken_index_is_a_note_not_an_error(repo):
    def broken():
        raise IndexNotReadyError("built with another embedding model")

    answer = ChatService(repo, RecordingModel(), broken).ask("What are my gaps?", "E1001")
    assert any("another embedding model" in n for n in answer.notes) and answer.facts


def test_ollama_only_outage_is_503(repo, index):
    chat = ChatService(repo, OllamaProvider(closed_port_url()), lambda: index, lambda i: 0.08)
    with pytest.raises(ServiceUnavailableError) as error:
        chat.ask("How many learning hours do I get per year?")
    assert error.value.code == "LLM_UNAVAILABLE"


# --- Conversation ---------------------------------------------------------------------------------


def test_history_reaches_the_model(repo, index):
    chat, model = make(repo, index)
    history = [("user", "Which skills does an AI Engineer need?"), ("assistant", "Python level 4, ...")]
    chat.ask("And what about prompt engineering courses?", history=history)
    messages = build_messages(model.requests[0])
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]


def test_short_follow_up_is_searched_with_the_previous_question(repo, index):
    chat, _ = make(repo, index)
    history = [("user", "How much of the certification exam fee is reimbursed?"), ("assistant", "...")]
    answer = chat.ask("And a second attempt?", history=history)
    assert answer.sources and answer.sources[0].source == "certification_reimbursement_policy.pdf"


def test_only_the_last_turns_are_sent(repo):
    chat, model = make(repo)
    history = [("user", f"q{i}") for i in range(10)]
    chat.ask("Which skills are required for an AI Engineer?", history=history)
    messages = build_messages(model.requests[0])
    assert [m["content"] for m in messages[1:-1]] == [f"q{i}" for i in range(4, 10)]
