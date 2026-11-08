"""
Document ingestion: add, update and delete knowledge documents (API 7).

PURPOSE
    Let an administrator upload a document (PDF, DOCX, TXT, CSV or Markdown)
    so the AI assistant can use it, replace it with a new version, or remove it.

WHERE FILES GO
    Uploads are stored in RAG_UPLOAD_DIR (default data/uploads/documents),
    NOT in documents/. The approved base documents can therefore never be
    replaced or deleted through the API, and uploads survive container
    rebuilds on the Docker data volume.

STEP BY STEP (upload)
    1. Name        keep only the file name; unsafe characters become "_"
                   (a name like "../../app/main.py" cannot escape the folder).
    2. Checks      supported type, not empty, not larger than RAG_MAX_UPLOAD_MB.
    3. Conflicts   same name as an approved document -> refused;
                   same name as an upload -> refused unless overwrite=true (an update);
                   same CONTENT as any document under another name -> refused (duplicate).
    4. Validate    extract the text first; a damaged or scanned file is refused
                   before anything is stored.
    5. Store + rebuild  save the file and rebuild the index. If the rebuild fails,
                   the change is rolled back: the old file and the old index stay.

WHY A FULL REBUILD
    With ~150 chunks a rebuild takes well under a second (a few seconds with
    Ollama embeddings), it keeps TF-IDF vocabularies consistent, and it has
    one simple, testable code path. Incremental updates are a later optimisation.

ONE CHANGE AT A TIME
    A lock makes uploads and deletions wait for each other, so two requests can
    never rebuild the index at the same moment (within one API process).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
)
from app.data_processing.loader import resolve_folder
from app.llm.base import LLMUnavailableError
from app.rag.document_loader import SUPPORTED, DocumentError, load_document
from app.rag.embeddings import Embedder
from app.rag.index import IndexNotReadyError, IndexReport, build_index, read_manifest
from app.rag.vector_store import VectorStore
from app.security.prompt_injection import find_injection
from app.security.uploads import content_problem

_LOCK = threading.Lock()


@dataclass(frozen=True)
class IngestResult:
    source: str
    title: str
    pages: int
    chunks: int
    sha256: str
    status: str  # added | updated | deleted
    index: IndexReport
    notes: list[str] = field(default_factory=list)


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{n / 1024:.0f} KB"


def safe_name(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    if not name or len(name) > 120:
        raise InvalidInputError("INVALID_FILE_NAME", "The file name is empty or longer than 120 characters.")
    return name


class IngestionService:
    def __init__(
        self,
        documents_dir: str | Path,
        upload_dir: str | Path,
        index_dir: Path,
        choose_embedder: Callable[[], tuple[Embedder, list[str]]],
        backend: type[VectorStore],
        chunk_size: int = 800,
        overlap: int = 120,
        max_bytes: int = 10 * 1024 * 1024,
        on_change: Callable[[], None] = lambda: None,
        block_injection: bool = True,
    ) -> None:
        self.documents_dir = resolve_folder(documents_dir)
        self.upload_dir = resolve_folder(upload_dir)
        self.index_dir = index_dir
        self.choose_embedder = choose_embedder
        self.backend = backend
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_bytes = max_bytes
        self.on_change = on_change  # e.g. tell the API to reload the index
        self.block_injection = block_injection  # Phase 17: refuse documents with hidden instructions

    # --- upload / update ---------------------------------------------------------------------
    def ingest(self, filename: str, content: bytes, overwrite: bool = False) -> IngestResult:
        name = safe_name(filename)
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED:
            raise InvalidInputError(
                "UNSUPPORTED_FILE_TYPE",
                f"'{suffix or name}' is not supported. Use: {', '.join(sorted(SUPPORTED))}.",
            )
        if not content:
            raise InvalidInputError("EMPTY_FILE", f"{name} is empty.")
        if len(content) > self.max_bytes:
            raise PayloadTooLargeError(
                "FILE_TOO_LARGE",
                f"{name} is {_size(len(content))}; the limit is {_size(self.max_bytes)}.",
            )
        problem = content_problem(suffix, content)  # Phase 17: the content must match the extension
        if problem:
            raise InvalidInputError("FILE_CONTENT_MISMATCH", f"{name} was refused: {problem}.")
        if (self.documents_dir / name).exists():
            raise ConflictError(
                "DOCUMENT_IS_APPROVED",
                f"{name} is an approved base document and cannot be replaced through the API.",
            )
        target = self.upload_dir / name
        if target.exists() and not overwrite:
            raise ConflictError(
                "DOCUMENT_EXISTS", f"{name} already exists. Send overwrite=true to replace it."
            )
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self._same_content(digest, ignore=name)
        if duplicate:
            raise ConflictError("DUPLICATE_DOCUMENT", f"{name} has the same content as {duplicate}.")

        self.upload_dir.mkdir(parents=True, exist_ok=True)
        temp = self.upload_dir / f".upload-{uuid.uuid4().hex}{suffix}"
        temp.write_bytes(content)
        try:
            document = load_document(temp)
        except DocumentError as error:
            temp.unlink(missing_ok=True)
            raise InvalidInputError("INVALID_DOCUMENT", str(error).replace(temp.name, name)) from error
        found = find_injection("\n".join(p.text for p in document.pages)) if self.block_injection else []
        if found:  # Phase 17: text written to manipulate the assistant, not to inform it
            temp.unlink(missing_ok=True)
            raise InvalidInputError(
                "INJECTION_SUSPECTED",
                f"{name} was refused: it contains text that tries to instruct the AI assistant "
                f"({', '.join(sorted(set(found)))}). Remove it and upload again.",
            )

        status = "updated" if target.exists() else "added"
        with _LOCK:
            backup = self._backup(target)
            temp.replace(target)
            try:
                report = self._rebuild()
            except Exception:
                target.unlink(missing_ok=True)
                self._restore(backup, target)
                raise
            self._discard(backup)
        self.on_change()
        entry = next(d for d in read_manifest(self.index_dir)["documents"] if d["source"] == name)
        return IngestResult(
            name,
            entry["title"],  # from the index: the title of the stored file
            len(document.pages),
            entry["chunks"],
            digest,
            status,
            report,
            self._notes(report),
        )

    # --- delete -----------------------------------------------------------------------------
    def delete(self, source: str) -> IngestResult:
        name = safe_name(source)
        target = self.upload_dir / name
        if not target.exists():
            if (self.documents_dir / name).exists():
                raise ConflictError(
                    "DOCUMENT_IS_APPROVED",
                    f"{name} is an approved base document and cannot be deleted through the API.",
                )
            raise NotFoundError("DOCUMENT_NOT_FOUND", f"No uploaded document named {name}.")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        with _LOCK:
            backup = self._backup(target)
            try:
                report = self._rebuild()
            except Exception:
                self._restore(backup, target)
                raise
            self._discard(backup)
        self.on_change()
        return IngestResult(name, name, 0, 0, digest, "deleted", report, self._notes(report))

    # --- helpers ------------------------------------------------------------------------------
    def _same_content(self, digest: str, ignore: str) -> str | None:
        for folder in (self.documents_dir, self.upload_dir):
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if path.is_file() and path.name != ignore and not path.name.startswith("."):
                    if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                        return path.name
        return None

    def _rebuild(self) -> IndexReport:
        embedder, _ = self.choose_embedder()
        try:
            return build_index(
                self.documents_dir,
                self.index_dir,
                embedder,
                self.backend,
                self.chunk_size,
                self.overlap,
                upload_dir=self.upload_dir,
            )
        except (LLMUnavailableError, IndexNotReadyError, OSError) as error:
            raise ServiceUnavailableError(
                "INDEX_BUILD_FAILED", f"The index could not be rebuilt: {error}"
            ) from error

    @staticmethod
    def _backup(target: Path) -> Path | None:
        if not target.exists():
            return None
        backup = target.with_name(f".backup-{uuid.uuid4().hex}-{target.name}")
        shutil.move(target, backup)
        return backup

    @staticmethod
    def _restore(backup: Path | None, target: Path) -> None:
        if backup is not None and backup.exists():
            shutil.move(backup, target)

    @staticmethod
    def _discard(backup: Path | None) -> None:
        if backup is not None:
            backup.unlink(missing_ok=True)

    @staticmethod
    def _notes(report: IndexReport) -> list[str]:
        notes = [f"Index rebuilt: {report.documents} documents, {report.chunks} chunks ({report.embedder})."]
        return notes + [f"Skipped: {w}" for w in report.warnings]
