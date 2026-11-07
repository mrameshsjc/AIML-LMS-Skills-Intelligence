"""
Role similarity: which job roles need similar skills? (TF-IDF + cosine similarity)

PURPOSE
    Suggest related roles. If an employee targets Data Engineer, roles with a
    similar skill profile (for example Machine Learning Engineer) are natural
    alternatives or next steps.

HOW IT WORKS - IN THREE STEPS
    1. Describe each role as a "document" of skill tokens, each repeated by
       its required level. Data Engineer (Python 4, SQL 4, AWS 3, ML 2,
       Docker 3) becomes:
           "SK001 SK001 SK001 SK001 SK004 SK004 SK004 SK004 SK017 SK017 ..."
       A higher required level means the skill appears more often, so it
       counts more.

    2. TF-IDF turns each document into numbers:
         TF  (term frequency)          how often the skill appears in THIS role
         IDF (inverse document freq.)  how RARE the skill is across ALL roles
       A skill that almost every role needs (like Communication) gets a low
       IDF, so it says little about what makes a role special. A skill only a
       few roles need (like MLOps) gets a high IDF. TF x IDF is large for
       skills that are important to a role AND distinctive.

    3. Cosine similarity compares two roles' number lists:
           1.0 = identical skill profiles, 0.0 = no skills in common.
       It measures the angle between two vectors, so a role with many
       requirements and one with few can still be very similar.

WHY TF-IDF HERE (AND NOT AN LLM OR EMBEDDINGS)
    The roles are described by a small, structured skill list. TF-IDF is
    exact, explainable (the shared skills are the reason), fast, and needs no
    model download. Text embeddings become useful in Phase 12, for free-text
    documents.

LIBRARY
    scikit-learn: TfidfVectorizer builds the TF-IDF numbers; cosine_similarity
    compares them.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.domain.models import JobRole, RoleRequirement


@dataclass(frozen=True)
class SimilarRole:
    role: JobRole
    similarity: float  # 0..1, rounded to 2 decimals
    shared_skill_ids: list[str]


def role_document(requirements: list[RoleRequirement]) -> str:
    """One role as text: each required skill ID repeated by its required level."""
    return " ".join(r.skill_id for r in requirements for _ in range(r.required_level))


class RoleSimilarityIndex:
    """Pre-computes the similarity of every pair of roles once."""

    def __init__(self, roles: list[JobRole], requirements: dict[str, list[RoleRequirement]]) -> None:
        self.roles = sorted(roles, key=lambda r: r.role_id)
        self._position = {r.role_id: i for i, r in enumerate(self.roles)}
        self._skills = {r.role_id: {q.skill_id for q in requirements.get(r.role_id, [])} for r in self.roles}

        documents = [role_document(requirements.get(r.role_id, [])) for r in self.roles]
        # token_pattern=r"\S+" : every space-separated word is a token (our skill IDs).
        # lowercase=False      : keep IDs exactly as written.
        self.vectorizer = TfidfVectorizer(token_pattern=r"\S+", lowercase=False)
        matrix = self.vectorizer.fit_transform(documents)
        self.similarity = cosine_similarity(matrix)  # a roles x roles table of scores

    def similar_to(self, role_id: str, top_n: int = 3, min_similarity: float = 0.05) -> list[SimilarRole]:
        """The most similar other roles, best first. Unknown role -> empty list."""
        if role_id not in self._position:
            return []
        row = self.similarity[self._position[role_id]]
        candidates = [
            SimilarRole(
                other, round(float(row[i]), 2), sorted(self._skills[role_id] & self._skills[other.role_id])
            )
            for i, other in enumerate(self.roles)
            if other.role_id != role_id and row[i] >= min_similarity
        ]
        candidates.sort(key=lambda c: (-c.similarity, c.role.title))
        return candidates[:top_n]
