# migrations – reserved for Alembic

**Phase 9 decision:** the database uses Python's built-in `sqlite3`, and its migrations are plain numbered SQL files in [`app/database/migrations/`](../app/database/migrations/). They live inside `app/` so that they ship with the application (and the Docker image).

This folder stays reserved for **Alembic** revisions if the project moves to SQLAlchemy and MySQL later. See [`docs/DATABASE_GUIDE.md`](../docs/DATABASE_GUIDE.md), section 9.
