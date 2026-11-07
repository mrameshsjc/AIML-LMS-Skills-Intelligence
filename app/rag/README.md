# app/rag – knowledge documents for the AI assistant

**Filled in:** Phase 12 (search). Phase 13 adds the chat answer and document ingestion.

| File | Step |
| --- | --- |
| `document_loader.py` | Text from `.md`, `.txt`, `.pdf` (pypdf, with page numbers) and `.docx` (built-in zipfile) |
| `chunking.py` | Clean the text; split along headings and paragraphs into ~800-character chunks with overlap |
| `embeddings.py` | Ollama embeddings (`nomic-embed-text`) or TF-IDF; normalised vectors |
| `vector_store.py` | FAISS (`IndexFlatIP`) or exact NumPy search, saved to disk |
| `index.py` | Build an index (written to a temp folder, then swapped in) and search it; `manifest.json` |
| `factory.py` | Settings → embedder and index |

RAG adds knowledge without retraining the LLM. It is separate from ML retraining and from fine-tuning. Guide: [`docs/LLM_RAG_GUIDE.md`](../../docs/LLM_RAG_GUIDE.md) section 10.
