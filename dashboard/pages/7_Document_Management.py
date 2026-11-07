"""Document management: upload, list and delete the assistant's knowledge documents (API 7)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_index_manifest, get_ingestion_service, get_knowledge_index  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.rag.factory import choose_embedder, tenant_folder  # noqa: E402
from app.rag.index import IndexNotReadyError, build_index  # noqa: E402
from app.rag.vector_store import choose_backend  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "Document management",
    "The documents the AI assistant may use. Upload → text extraction → cleaning → chunking → embeddings → "
    "vector index, then ask about them on the assistant page.",
    "🗂️",
)
ui.admin_notice()
settings = get_settings()
manifest = get_index_manifest()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Index", "Ready" if manifest else "Not built")
c2.metric("Documents", len(manifest["documents"]) if manifest else 0)
c3.metric("Chunks", manifest["chunk_count"] if manifest else 0)
c4.metric("Embeddings", f"{manifest['embedder']['name']} · {manifest['backend']}" if manifest else "–")
if manifest:
    st.caption(f"Built {manifest['created_at']} with {manifest['embedder']['model']}.")
    st.dataframe(data.documents_table(manifest), hide_index=True)
    for warning in manifest.get("warnings", []):
        st.caption(f"Skipped at the last build: {warning}")

st.subheader("Upload a document")
uploaded = st.file_uploader("PDF, Word, text, CSV or Markdown", type=["pdf", "docx", "txt", "csv", "md"])
overwrite = st.checkbox("Replace an uploaded document with the same name")
if uploaded is not None and st.button("Upload and ingest", type="primary"):
    with st.spinner("Extracting, chunking and embedding ..."):
        result = ui.safe(get_ingestion_service().ingest, uploaded.name, uploaded.getvalue(), overwrite)
    if result:
        st.success(
            f"{result.status.capitalize()}: {result.source} ({result.pages} pages, {result.chunks} chunks)."
        )
        for note in result.notes:
            st.caption(note)

uploads = [d["source"] for d in (manifest or {}).get("documents", []) if d.get("origin") == "uploaded"]
st.subheader("Delete an uploaded document")
if uploads:
    to_delete = st.selectbox("Uploaded document", uploads)
    if st.button("Delete", icon="🗑️"):
        result = ui.safe(get_ingestion_service().delete, to_delete)
        if result:
            st.success(f"Deleted {result.source}. The index was rebuilt.")
else:
    st.caption("No uploaded documents. The approved documents in documents/ cannot be deleted here.")

st.subheader("Rebuild the index")
st.caption(
    "After adding files to documents/ by hand, or to switch to Ollama embeddings once they are installed."
)
if st.button("Rebuild now"):
    with st.spinner("Rebuilding ..."):
        try:
            embedder, notes = choose_embedder(settings)
            report = build_index(
                settings.documents_dir,
                tenant_folder(settings),
                embedder,
                choose_backend(settings.vector_backend),
                settings.rag_chunk_size,
                settings.rag_chunk_overlap,
                upload_dir=settings.rag_upload_dir,
            )
            get_knowledge_index.cache_clear()
            st.success(
                f"Indexed {report.documents} documents as {report.chunks} chunks in {report.seconds:.1f} s."
            )
            for note in notes:
                st.caption(note)
        except (IndexNotReadyError, RuntimeError) as error:
            st.error(str(error))
