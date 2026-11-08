"""
Container start step (Phase 18): get a fresh volume ready, then start the app.

WHY
    A new container starts with EMPTY volumes: no database, no document index.
    Without this step the first user would see "No index yet - run
    scripts/build_index.py" and need to know Docker commands. This step makes
    `docker compose up` give a working system on the very first start.

WHAT IT DOES (each step is skipped when its result already exists)
    1. folders     uploads, index, models, logs, accounts, database folder
    2. database    DATA_SOURCE=database: create the tables (migrations) and load
                   the synthetic sample data, ONLY if the database is empty
    3. index       build the document index if there is none (Ollama embeddings
                   when reachable, otherwise TF-IDF - the same choice as
                   scripts/build_index.py)
    Then it REPLACES itself with the real command (uvicorn, streamlit, mlflow),
    so that command receives Docker's stop signal directly.

    A failed index build is reported and the app still starts (the assistant
    says the index is missing). A database that cannot be prepared stops the
    container: the APIs could not work without it.

HOW IT IS USED (Dockerfile)
    ENTRYPOINT ["python", "-m", "app.core.prepare"]
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    Set PREPARE_ON_START=false for every other service using the same volumes
    (dashboard, mlflow): two containers must not build the same index at once.

    Run it by hand (no command = prepare only):   python -m app.core.prepare
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import closing
from pathlib import Path

from app.core.config import Settings, get_settings
from app.data_processing.loader import load_all, resolve_folder

logger = logging.getLogger("prepare")


def ensure_folders(settings: Settings) -> list[str]:
    """Create the writable folders; returns the ones that were new."""
    created = []
    folders = [
        resolve_folder(settings.rag_upload_dir),
        resolve_folder(settings.vector_store_dir),
        resolve_folder(settings.model_dir),
    ]
    for file_setting in (settings.users_file, settings.audit_log_file):
        if file_setting:
            file = Path(file_setting)
            folders.append(file.parent if file.is_absolute() else resolve_folder(file.parent))
    for folder in folders:
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            created.append(str(folder))
    return created


def ensure_database(settings: Settings) -> str:
    """With DATA_SOURCE=database: tables + sample data on first start. Returns what was done."""
    if settings.data_source != "database":
        return "skipped (DATA_SOURCE=csv)"
    from app.database.connection import connect
    from app.database.migrate import apply_migrations
    from app.database.tables import save_datasets, table_counts

    with closing(connect(settings.database_url, create_folder=True)) as conn:
        ran = apply_migrations(conn)
        if table_counts(conn).get("employees", 0) > 0:
            return "ready" + (f" (migrations run now: {', '.join(ran)})" if ran else "")
        counts = save_datasets(conn, load_all(settings.data_dir))
    return f"created and loaded from {settings.data_dir}: {sum(counts.values())} rows in {len(counts)} tables"


def ensure_index(settings: Settings) -> str:
    """Build the document index if there is none. Returns what was done."""
    from app.rag.factory import choose_embedder, tenant_folder
    from app.rag.index import build_index, read_manifest
    from app.rag.vector_store import choose_backend

    folder = tenant_folder(settings)
    if read_manifest(folder) is not None:
        return f"ready ({folder})"
    embedder, notes = choose_embedder(settings)
    report = build_index(
        settings.documents_dir,
        folder,
        embedder,
        choose_backend(settings.vector_backend),
        settings.rag_chunk_size,
        settings.rag_chunk_overlap,
        upload_dir=settings.rag_upload_dir,
    )
    how = f"{report.embedder}/{report.backend}"
    return f"built: {report.documents} documents, {report.chunks} chunks ({how}). {' '.join(notes)}".strip()


def prepare(settings: Settings) -> list[str]:
    """Run every step; returns readable lines for the container log. Raises only for the database."""
    if not settings.prepare_on_start:
        return ["Start step skipped (PREPARE_ON_START=false)."]
    lines = []
    created = ensure_folders(settings)
    lines.append(f"Folders: {'created ' + ', '.join(created) if created else 'ready'}")
    lines.append(f"Database: {ensure_database(settings)}")
    try:
        lines.append(f"Document index: {ensure_index(settings)}")
    except Exception as error:  # the API still works; the assistant reports the missing index
        lines.append(f"Document index: NOT built ({error}). Build it later: python scripts/build_index.py")
    return lines


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | prepare | %(message)s")
    try:
        for line in prepare(get_settings()):
            logger.info(line)
    except Exception as error:
        logger.error("Cannot prepare the database: %s", error)
        sys.exit(1)
    if argv:  # become the real command (same process: it gets Docker's stop signal)
        sys.stdout.flush()
        os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])
