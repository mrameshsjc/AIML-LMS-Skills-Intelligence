# LMS Skills Intelligence Engine – API

FastAPI service with seven APIs for an enterprise LMS, on **synthetic data only**. Open **`/docs`** for the interactive Swagger UI.

| # | Endpoint |
| --- | --- |
| 1 | `POST /api/v1/skills/analyze` |
| 2 | `POST /api/v1/roles/match` |
| 3 | `POST /api/v1/trainings/recommend` |
| 4 | `GET /api/v1/learning-path/{employee_id}` |
| 5 | `POST /api/v1/ai/chat` |
| 6 | `POST /api/v1/ml/retrain` (administrators) |
| 7 | `POST /api/v1/rag/ingest` (administrators) |

Visitors can call APIs 1–5 without an account (read-only guest access). Try `POST /api/v1/skills/analyze` with `{"employee_id": "E1001", "target_role_id": "R004"}`. Requests are rate-limited.

Source code and documentation: https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence
