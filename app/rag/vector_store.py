"""
Vector stores: keep the chunk vectors and find the nearest ones (Phase 12).

TWO BACKENDS (VECTOR_BACKEND)
    numpy   exact search: one matrix multiplication of the question vector with
            every chunk vector. Simple and exact; fast enough for tens of
            thousands of chunks (the sample has about 130).
    faiss   FAISS (Facebook AI Similarity Search), a library built for millions
            of vectors. IndexFlatIP is also exact; FAISS's approximate indexes
            (IVF, HNSW) are the next step when collections grow large.
            Needs: pip install faiss-cpu
    auto    faiss if it is installed, else numpy (default).

    Both give the SAME results for the same vectors (a test checks this when
    FAISS is installed), so the choice is only about scale.

ON DISK (one folder per index)
    vectors.npy or index.faiss    the vectors
    chunks.jsonl                  one chunk (text, source, section, page) per line
"""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


def faiss_installed() -> bool:
    return importlib.util.find_spec("faiss") is not None


class VectorStore(ABC):
    name = "base"

    @abstractmethod
    def build(self, vectors: np.ndarray) -> None:
        """Store the (normalised) chunk vectors, row i = chunk i."""

    @abstractmethod
    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        """(chunk index, cosine similarity) of the k nearest chunks, best first."""

    @abstractmethod
    def save(self, folder: Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, folder: Path) -> VectorStore: ...


class NumpyVectorStore(VectorStore):
    name = "numpy"
    FILE = "vectors.npy"

    def __init__(self, vectors: np.ndarray | None = None) -> None:
        self.vectors = np.zeros((0, 0), dtype=np.float32) if vectors is None else vectors

    def build(self, vectors: np.ndarray) -> None:
        self.vectors = np.asarray(vectors, dtype=np.float32)

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        if len(self.vectors) == 0:
            return []
        scores = self.vectors @ query  # cosine similarity, because all vectors have length 1
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]  # the k best, unordered (faster than sorting all)
        top = top[np.argsort(-scores[top], kind="stable")]
        return [(int(i), float(scores[i])) for i in top]

    def save(self, folder: Path) -> None:
        np.save(folder / self.FILE, self.vectors)

    @classmethod
    def load(cls, folder: Path) -> NumpyVectorStore:
        return cls(np.load(folder / cls.FILE))


class FaissVectorStore(VectorStore):
    name = "faiss"
    FILE = "index.faiss"

    def __init__(self, index=None) -> None:
        self.index = index

    def build(self, vectors: np.ndarray) -> None:
        import faiss

        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        self.index = faiss.IndexFlatIP(vectors.shape[1])  # inner product = cosine for normalised vectors
        self.index.add(vectors)

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []
        scores, ids = self.index.search(np.ascontiguousarray(query.reshape(1, -1), dtype=np.float32), k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0], strict=True) if i >= 0]

    def save(self, folder: Path) -> None:
        import faiss

        faiss.write_index(self.index, str(folder / self.FILE))

    @classmethod
    def load(cls, folder: Path) -> FaissVectorStore:
        import faiss

        return cls(faiss.read_index(str(folder / cls.FILE)))


BACKENDS: dict[str, type[VectorStore]] = {"numpy": NumpyVectorStore, "faiss": FaissVectorStore}


def choose_backend(setting: str) -> type[VectorStore]:
    if setting == "faiss" and not faiss_installed():
        raise RuntimeError("VECTOR_BACKEND=faiss, but FAISS is not installed. Run: pip install faiss-cpu")
    if setting == "auto":
        return FaissVectorStore if faiss_installed() else NumpyVectorStore
    return BACKENDS[setting]
