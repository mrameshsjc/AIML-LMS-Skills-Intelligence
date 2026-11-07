# app/services – business logic (the heart of the engine)

**Filled in:** Phase 5 onward.

All decisions live here: gap scores, match percentages, recommendation ranking, learning-path order. Both the FastAPI routers **and** the Streamlit dashboard call these services, so they always give the same answer.

Rules for this folder:
- No FastAPI, Streamlit or SQL code here. Services receive plain Python objects and return plain Python objects.
- Data comes only through `app/repositories`, so the source (CSV, SQLite, MySQL, later the LMS) can change without touching this code.

| Planned file | Phase | Job |
| --- | --- | --- |
| `data_upload_service.py` | 4 – **done** | Upload, preview and validate CSV files |
| `skill_analysis.py` | 5 | Per-skill gaps and gap score |
| `role_matching.py` | 6 | Weighted match % for every role |
| `training_recommendation.py` | 7 | Ranked, explained course recommendations |
| `learning_path_service.py` | 10 | Prerequisite-ordered path and progress |
| `chat_service.py` | 13 | Builds the RAG answer for the assistant |
| `ingestion_service.py` | 13 | Document upload → chunks → vectors |
| `retraining_service.py` | 16 | Controlled ML retraining workflow |
