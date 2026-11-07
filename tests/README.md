# tests – automated tests

Run all: `pytest -v`

| Folder | What it tests |
| --- | --- |
| `unit/` | Single functions and services (gap formula, scoring) |
| `api/` | Endpoints through FastAPI's TestClient (`test_health.py` – Phase 1) |
| `integration/` | Several parts together (database, vector store) |
| `security/` | Admin-only actions, tenant isolation, upload limits |
