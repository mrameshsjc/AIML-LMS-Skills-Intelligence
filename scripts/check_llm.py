"""
Check the language model setup (Phase 11).

WHAT IT DOES
    1. Shows the LLM settings from .env.
    2. Asks Ollama whether it is running and whether the model is installed.
    3. Sends one tiny test question and times it (the first call loads the model).
    4. Explains an employee's learning path (API 4) with the LLM, and runs the
       grounding check on the answer.

HOW TO RUN (from the project folder)
    PS> python scripts/check_llm.py
    PS> python scripts/check_llm.py --employee E1020 --model qwen2.5:3b

EXIT CODE
    0  Ollama answered          1  Ollama not usable (the fallback was shown instead)
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.llm.base import LLMRequest, LLMUnavailableError  # noqa: E402
from app.llm.fallback_provider import FallbackProvider  # noqa: E402
from app.llm.ollama_provider import OllamaProvider  # noqa: E402
from app.repositories.csv_repository import CsvLmsRepository  # noqa: E402
from app.services.explanation_service import ExplanationService  # noqa: E402
from app.services.learning_path import LearningPathService  # noqa: E402

parser = argparse.ArgumentParser(description="Check Ollama and try an LLM explanation.")
parser.add_argument("--employee", default="E1001")
parser.add_argument("--model", help="override OLLAMA_MODEL for this check")
args = parser.parse_args()

settings = get_settings()
model = args.model or settings.ollama_model


def heading(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


heading("1. Settings")
print(
    f"LLM_PROVIDER={settings.llm_provider}  OLLAMA_BASE_URL={settings.ollama_base_url}  OLLAMA_MODEL={model}"
)
print(f"LLM_TIMEOUT_SECONDS={settings.llm_timeout_seconds:g}  LLM_TEMPERATURE={settings.llm_temperature:g}")

ollama = OllamaProvider(
    settings.ollama_base_url,
    model,
    settings.llm_timeout_seconds,
    settings.llm_temperature,
    settings.llm_max_tokens,
    settings.llm_allow_remote,
)

heading("2. Is Ollama ready?")
status = ollama.status()
print(("OK    " if status.available else "NOT OK ") + status.detail)
if status.models_installed:
    print(f"Installed models: {', '.join(status.models_installed)}")

works = False
if status.available:
    heading("3. A tiny test question")
    start = time.perf_counter()
    try:
        reply = ollama.generate(LLMRequest("Reply with exactly one word: ready", max_tokens=10))
        works = True
        print(
            f"Answer: {reply.text!r}  ({(time.perf_counter() - start):.1f} s, {reply.output_tokens} tokens)"
        )
        print("The first call loads the model into memory; the next ones are much faster.")
    except LLMUnavailableError as error:
        print(f"NOT OK {error}")

heading(f"4. Explain {args.employee}'s learning path " + ("with Ollama" if works else "(fallback - no LLM)"))
service = ExplanationService(
    LearningPathService(CsvLmsRepository(settings.data_dir)), ollama if works else FallbackProvider()
)
explanation = service.explain_learning_path(args.employee)
print(explanation.text)
seconds = explanation.duration_ms / 1000
print(f"\nprovider={explanation.provider}  model={explanation.model}  time={seconds:.1f} s")
if not explanation.is_fallback:
    print("Grounding check: " + ("no problems found" if not explanation.grounding_warnings else ""))
    for warning in explanation.grounding_warnings:
        print(f"  WARNING {warning}")

if not works:
    print("\nTo use a real LLM: install Ollama (https://ollama.com/download), then run")
    print(f"  ollama pull {model}\nand run this script again.")
sys.exit(0 if works else 1)
