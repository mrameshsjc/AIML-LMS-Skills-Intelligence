"""
Build and search the knowledge index (Phase 12).

BUILD  (python scripts/build_index.py)
    documents/  ->  load  ->  chunk  ->  embed  ->  vector store  ->  vector_store/<tenant>/

    Everything is written to a temporary folder first and swapped in at the
    end, so a failed build never leaves a half-written index behind, and the
    API keeps using the old one until the new one is complete.

    manifest.json records HOW the index was built: embedder and model, vector
    backend, chunk settings, and a SHA-256 fingerprint of every document. It is
    what lets a question be embedded the same way, and lets you see what the
    assistant knows.

SEARCH
    question  ->  embed (same embedder as the index)  ->  k nearest chunks
    Each result has its text, source file, section, page and similarity score.

ONE INDEX PER TENANT
    vector_store/<tenant>/ (RAG_TENANT, default "default"). In a multi-company
    LMS each customer gets its own index, so one customer's documents can
    never appear in another customer's answers.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.data_processing.loader import resolve_folder
from app.rag.chunking import Chunk, chunk_document
from app.rag.document_loader import load_folder
from app.rag.embeddings import Embedder, OllamaEmbedder, TfidfEmbedder
from app.rag.vector_store import BACKENDS, VectorStore

MANIFEST = "manifest.json"
CHUNKS = "chunks.jsonl"
INDEX_VERSION = 1


class IndexNotReadyError(RuntimeError):
    """There is no index yet, or it cannot be used with the current setup."""


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    source: str
    title: str
    section: str
    page: int | None
    text: str
    score: float

    @property
    def citation(self) -> str:
        return f"{self.source}" + (f", page {self.page}" if self.page else "") + f" ({self.section})"


@dataclass
class IndexReport:
    folder: str
    documents: int
    chunks: int
    embedder: str
    model: str
    backend: str
    seconds: float
    warnings: list[str] = field(default_factory=list)


def index_folder(vector_store_dir: str | Path, tenant: str = "default") -> Path:
    if not tenant.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Tenant name '{tenant}' may only contain letters, digits, '-' and '_'.")
    return resolve_folder(vector_store_dir) / tenant


def build_index(
    documents_dir: str | Path,
    target: Path,
    embedder: Embedder,
    backend: type[VectorStore],
    chunk_size: int = 800,
    overlap: int = 120,
) -> IndexReport:
    start = time.perf_counter()
    documents, warnings = load_folder(resolve_folder(documents_dir))
    if not documents:
        raise IndexNotReadyError(
            f"No documents found in {resolve_folder(documents_dir)} (.md, .txt, .pdf, .docx)."
        )
    chunks: list[Chunk] = [c for d in documents for c in chunk_document(d, chunk_size, overlap)]
    texts = [c.text_for_embedding for c in chunks]

    embedder.fit(texts)
    vectors = embedder.embed_documents(texts)
    store = backend()
    store.build(vectors)

    temp = target.with_name(target.name + ".building")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    store.save(temp)
    embedder.save(temp)
    with (temp / CHUNKS).open("w", encoding="utf-8", newline="\n") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    sources = resolve_folder(documents_dir)
    manifest = {
        "version": INDEX_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "embedder": {"name": embedder.name, "model": embedder.model, "dimensions": int(vectors.shape[1])},
        "backend": store.name,
        "chunk_size": chunk_size,
        "chunk_overlap": overlap,
        "chunk_count": len(chunks),
        "documents": [
            {
                "source": d.source,
                "title": d.title,
                "pages": len(d.pages),
                "chunks": sum(1 for c in chunks if c.source == d.source),
                "sha256": hashlib.sha256((sources / d.source).read_bytes()).hexdigest(),
            }
            for d in documents
        ],
        "warnings": warnings,
    }
    (temp / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    old = target.with_name(target.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    temp.rename(target)  # the swap: the new index appears complete, in one step
    shutil.rmtree(old, ignore_errors=True)
    return IndexReport(
        str(target),
        len(documents),
        len(chunks),
        embedder.name,
        embedder.model,
        store.name,
        round(time.perf_counter() - start, 2),
        warnings,
    )


def read_manifest(folder: Path) -> dict | None:
    file = folder / MANIFEST
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


class KnowledgeIndex:
    """A built index, ready to answer searches."""

    def __init__(self, manifest: dict, chunks: list[Chunk], store: VectorStore, embedder: Embedder) -> None:
        self.manifest = manifest
        self.chunks = chunks
        self.store = store
        self.embedder = embedder

    @classmethod
    def load(cls, folder: Path, ollama_embedder: OllamaEmbedder | None = None) -> KnowledgeIndex:
        """Load an index. ollama_embedder is needed if the index was built with Ollama embeddings."""
        manifest = read_manifest(folder)
        if manifest is None:
            raise IndexNotReadyError(
                f"No knowledge index in {folder}. Build it with: python scripts/build_index.py"
            )
        backend = BACKENDS.get(manifest["backend"])
        if backend is None:
            raise IndexNotReadyError(f"Unknown vector backend '{manifest['backend']}'; rebuild the index.")
        try:
            store = backend.load(folder)
        except ImportError as error:
            raise IndexNotReadyError(
                "The index was built with FAISS, which is not installed here. "
                "Run: pip install faiss-cpu, or rebuild the index with VECTOR_BACKEND=numpy."
            ) from error
        info = manifest["embedder"]
        if info["name"] == "tfidf":
            embedder: Embedder = TfidfEmbedder.load(folder)
        elif ollama_embedder is not None and ollama_embedder.model == info["model"]:
            embedder = ollama_embedder
        else:
            raise IndexNotReadyError(
                f"The index was built with Ollama embeddings ({info['model']}); questions must use the same "
                f"model. Set OLLAMA_EMBED_MODEL={info['model']}, or rebuild the index."
            )
        with (folder / CHUNKS).open(encoding="utf-8") as f:
            chunks = [Chunk(**json.loads(line)) for line in f]
        return cls(manifest, chunks, store, embedder)

    def search(self, question: str, k: int = 4) -> list[SearchResult]:
        if not question.strip():
            return []
        query = self.embedder.embed_query(question)
        results = []
        for i, score in self.store.search(query, k):
            if score <= 0:  # nothing in common with the question: not a result
                continue
            c = self.chunks[i]
            results.append(
                SearchResult(c.chunk_id, c.source, c.title, c.section, c.page, c.text, round(score, 4))
            )
        return results
