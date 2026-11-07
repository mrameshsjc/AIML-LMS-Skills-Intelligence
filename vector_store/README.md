# vector_store – saved knowledge indexes

**Filled in:** Phase 12. Generated files, **not committed to Git** (only this README is).

`python scripts/build_index.py` creates one folder per tenant (`RAG_TENANT`, default `default`):

| File | What it is |
| --- | --- |
| `manifest.json` | How the index was built: embedder and model, backend, chunk settings, documents with SHA-256 fingerprints |
| `chunks.jsonl` | One chunk per line: text, source, section, page |
| `index.faiss` or `vectors.npy` | The vectors (FAISS or NumPy backend) |
| `tfidf_vectorizer.joblib` | Only for TF-IDF indexes: the learned vocabulary |

In Docker, this folder is the `lms_index` volume, so the index survives container restarts.
