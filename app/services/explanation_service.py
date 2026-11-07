"""
Plain-language explanations with an LLM (Phase 11).

PURPOSE
    The engine's answers are exact but technical: gap 2, score 0.41, after
    step 3. This service asks the language model to explain them to the
    employee in a few friendly sentences, WITHOUT letting it invent anything.

HOW (the same pattern the RAG assistant uses in Phase 13)
    1. Facts      turn the learning path (API 4) into short factual lines.
    2. Ask        send the facts + an instruction to the LLM provider
                  (Ollama, or the labelled fallback when no model is available).
    3. Check      guardrails.check_grounding() flags course IDs and numbers in
                  the answer that are not in the facts.
    4. Return     the text, which provider/model wrote it, the facts it was
                  given and any warnings - so a reader can always verify it.

PRIVACY
    Only what the explanation needs is sent: the first name, roles, skills,
    courses. No e-mail, manager or location; redact() removes e-mails and
    phone numbers as a second line of defence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import ServiceUnavailableError
from app.llm.base import LLMProvider, LLMRequest, LLMUnavailableError
from app.llm.guardrails import check_grounding
from app.services.learning_path import LearningPath, LearningPathService

INSTRUCTION = (
    "Explain this learning path to {name} in a short, encouraging paragraph: where they are now, "
    "the most important gaps for {target}, the order of the courses and why, and what to do first."
)


@dataclass(frozen=True)
class Explanation:
    text: str
    provider: str
    model: str
    is_fallback: bool
    duration_ms: int
    facts: list[str]
    grounding_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def learning_path_facts(path: LearningPath) -> list[str]:
    """The learning path as short factual lines - the ONLY information the model receives."""
    first_name = path.employee_name.split()[0]
    target = path.target_role.title
    source = {
        "career_goal": "their career goal",
        "request": "the request",
        "current_role": "their current role",
    }
    p = path.progress
    facts = [
        f"Employee first name: {first_name}.",
        f"Current role: {path.current_role.title}. "
        f"Target role: {target} (from {source[path.target_source]}).",
        f"Match with {target} now: {p.match_percentage:g}%. After completing the path: "
        f"{p.projected_match_percentage:g}%. Skills already met: {p.skills_met} of {p.skills_required}.",
    ]
    for g in path.gaps:
        kind = "mandatory" if g.gap.mandatory else "optional"
        facts.append(
            f"Gap ({kind}): {g.gap.skill_name} is level {g.gap.current_level}, {target} needs level "
            f"{g.gap.required_level}."
        )
    for s in path.steps:
        raises = ", ".join(f"{r.skill_name} {r.level_from}->{r.level_to}" for r in s.raises)
        after = f" Take it after step {', '.join(map(str, s.after_steps))}." if s.after_steps else ""
        facts.append(
            f"Step {s.step}: {s.course.course_id} '{s.course.title}' ({s.course.duration_hours} hours, "
            f"{s.course.difficulty}). Raises {raises}. Status: {s.status}.{after}"
        )
    if path.steps:
        facts.append(f"The path has {p.total_steps} steps and {p.total_hours} hours in total.")
    if p.completed_courses:
        facts.append(
            "Already completed: " + ", ".join(f"{c.course_id} '{c.title}'" for c in p.completed_courses) + "."
        )
    if path.uncovered_skills:
        facts.append("No available course fully closes: " + ", ".join(path.uncovered_skills) + ".")
    facts.append(f"Next action: {path.next_action}")
    return facts


class ExplanationService:
    def __init__(self, learning_paths: LearningPathService | None, llm: LLMProvider) -> None:
        self.learning_paths = learning_paths
        self.llm = llm

    def explain_learning_path(self, employee_id: str, target_role_id: str | None = None) -> Explanation:
        return self.explain_path(self.learning_paths.build(employee_id, target_role_id))

    def explain_path(self, path: LearningPath) -> Explanation:
        """Explain a learning path that has already been built (API 4 uses this with ?explain=true)."""
        facts = learning_path_facts(path)
        instruction = INSTRUCTION.format(name=path.employee_name.split()[0], target=path.target_role.title)
        try:
            result = self.llm.generate(LLMRequest(instruction=instruction, context=facts))
        except LLMUnavailableError as error:  # only with LLM_PROVIDER=ollama; "auto" falls back instead
            raise ServiceUnavailableError("LLM_UNAVAILABLE", str(error)) from error
        warnings = [] if result.is_fallback else check_grounding(result.text, facts)
        return Explanation(
            text=result.text,
            provider=result.provider,
            model=result.model,
            is_fallback=result.is_fallback,
            duration_ms=result.duration_ms,
            facts=facts,
            grounding_warnings=warnings,
            notes=result.notes,
        )
