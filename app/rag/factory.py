"""
Turn settings into RAG components (Phase 12).

    choose_embedder(settings)   which embedder BUILDS a new index
                                (EMBEDDING_PROVIDER: auto / ollama / tfidf)
    load_index(settings)        the saved index for RAG_TENANT, ready to search
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.rag.embeddings import Embedder, OllamaEmbedder, TfidfEmbedder
from app.rag.index import KnowledgeIndex, index_folder


def ollama_embedder(settings: Settings) -> OllamaEmbedder:
    return OllamaEmbedder(
        settings.ollama_base_url,
        settings.ollama_embed_model,
        settings.llm_timeout_seconds,
        allow_remote=settings.llm_allow_remote,
    )


def choose_embedder(settings: Settings) -> tuple[Embedder, list[str]]:
    """The embedder for building an index, and notes explaining the choice."""
    if settings.embedding_provider == "tfidf":
        return TfidfEmbedder(), ["EMBEDDING_PROVIDER=tfidf: word-based TF-IDF vectors (no model needed)."]
    embedder = ollama_embedder(settings)
    available, detail = embedder.available()
    if available:
        return embedder, [f"Ollama embeddings with {embedder.model}."]
    if settings.embedding_provider == "ollama":
        raise RuntimeError(f"EMBEDDING_PROVIDER=ollama, but: {detail}")
    return TfidfEmbedder(), [
        f"Ollama embeddings not available ({detail}). Using TF-IDF instead: it matches words, not meaning. "
        f"For better search: ollama pull {embedder.model}, then rebuild the index."
    ]


def tenant_folder(settings: Settings) -> Path:
    return index_folder(settings.vector_store_dir, settings.rag_tenant)


def load_index(settings: Settings) -> KnowledgeIndex:
    return KnowledgeIndex.load(tenant_folder(settings), ollama_embedder(settings))


DEFAULT_MIN_SCORE = {"tfidf": 0.08, "ollama": 0.45}


def min_score(settings: Settings, index: KnowledgeIndex) -> float:
    """Passages below this similarity are not relevant enough to use (RAG_MIN_SCORE, else by embedder)."""
    if settings.rag_min_score is not None:
        return settings.rag_min_score
    return DEFAULT_MIN_SCORE.get(index.manifest["embedder"]["name"], 0.3)
