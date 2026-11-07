# app/api/v1 – HTTP endpoints (version 1)

Routers only: receive the request, call a service, return the response. No business logic here.

| File | Endpoint | Phase |
| --- | --- | --- |
| `health.py` | `GET /api/v1/health` | 1 – **done** |
| `skills.py` | `POST /api/v1/skills/analyze` | 5 |
| `roles.py` | `POST /api/v1/roles/match` | 6 |
| `trainings.py` | `POST /api/v1/trainings/recommend` | 7 |
| `learning_path.py` | `GET /api/v1/learning-path/{employee_id}` | 10 |
| `ai_chat.py` | `POST /api/v1/ai/chat` | 13 |
| `rag.py` | `POST /api/v1/rag/ingest` | 13 |
| `ml_training.py` | `POST /api/v1/ml/retrain` | 16 |
