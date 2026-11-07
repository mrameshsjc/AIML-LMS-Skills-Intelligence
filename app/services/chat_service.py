"""
The LMS AI assistant: answer questions with engine data + documents (API 5).

PURPOSE
    Answer questions such as "What are my current skill gaps?", "Which skills
    does an AI Engineer need?" or "How many learning hours do I have?" -
    correctly, with sources, and without inventing anything.

TWO KINDS OF KNOWLEDGE
    Engine facts   exact data from the LMS: the employee's gaps and learning
                   path (APIs 1-4), role requirements, course details.
    Documents      passages found by the knowledge search (Phase 12): policies,
                   FAQ, guides. Labelled [S1], [S2] ... so the answer can cite them.

STEP BY STEP
    1. Understand  simple, explainable rules - no hidden model decides:
                     - a job role named in the question (e.g. "AI Engineer")  -> its requirements
                     - a skill named (e.g. "Python")                           -> courses that raise it
                     - a course ID (e.g. C-SQL-201)                            -> its details
                     - "my", "I", "me" + an employee_id                        -> their learning path
                       (toward the role named in the question, if any)
    2. Retrieve    search the documents; keep passages above the minimum score.
    3. Refuse      if there are no facts and no relevant passages, say so - without
                   calling the language model at all (nothing to ground an answer in).
    4. Answer      the LLM writes the answer from the facts only, citing [S1] etc.
    5. Check       guardrails flag invented course IDs, numbers and citations.

WHY RULES FOR STEP 1 (AND NOT THE LLM)
    Every decision is visible in the response ("intents") and testable. A small
    local model choosing tools would be slower and less predictable. The rules
    cover the question types in the requirements; documents cover the rest.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.errors import ServiceUnavailableError
from app.domain.models import JobRole, Skill
from app.llm.base import LLMProvider, LLMRequest, LLMUnavailableError
from app.llm.guardrails import check_grounding
from app.rag.index import IndexNotReadyError, KnowledgeIndex
from app.repositories.base import LmsRepository
from app.services.explanation_service import learning_path_facts
from app.services.learning_path import LearningPathService
from app.services.training_recommendation import CompletionModel

PERSONAL = re.compile(r"\b(i|me|my|mine|myself|i'm|im|am i)\b", re.IGNORECASE)
# Words that ask about the employee's own LMS data (gaps, path, recommendations). Not "skills" or "level":
# "Which skills does an AI Engineer need?" is a question about the role, even when an employee asks it.
MY_DATA = re.compile(r"\b(recommend\w*|next|gaps?|learning path|path|progress|ready)\b", re.IGNORECASE)
COURSE_ID = re.compile(r"\bC-[A-Z0-9]+-\d{3}\b", re.IGNORECASE)
ROLE_ID = re.compile(r"\bR\d{3}\b")
CITATION = re.compile(r"\[S(\d+)\]")
RELATIVE_CUTOFF = 0.5  # keep passages scoring at least half as high as the best one
NO_INFORMATION = (
    "I don't have information about that in the LMS data or the approved documents. "
    "You can ask about your skill gaps and learning path, the skills a job role needs, "
    "courses for a skill, or the learning policies."
)


@dataclass(frozen=True)
class Source:
    label: str  # S1, S2, ...
    source: str
    title: str
    section: str
    page: int | None
    score: float
    text: str


@dataclass(frozen=True)
class ChatAnswer:
    question: str
    answer: str
    provider: str  # ollama | fallback | none (refused before calling a model)
    model: str
    is_fallback: bool
    intents: list[str]
    sources: list[Source]
    facts: list[str]  # the engine facts given to the model
    grounding_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    duration_ms: int = 0
    employee_id: str | None = None


def _find_names(text: str, names: dict[str, str], limit: int) -> list[str]:
    """IDs of names that appear in text as whole words; longest names first, no overlaps."""
    lowered, found = text.lower(), []
    for name in sorted(names, key=len, reverse=True):
        match = re.search(rf"(?<![\w-]){re.escape(name.lower())}(?![\w-])", lowered)
        if match and len(found) < limit:
            found.append(names[name])
            lowered = lowered[: match.start()] + " " * len(name) + lowered[match.end() :]
    return found


class ChatService:
    def __init__(
        self,
        repository: LmsRepository,
        llm: LLMProvider,
        index_loader: Callable[[], KnowledgeIndex | None] | None = None,
        min_score: Callable[[KnowledgeIndex], float] = lambda index: 0.05,
        top_k: int = 4,
        completion_model: CompletionModel | None = None,
    ) -> None:
        self.repo = repository
        self.llm = llm
        self.index_loader = index_loader or (lambda: None)
        self.min_score = min_score
        self.top_k = top_k
        self.paths = LearningPathService(repository, completion_model)

    # --- public -------------------------------------------------------------------------
    def ask(
        self, question: str, employee_id: str | None = None, history: list[tuple[str, str]] | None = None
    ) -> ChatAnswer:
        start = time.perf_counter()
        question = " ".join(question.split())
        history = history or []
        facts, intents, notes = self._engine_facts(question, employee_id)
        sources = self._retrieve(self._search_text(question, history), notes)
        if sources:
            intents.append("documents")

        if not facts and not sources:
            elapsed = int((time.perf_counter() - start) * 1000)
            return ChatAnswer(
                question,
                NO_INFORMATION,
                "none",
                "none",
                False,
                intents,
                [],
                [],
                [],
                notes,
                elapsed,
                employee_id,
            )

        context = facts + [f"[{s.label}] {s.title}, {self._where(s)}: {s.text}" for s in sources]
        instruction = (
            f"Question from the employee: {question}\n"
            "Answer using only the facts above. Cite document facts with their label, e.g. [S1]."
        )
        try:
            result = self.llm.generate(LLMRequest(instruction=instruction, context=context, history=history))
        except LLMUnavailableError as error:  # only with LLM_PROVIDER=ollama; "auto" falls back instead
            raise ServiceUnavailableError("LLM_UNAVAILABLE", str(error)) from error

        warnings: list[str] = []
        if not result.is_fallback:
            warnings = check_grounding(result.text, context)
            labels = {s.label for s in sources}
            unknown = sorted({f"S{n}" for n in CITATION.findall(result.text)} - labels)
            if unknown:
                warnings.append(f"The answer cites sources that do not exist: {', '.join(unknown)}.")
        return ChatAnswer(
            question=question,
            answer=result.text,
            provider=result.provider,
            model=result.model,
            is_fallback=result.is_fallback,
            intents=intents,
            sources=sources,
            facts=facts,
            grounding_warnings=warnings,
            notes=notes + result.notes,
            duration_ms=int((time.perf_counter() - start) * 1000),
            employee_id=employee_id,
        )

    # --- 1. engine facts ------------------------------------------------------------------
    def _engine_facts(self, question: str, employee_id: str | None) -> tuple[list[str], list[str], list[str]]:
        facts: list[str] = []
        intents: list[str] = []
        notes: list[str] = []
        roles = {r.title: r.role_id for r in self.repo.list_roles()}
        role_ids = [rid for rid in ROLE_ID.findall(question) if self.repo.get_role(rid)]
        role_ids = list(dict.fromkeys(role_ids + _find_names(question, roles, 2)))[:2]
        skills = self.repo.get_skills()
        skill_ids = _find_names(question, {s.name: sid for sid, s in skills.items()}, 3)
        courses = self.repo.get_courses()
        course_ids = [
            c for c in dict.fromkeys(m.upper() for m in COURSE_ID.findall(question)) if c in courses
        ][:3]
        about_my_data = bool(MY_DATA.search(question)) or bool(course_ids)
        # "my"/"I" always counts; with an employee_id, "Why was X recommended?" or "What next?" counts too.
        personal = bool(PERSONAL.search(question)) or (employee_id is not None and about_my_data)

        if personal and employee_id:
            target = role_ids[0] if role_ids else None
            path = self.paths.build(employee_id, target)
            facts += learning_path_facts(path)
            if re.search(r"\bwhy\b", question, re.IGNORECASE) or course_ids:
                facts += [
                    f"Why step {s.step} ({s.course.course_id}) is in the path: {s.reason}"
                    for s in path.steps
                    if not course_ids or s.course.course_id in course_ids
                ]
            intents.append("my_learning_path")
            role_ids = role_ids[1:]  # the target role is already covered by the path
        elif personal and about_my_data:
            notes.append(
                "This sounds like a question about you: send employee_id for answers about your own data."
            )

        for rid in role_ids:
            facts += self._role_facts(self.repo.get_role(rid), skills)
        if role_ids:
            intents.append("role_requirements")

        levels = self.repo.get_employee_skills(employee_id) if employee_id else {}
        history = self.repo.get_training_status(employee_id) if employee_id else {}
        for sid in skill_ids:
            facts += self._skill_course_facts(skills[sid], courses, levels if employee_id else None, history)
        if skill_ids:
            intents.append("skill_courses")

        for cid in course_ids:
            facts += self._course_facts(cid, courses, skills, history.get(cid) if employee_id else None)
        if course_ids:
            intents.append("course_details")
        return list(dict.fromkeys(facts)), intents, notes

    def _role_facts(self, role: JobRole, skills: dict[str, Skill]) -> list[str]:
        reqs = self.repo.get_role_requirements(role.role_id)
        mandatory = [f"{skills[r.skill_id].name} level {r.required_level}" for r in reqs if r.mandatory]
        optional = [f"{skills[r.skill_id].name} level {r.required_level}" for r in reqs if not r.mandatory]
        return [
            f"Job role {role.title} ({role.role_id}): {role.seniority}-level, {role.department} department.",
            f"{role.title} mandatory skills: {', '.join(mandatory) or 'none'}.",
            f"{role.title} optional skills: {', '.join(optional) or 'none'}.",
        ]

    def _skill_course_facts(self, skill, courses, levels, history) -> list[str]:
        facts = []
        if levels is not None:
            facts.append(f"The employee's current {skill.name} level: {levels.get(skill.skill_id, 0)}.")
        options = []
        for cid, course in courses.items():
            if not course.is_active or history.get(cid) == "Completed":
                continue
            for cs in self.repo.get_course_skills(cid):
                if cs.skill_id == skill.skill_id and (
                    levels is None or cs.level_to > levels.get(cs.skill_id, 0)
                ):
                    options.append((cs.level_from, cid, cs))
        for _, cid, cs in sorted(options)[:5]:
            course = courses[cid]
            prereqs = ", ".join(self.repo.get_prerequisites(cid)) or "none"
            facts.append(
                f"Course {cid} '{course.title}' raises {skill.name} from level {cs.level_from} "
                f"to {cs.level_to} ({course.duration_hours} hours, {course.difficulty}; "
                f"prerequisites: {prereqs})."
            )
        if not options:
            facts.append(
                f"No available course raises {skill.name}" + (" above the current level." if levels else ".")
            )
        return facts

    def _course_facts(self, cid, courses, skills, status) -> list[str]:
        course = courses[cid]
        raises = "; ".join(
            f"{skills[cs.skill_id].name} {cs.level_from}->{cs.level_to}"
            for cs in self.repo.get_course_skills(cid)
        )
        facts = [
            f"Course {cid} '{course.title}': {course.difficulty}, {course.duration_hours} hours, "
            f"{course.delivery_mode}, by {course.provider}. Raises {raises}. "
            f"Prerequisites: {', '.join(self.repo.get_prerequisites(cid)) or 'none'}."
        ]
        if status:
            facts.append(f"The employee's status for {cid}: {status}.")
        return facts

    # --- 2. documents -----------------------------------------------------------------------
    @staticmethod
    def _search_text(question: str, history: list[tuple[str, str]]) -> str:
        """A short follow-up ("and Docker?") is searched together with the previous question."""
        previous = next((text for role, text in reversed(history) if role == "user"), "")
        return f"{previous} {question}" if previous and len(question.split()) < 6 else question

    def _retrieve(self, text: str, notes: list[str]) -> list[Source]:
        try:
            index = self.index_loader()
        except IndexNotReadyError as error:
            notes.append(f"Document search is not available: {error}")
            return []
        if index is None:
            notes.append(
                "No document index yet (python scripts/build_index.py): answering from LMS data only."
            )
            return []
        try:
            results = index.search(text, self.top_k)
        except LLMUnavailableError as error:
            notes.append(f"Document search is not available right now: {error}")
            return []
        if not results:
            return []
        # Absolute minimum (by embedder) AND close to the best match: weak passages only add noise.
        threshold = max(self.min_score(index), RELATIVE_CUTOFF * results[0].score)
        kept = [r for r in results if r.score >= threshold]
        return [
            Source(f"S{i}", r.source, r.title, r.section, r.page, r.score, r.text)
            for i, r in enumerate(kept, start=1)
        ]

    @staticmethod
    def _where(s: Source) -> str:
        section = s.section.split(" > ", 1)[1] if " > " in s.section else s.section
        return f"section '{section}'" + (f", page {s.page}" if s.page else "")
