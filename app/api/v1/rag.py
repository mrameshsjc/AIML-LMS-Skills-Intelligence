"""
API 7 - RAG Knowledge Ingestion: POST /api/v1/rag/ingest
plus GET /api/v1/rag/documents and DELETE /api/v1/rag/documents/{source}

PURPOSE
    Upload a document (PDF, DOCX, TXT, CSV, Markdown) so the assistant can use
    it, replace it (overwrite=true), list what is indexed, or delete an upload.
    Approved base documents (documents/) are read-only through the API.
    All logic is in app/services/ingestion_service.py.

WHY MULTIPART
    Files are sent as multipart/form-data, the standard way browsers and tools
    upload files (FastAPI needs the python-multipart package for it).

SECURITY NOTE
    Phase 17 restricts these endpoints to administrators. Until then they are
    open, like every endpoint, and the API serves synthetic data only.

ERRORS (shared format)
    404 DOCUMENT_NOT_FOUND             409 DOCUMENT_EXISTS / DUPLICATE_DOCUMENT / DOCUMENT_IS_APPROVED
    413 FILE_TOO_LARGE                 422 UNSUPPORTED_FILE_TYPE / EMPTY_FILE / INVALID_DOCUMENT
    503 INDEX_BUILD_FAILED
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import IngestionServiceDep, get_index_manifest
from app.core.config import get_settings
from app.schemas.common import ErrorResponse
from app.schemas.rag import DocumentListResponse, DocumentOut, IndexSummaryOut, IngestResponse
from app.services.ingestion_service import IngestResult

router = APIRouter(prefix="/rag", tags=["7. Knowledge Documents"])

ERRORS = {
    404: {"model": ErrorResponse, "description": "Document not found"},
    409: {"model": ErrorResponse, "description": "Name exists, duplicate content, or an approved document"},
    413: {"model": ErrorResponse, "description": "File too large"},
    422: {"model": ErrorResponse, "description": "Unsupported, empty or unreadable file"},
    503: {"model": ErrorResponse, "description": "The index could not be rebuilt"},
}


def _out(r: IngestResult) -> IngestResponse:
    return IngestResponse(
        status=r.status,
        source=r.source,
        title=r.title,
        pages=r.pages,
        chunks=r.chunks,
        sha256=r.sha256,
        index=IndexSummaryOut(
            documents=r.index.documents,
            chunks=r.index.chunks,
            embedder=r.index.embedder,
            embedding_model=r.index.model,
            backend=r.index.backend,
            seconds=r.index.seconds,
        ),
        notes=r.notes,
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Upload a document into the knowledge index",
    description=(
        "Extracts the text, checks it, stores the file in the uploads folder and rebuilds the index. "
        "Supported: .pdf, .docx, .txt, .csv, .md (up to RAG_MAX_UPLOAD_MB). Send **overwrite=true** to "
        "replace an uploaded document with a new version. Identical content under another name is refused."
    ),
    responses={k: v for k, v in ERRORS.items() if k != 404},
)
def ingest(
    service: IngestionServiceDep,
    file: Annotated[UploadFile, File(description="The document to upload.")],
    overwrite: Annotated[bool, Form(description="Replace an uploaded document with the same name.")] = False,
) -> IngestResponse:
    content = file.file.read(service.max_bytes + 1)  # read at most one byte over the limit
    return _out(service.ingest(file.filename or "", content, overwrite))


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List the documents in the knowledge index",
    description="Every indexed document with its origin (base or uploaded), pages, chunks and fingerprint.",
)
def list_documents(manifest: Annotated[dict | None, Depends(get_index_manifest)]) -> DocumentListResponse:
    tenant = get_settings().rag_tenant
    if manifest is None:
        return DocumentListResponse(ready=False, tenant=tenant)
    return DocumentListResponse(
        ready=True,
        tenant=tenant,
        embedder=manifest["embedder"]["name"],
        embedding_model=manifest["embedder"]["model"],
        backend=manifest["backend"],
        built_at=manifest["created_at"],
        chunk_count=manifest["chunk_count"],
        documents=[
            DocumentOut(
                source=d["source"],
                title=d["title"],
                origin=d.get("origin", "base"),
                pages=d["pages"],
                chunks=d["chunks"],
                sha256=d["sha256"],
            )
            for d in manifest["documents"]
        ],
        warnings=manifest.get("warnings", []),
    )


@router.delete(
    "/documents/{source}",
    response_model=IngestResponse,
    summary="Delete an uploaded document",
    description="Removes an uploaded document and rebuilds the index. Base documents cannot be deleted.",
    responses={k: v for k, v in ERRORS.items() if k in (404, 409, 503)},
)
def delete_document(source: str, service: IngestionServiceDep) -> IngestResponse:
    return _out(service.delete(source))
