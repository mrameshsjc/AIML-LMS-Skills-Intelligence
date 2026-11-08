"""
Tests for document ingestion (Phase 13): upload, update, duplicates, delete,
rollback. Every test uses temporary folders, never documents/ or vector_store/.

HOW TO RUN
    PS> pytest tests/unit/test_ingestion.py -v
"""

import pytest

from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
)
from app.llm.base import LLMUnavailableError
from app.rag.embeddings import TfidfEmbedder
from app.rag.index import KnowledgeIndex, read_manifest
from app.rag.vector_store import NumpyVectorStore
from app.services.ingestion_service import IngestionService, safe_name

CSV = b"training,provider,hours\nKafka Essentials,External Partner,12\nSpark Bootcamp,Internal Academy,24\n"


class BrokenEmbedder(TfidfEmbedder):
    def embed_documents(self, texts):
        raise LLMUnavailableError("Ollama stopped")


@pytest.fixture
def service(tmp_path):
    changes = []
    svc = IngestionService(
        "documents",
        tmp_path / "uploads",
        tmp_path / "store" / "default",
        lambda: (TfidfEmbedder(), []),
        NumpyVectorStore,
        max_bytes=5000,
        on_change=lambda: changes.append(1),
    )
    svc.changes = changes
    return svc


def _sources(svc) -> dict[str, str]:
    return {d["source"]: d["origin"] for d in read_manifest(svc.index_dir)["documents"]}


def test_upload_adds_the_document_to_the_index(service):
    result = service.ingest("internal_trainings.csv", CSV)
    assert (result.status, result.title, result.chunks) == ("added", "Internal Trainings", 1)
    assert _sources(service)["internal_trainings.csv"] == "uploaded"
    assert _sources(service)["faq.md"] == "base"
    assert service.changes == [1]  # the API is told to reload the index
    hits = KnowledgeIndex.load(service.index_dir).search("Kafka Essentials hours", 1)
    assert hits[0].source == "internal_trainings.csv" and "hours: 12" in hits[0].text


def test_csv_rows_become_searchable_lines(service):
    service.ingest("internal_trainings.csv", CSV)
    chunk = next(
        c for c in KnowledgeIndex.load(service.index_dir).chunks if c.source == "internal_trainings.csv"
    )
    assert "training: Kafka Essentials; provider: External Partner; hours: 12." in chunk.text


def test_update_needs_overwrite(service):
    service.ingest("internal_trainings.csv", CSV)
    with pytest.raises(ConflictError) as error:
        service.ingest("internal_trainings.csv", CSV + b"Airflow Basics,Internal Academy,10\n")
    assert error.value.code == "DOCUMENT_EXISTS"
    result = service.ingest(
        "internal_trainings.csv", CSV + b"Airflow Basics,Internal Academy,10\n", overwrite=True
    )
    assert result.status == "updated"
    assert "Airflow" in KnowledgeIndex.load(service.index_dir).search("Airflow Basics", 1)[0].text


def test_duplicate_content_is_refused(service):
    service.ingest("internal_trainings.csv", CSV)
    with pytest.raises(ConflictError, match="same content as internal_trainings.csv"):
        service.ingest("copy.csv", CSV)
    with pytest.raises(ConflictError, match="faq.md"):
        service.ingest("faq_copy.md", (service.documents_dir / "faq.md").read_bytes())


def test_approved_documents_are_read_only(service):
    with pytest.raises(ConflictError) as error:
        service.ingest("faq.md", b"# Fake FAQ\n\nAnything.")
    assert error.value.code == "DOCUMENT_IS_APPROVED"
    with pytest.raises(ConflictError):
        service.delete("faq.md")


@pytest.mark.parametrize(
    "name, content, error_type, code",
    [
        ("tool.exe", b"MZ", InvalidInputError, "UNSUPPORTED_FILE_TYPE"),
        ("empty.txt", b"", InvalidInputError, "EMPTY_FILE"),
        ("big.txt", b"x" * 5001, PayloadTooLargeError, "FILE_TOO_LARGE"),
        ("fake.pdf", b"this is not a pdf", InvalidInputError, "FILE_CONTENT_MISMATCH"),
        ("blank.md", b"   \n  ", InvalidInputError, "INVALID_DOCUMENT"),
    ],
)
def test_bad_uploads_are_refused_and_nothing_is_stored(service, name, content, error_type, code):
    with pytest.raises(error_type) as error:
        service.ingest(name, content)
    assert error.value.code == code
    assert not service.upload_dir.exists() or list(service.upload_dir.iterdir()) == []
    assert service.changes == []


def test_unsafe_names_stay_inside_the_folder(service):
    assert safe_name("../../app/main.md") == "main.md"
    assert safe_name("C:\\temp\\notes.txt") == "notes.txt"
    assert safe_name("my file (v2).md") == "my file _v2_.md"
    result = service.ingest("../../escape.md", b"# Escape\n\nShould stay in the uploads folder.")
    assert result.source == "escape.md" and (service.upload_dir / "escape.md").exists()


def test_delete_removes_the_document(service):
    service.ingest("internal_trainings.csv", CSV)
    result = service.delete("internal_trainings.csv")
    assert result.status == "deleted" and "internal_trainings.csv" not in _sources(service)
    with pytest.raises(NotFoundError):
        service.delete("internal_trainings.csv")


def test_failed_rebuild_rolls_back_an_upload(service):
    service.ingest("internal_trainings.csv", CSV)
    before = read_manifest(service.index_dir)
    service.choose_embedder = lambda: (BrokenEmbedder(), [])
    with pytest.raises(ServiceUnavailableError) as error:
        service.ingest("new.md", b"# New\n\nA new document.")
    assert error.value.code == "INDEX_BUILD_FAILED"
    assert not (service.upload_dir / "new.md").exists()
    assert read_manifest(service.index_dir) == before


def test_failed_rebuild_rolls_back_an_update_and_a_delete(service):
    service.ingest("internal_trainings.csv", CSV)
    service.choose_embedder = lambda: (BrokenEmbedder(), [])
    with pytest.raises(ServiceUnavailableError):
        service.ingest("internal_trainings.csv", CSV + b"Extra,X,1\n", overwrite=True)
    assert (service.upload_dir / "internal_trainings.csv").read_bytes() == CSV  # the old version is back
    with pytest.raises(ServiceUnavailableError):
        service.delete("internal_trainings.csv")
    assert (service.upload_dir / "internal_trainings.csv").exists()
    assert [p.name for p in service.upload_dir.iterdir()] == ["internal_trainings.csv"]  # no leftovers
