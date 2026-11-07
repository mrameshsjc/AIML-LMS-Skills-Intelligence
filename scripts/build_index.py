"""
Build the knowledge index for the AI assistant (Phase 12).

WHAT IT DOES
    Reads every document in DOCUMENTS_DIR (default documents/), splits them
    into chunks, embeds the chunks and saves the index in
    VECTOR_STORE_DIR/RAG_TENANT (default vector_store/default/).

    Embeddings: Ollama's nomic-embed-text when installed (better: understands
    meaning), otherwise TF-IDF (works everywhere, matches words). Restart the
    API after rebuilding so it loads the new index.

HOW TO RUN (from the project folder)
    PS> ollama pull nomic-embed-text            (optional, once)
    PS> python scripts/build_index.py
    PS> python scripts/build_index.py --provider tfidf --documents documents
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.rag.factory import choose_embedder, tenant_folder  # noqa: E402
from app.rag.index import build_index  # noqa: E402
from app.rag.vector_store import choose_backend  # noqa: E402

parser = argparse.ArgumentParser(description="Build the knowledge index.")
parser.add_argument("--documents", help="folder with the documents (default: DOCUMENTS_DIR)")
parser.add_argument("--provider", choices=["auto", "ollama", "tfidf"], help="override EMBEDDING_PROVIDER")
parser.add_argument("--backend", choices=["auto", "numpy", "faiss"], help="override VECTOR_BACKEND")
args = parser.parse_args()

settings = get_settings()
overrides = {
    k: v for k, v in {"embedding_provider": args.provider, "vector_backend": args.backend}.items() if v
}
settings = settings.model_copy(update=overrides)

try:
    embedder, notes = choose_embedder(settings)
    backend = choose_backend(settings.vector_backend)
except RuntimeError as error:
    sys.exit(f"Cannot build the index: {error}")

for note in notes:
    print(f"Embeddings: {note}")
print(
    f"Vector store: {backend.name}"
    + ("" if backend.name == "faiss" else " (pip install faiss-cpu to use FAISS)")
)

report = build_index(
    args.documents or settings.documents_dir,
    tenant_folder(settings),
    embedder,
    backend,
    settings.rag_chunk_size,
    settings.rag_chunk_overlap,
    upload_dir=settings.rag_upload_dir,
)
print(f"\nIndexed {report.documents} documents as {report.chunks} chunks in {report.seconds:.1f} s")
print(f"Saved to {report.folder}")
for warning in report.warnings:
    print(f"  skipped: {warning}")
print('\nTry it:  python scripts/search_documents.py "How many learning hours do I have?"')
