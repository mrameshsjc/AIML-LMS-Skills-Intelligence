"""
Embeddings: turn text into vectors of numbers (Phase 12).

WHAT IS AN EMBEDDING?
    A list of numbers (a vector) that represents what a text MEANS. Texts with
    similar meaning get vectors that point in similar directions, so "How many
    times can I retake a course?" lands close to "A course can be attempted up
    to 5 times", even though they share few words. Search then becomes
    "find the vectors closest to the question's vector".

TWO EMBEDDERS (EMBEDDING_PROVIDER)
    ollama   a neural embedding model served by Ollama, by default
             nomic-embed-text (~270 MB: ollama pull nomic-embed-text).
             Understands meaning and synonyms. Runs locally, like the chat model.
    tfidf    TF-IDF from scikit-learn (as for role similarity in Phase 6):
             no download, works everywhere, but matches WORDS, not meaning.
    auto     ollama when the embedding model is available, else tfidf (default).

    Why not sentence-transformers? It needs PyTorch, a multi-gigabyte install.
    Ollama already runs on the machine and serves good embedding models.

THE SAME EMBEDDER FOR INDEX AND QUESTIONS
    Vectors from different models live in different "spaces" and cannot be
    compared. The index remembers which embedder built it (manifest.json), and
    questions are always embedded with that same embedder.

NORMALISED VECTORS
    Every vector is scaled to length 1. Then the dot product of two vectors IS
    their cosine similarity (1 = same direction, 0 = unrelated), which keeps
    the search a single matrix multiplication.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.llm.base import LLMUnavailableError
from app.llm.ollama_provider import OllamaProvider


def normalise(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class Embedder(ABC):
    name = "base"
    model = ""

    def fit(self, texts: list[str]) -> None:  # noqa: B027 - only TF-IDF needs to learn from the documents
        """Learn from the document texts before embedding them (only TF-IDF needs this)."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Vectors for document chunks, shape (n, dim), normalised."""

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """Vector for a question, shape (dim,), normalised."""

    def save(self, folder: Path) -> None:  # noqa: B027 - most embedders have nothing to save
        """Store whatever is needed to embed questions later (only TF-IDF has something)."""


class OllamaEmbedder(Embedder):
    """Neural embeddings from Ollama's /api/embed endpoint."""

    name = "ollama"
    BATCH = 32  # texts per request

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout_seconds: float = 120,
        allow_remote: bool = False,
    ) -> None:
        self.model = model
        self.client = OllamaProvider(base_url, model, timeout_seconds, allow_remote=allow_remote)
        # nomic-embed-text is trained with task prefixes; using them improves search quality.
        self._doc_prefix, self._query_prefix = (
            ("search_document: ", "search_query: ") if model.startswith("nomic-embed") else ("", "")
        )

    def available(self) -> tuple[bool, str]:
        status = self.client.status()
        return status.available, status.detail

    def _embed(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for start in range(0, len(texts), self.BATCH):
            batch = texts[start : start + self.BATCH]
            reply = self.client.call("/api/embed", {"model": self.model, "input": batch})
            embeddings = reply.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise LLMUnavailableError(
                    f"Ollama returned {len(embeddings)} embeddings for {len(batch)} texts."
                )
            vectors.extend(embeddings)
        return normalise(np.array(vectors))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed([self._doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([self._query_prefix + text])[0]


class TfidfEmbedder(Embedder):
    """Word-based vectors (TF-IDF); learns its vocabulary from the documents."""

    name = "tfidf"
    model = "tfidf-1-2gram"
    FILE = "tfidf_vectorizer.joblib"

    def __init__(self, vectorizer: TfidfVectorizer | None = None) -> None:
        # Words and word pairs ("learning time"), common English words ignored, damped repeat counts.
        self.vectorizer = vectorizer or TfidfVectorizer(
            ngram_range=(1, 2), stop_words="english", sublinear_tf=True, token_pattern=r"(?u)\b[\w-]{2,}\b"
        )

    def fit(self, texts: list[str]) -> None:
        self.vectorizer.fit(texts)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return normalise(self.vectorizer.transform(texts).toarray())

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]

    def save(self, folder: Path) -> None:
        joblib.dump(self.vectorizer, folder / self.FILE)

    @classmethod
    def load(cls, folder: Path) -> TfidfEmbedder:
        return cls(joblib.load(folder / cls.FILE))
