"""
Guardrails for LLM input and output (Phase 11).

TWO SIMPLE PROTECTIONS
    1. redact()           removes e-mail addresses and phone numbers from text
                          BEFORE it goes to a model. Even a local model should
                          only see what it needs; this matters even more if a
                          hosted model is ever used (the requirements forbid
                          sending confidential data to external AI without
                          approval).
    2. check_grounding()  AFTER the model answers, looks for numbers and course
                          IDs that do not appear in the facts it was given.
                          Small models sometimes invent a level ("level 5") or
                          a course ("C-SQL-301"); this catches the obvious cases
                          and the warnings are returned with the answer.

    These are simple pattern checks, not a guarantee. They make the most common
    failures visible instead of silent. Phase 17 adds prompt-injection checks.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
COURSE_ID = re.compile(r"\bC-[A-Z0-9]+-\d{3}\b")
NUMBER = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w])")


def redact(text: str) -> str:
    """Replace e-mail addresses and phone numbers with placeholders."""
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


def _numbers(text: str) -> set[str]:
    found = set()
    for n in NUMBER.findall(text):
        value = float(n)
        found.add(f"{value:g}")
    return found


def check_grounding(answer: str, context: list[str]) -> list[str]:
    """Warnings for course IDs and numbers in the answer that are not in the context."""
    facts = "\n".join(context)
    warnings = []
    unknown_courses = sorted(set(COURSE_ID.findall(answer)) - set(COURSE_ID.findall(facts)))
    if unknown_courses:
        warnings.append(f"The answer mentions courses not in the facts: {', '.join(unknown_courses)}.")
    # Small numbers (0-5) are skill levels and step counts that appear naturally ("step 1", "3 courses").
    known = _numbers(facts) | {str(i) for i in range(6)}
    unknown_numbers = sorted(_numbers(answer) - known, key=float)
    if unknown_numbers:
        warnings.append(f"The answer contains numbers not in the facts: {', '.join(unknown_numbers)}.")
    return warnings
