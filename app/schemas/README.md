# app/schemas – API request and response shapes

**Filled in:** Phase 5 onward (one file per API area).

Pydantic models that describe exactly what each endpoint accepts and returns. FastAPI uses them to validate input and to draw Swagger UI.

| Planned file | For endpoint |
| --- | --- |
| `skills.py` | `POST /api/v1/skills/analyze` (**done**) |
| `roles.py` | `POST /api/v1/roles/match` (**done**) |
| `trainings.py` | `POST /api/v1/trainings/recommend` |
| `learning_path.py` | `GET /api/v1/learning-path/{employee_id}` |
| `chat.py` | `POST /api/v1/ai/chat` |
| `ml.py` | `POST /api/v1/ml/retrain` |
| `rag.py` | `POST /api/v1/rag/ingest` |
| `common.py` | shared error format and role reference (**done**) |
