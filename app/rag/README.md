# app/rag – knowledge documents for the AI assistant

**Filled in:** Phase 12–13.

| Planned file | Step |
| --- | --- |
| `document_loader.py` | Extract text from PDF, DOCX, TXT, CSV |
| `cleaning.py` | Remove noise, normalise whitespace |
| `chunking.py` | Split text into overlapping chunks |
| `embeddings.py` | Sentence Transformers vectors |
| `vector_store.py` | FAISS index saved in `vector_store/` |
| `retrieval.py` | Top-k similar chunks with source and page |
| `prompts.py` | Grounded prompt templates |

RAG adds knowledge without retraining the LLM. It is separate from ML retraining and from fine-tuning.
