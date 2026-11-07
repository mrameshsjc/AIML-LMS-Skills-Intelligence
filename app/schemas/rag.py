"""Response shapes for API 7 (document ingestion) and the document list."""

from pydantic import BaseModel, Field


class IndexSummaryOut(BaseModel):
    documents: int
    chunks: int
    embedder: str = Field(examples=["ollama"])
    embedding_model: str = Field(examples=["nomic-embed-text"])
    backend: str = Field(examples=["faiss"])
    seconds: float = Field(description="How long the rebuild took.")


class IngestResponse(BaseModel):
    status: str = Field(examples=["added"], description="added, updated or deleted.")
    source: str = Field(examples=["internal_trainings.csv"])
    title: str
    pages: int
    chunks: int = Field(description="Chunks created from this document.")
    sha256: str = Field(description="Fingerprint of the file, used to detect duplicates.")
    index: IndexSummaryOut
    notes: list[str]


class DocumentOut(BaseModel):
    source: str
    title: str
    origin: str = Field(description="base (approved folder, read-only) or uploaded (API 7).")
    pages: int
    chunks: int
    sha256: str


class DocumentListResponse(BaseModel):
    ready: bool
    tenant: str
    embedder: str | None = None
    embedding_model: str | None = None
    backend: str | None = None
    built_at: str | None = None
    chunk_count: int = 0
    documents: list[DocumentOut] = []
    warnings: list[str] = Field(default=[], description="Files skipped at the last build, with the reason.")
