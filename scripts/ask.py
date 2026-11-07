"""
Ask the LMS AI assistant from the command line (Phase 13).

The same assistant as API 5 (POST /api/v1/ai/chat): LMS data + approved
documents, answered by the language model (or the labelled fallback).

HOW TO RUN (from the project folder)
    PS> python scripts/ask.py "What are my current skill gaps?" --employee E1001
    PS> python scripts/ask.py "Which skills are required for an AI Engineer?"
    PS> python scripts/ask.py --employee E1001            (interactive: type questions, empty line to stop)
"""

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.dependencies import get_chat_service, get_llm_provider, get_repository  # noqa: E402
from app.core.errors import AppError  # noqa: E402

parser = argparse.ArgumentParser(description="Ask the LMS AI assistant.")
parser.add_argument("question", nargs="?", help="leave out for an interactive conversation")
parser.add_argument("--employee", help="employee ID for personal questions, e.g. E1001")
parser.add_argument("--details", action="store_true", help="also show the facts given to the model")
args = parser.parse_args()

service = get_chat_service(get_repository(), get_llm_provider())
history: list[tuple[str, str]] = []


def ask(question: str) -> None:
    try:
        a = service.ask(question, args.employee, history)
    except AppError as error:
        print(f"Error {error.code}: {error.message}")
        return
    print(f"\n{a.answer}\n")
    understood = ", ".join(a.intents) or "-"
    print(f"[{a.provider} {a.model}, {a.duration_ms / 1000:.1f} s, understood as: {understood}]")
    for s in a.sources:
        print(
            f"  [{s.label}] {s.source}"
            + (f", page {s.page}" if s.page else "")
            + f" - {s.section} ({s.score:.2f})"
        )
    for w in a.grounding_warnings:
        print(f"  WARNING {w}")
    for n in a.notes:
        print(f"  note: {textwrap.shorten(n, 160)}")
    if args.details:
        print("\nFacts:\n" + "\n".join(f"  - {f}" for f in a.facts))
    history.extend([("user", question), ("assistant", a.answer)])


if args.question:
    ask(args.question)
else:
    print("Ask a question (empty line to stop).")
    while question := input("\nYou: ").strip():
        ask(question)
