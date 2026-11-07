# tests – automated tests

Run all: `pytest` · quick: `pytest -m "not slow"` · full guide: [`docs/TESTING_GUIDE.md`](../docs/TESTING_GUIDE.md)

| Folder | What it tests | Tests |
| --- | --- | --- |
| `unit/` | Single functions and services: formulas, scoring, loaders, RAG, LLM layer (with a fake Ollama server in `conftest.py`) | 319 |
| `api/` | Each endpoint through FastAPI's TestClient: input validation, response shape, the shared error format, the published contract | 71 |
| `integration/` | The APIs together for every employee, the HTTP business flow, and the API contract snapshot (`docs/api_contract.json`) | 24 |
| `security/` | Admin-only actions, tenant isolation, upload limits (Phase 17) | – |

A running server is checked with `python scripts/api_smoke_test.py` (also used by CI).
