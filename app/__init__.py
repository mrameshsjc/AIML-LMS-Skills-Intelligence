"""LMS Skills Intelligence Engine - application package.

Layers (added phase by phase):
    app/api/       FastAPI routers (HTTP only, no business logic)
    app/core/      configuration, logging, errors
    app/data_processing/  dataset schemas, CSV loading, validation (Phase 3)
    app/services/  business logic shared by the API and the dashboard (upload service: Phase 4)
    app/ml/        machine-learning training and prediction (Phase 8+)
    app/rag/       document ingestion, embeddings, vector search (Phase 12+)
    app/llm/       LLM providers: Ollama, hosted, fallback (Phase 11+)
    app/database/  SQLAlchemy models and repositories (Phase 9+)
"""
