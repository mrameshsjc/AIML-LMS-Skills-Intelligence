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
    4. admin       BOOTSTRAP_ADMIN_PASSWORD set: create the admin account if it
                   does not exist (hosts whose disk resets on restart, Phase 19)
    5. model       PREPARE_TRAIN_MODEL=true: train a first completion model if
                   there is none, so the demo can show model metrics (Phase 19)

SEVERAL PODS AT ONCE (Phase 20)
    On Kubernetes every API and dashboard pod runs this step in an init container,
    all on the same volume. A lock file (vector_store/.prepare.lock) makes them wait
    for each other: the first builds, the others then find everything "ready".

RESET (Phase 19)
    reset_demo() puts the demo back to its starting state: uploaded documents,
    model versions and the database are removed, then the steps above run again.
    Used by the admin endpoint POST /api/v1/admin/reset-demo, the dashboard and
        python -m app.core.prepare --reset
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
    Reset the demo data:                          python -m app.core.prepare --reset
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
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


def ensure_admin_account(settings: Settings) -> str:
    """Create the bootstrap admin account from a secret, once."""
    password = settings.bootstrap_admin_password.get_secret_value()
    if not password:
        return "skipped (no BOOTSTRAP_ADMIN_PASSWORD)"
    from app.security.users import UserStore

    store = UserStore(settings.users_file)
    if store.get(settings.bootstrap_admin_username) is not None:
        return f"ready ({settings.bootstrap_admin_username})"
    store.save(settings.bootstrap_admin_username, password, "admin", None, settings.rag_tenant)
    return f"created {settings.bootstrap_admin_username} (password from BOOTSTRAP_ADMIN_PASSWORD)"


def ensure_model(settings: Settings) -> str:
    """Train a first completion model if there is none (only with PREPARE_TRAIN_MODEL=true)."""
    if not settings.prepare_train_model:
        return "skipped (PREPARE_TRAIN_MODEL=false)"
    from functools import partial

    from app.ml.model_registry import MODEL_NAME, current_version
    from app.ml.retraining import RetrainingService
    from app.ml.tracking import choose_tracker

    if current_version(settings.model_dir) is not None:
        return f"ready (version {current_version(settings.model_dir)})"
    service = RetrainingService(
        settings.data_dir,
        settings.model_dir,
        tracker_factory=partial(
            choose_tracker,
            settings.mlflow_enabled,
            settings.mlflow_tracking_uri,
            settings.mlflow_experiment,
            MODEL_NAME,
        ),
        min_roc_auc=settings.ml_min_roc_auc,
        max_regression=settings.ml_max_regression,
        min_rows=settings.ml_min_training_rows,
    )
    report = service.retrain(requested_by="start step", reason="first model for the demo")
    return f"{report.status}: version {report.new_version}, test ROC AUC {report.new_metrics.get('roc_auc')}"


def reset_demo(settings: Settings) -> list[str]:
    """Back to the starting state: remove uploads, model versions, database and index; prepare again.

    Accounts and the audit log are kept (who reset the demo stays on record).
    """
    from app.rag.factory import tenant_folder

    removed = []
    targets = [
        resolve_folder(settings.rag_upload_dir),
        resolve_folder(settings.model_dir),
        tenant_folder(settings),
    ]
    for folder in targets:
        if folder.exists():
            shutil.rmtree(folder)
            removed.append(str(folder))
    if settings.data_source == "database":
        from app.database.connection import sqlite_path

        db = Path(sqlite_path(settings.database_url))
        if db.exists():
            db.unlink()
            removed.append(str(db))
    lines = [f"Removed: {', '.join(removed) if removed else 'nothing'}"]
    return lines + prepare(settings.model_copy(update={"prepare_on_start": True}))


@contextmanager
def volume_lock(settings: Settings) -> Iterator[None]:
    """One start step at a time per shared volume (Linux containers). A no-op on Windows."""
    folder = resolve_folder(settings.vector_store_dir)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # Windows: one local process, nothing to coordinate
        yield
        return
    with (folder / ".prepare.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)  # waits while another pod prepares
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def prepare(settings: Settings) -> list[str]:
    """Run every step; returns readable lines for the container log. Raises only for the database."""
    if not settings.prepare_on_start:
        return ["Start step skipped (PREPARE_ON_START=false)."]
    with volume_lock(settings):
        return _prepare(settings)


def _prepare(settings: Settings) -> list[str]:
    lines = []
    created = ensure_folders(settings)
    lines.append(f"Folders: {'created ' + ', '.join(created) if created else 'ready'}")
    lines.append(f"Database: {ensure_database(settings)}")
    try:
        lines.append(f"Document index: {ensure_index(settings)}")
    except Exception as error:  # the API still works; the assistant reports the missing index
        lines.append(f"Document index: NOT built ({error}). Build it later: python scripts/build_index.py")
    lines.append(f"Admin account: {ensure_admin_account(settings)}")
    try:
        lines.append(f"Model: {ensure_model(settings)}")
    except Exception as error:  # recommendations work without a model (three-part score)
        lines.append(f"Model: NOT trained ({error}). Train it later: python scripts/retrain.py")
    return lines


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | prepare | %(message)s")
    reset = bool(argv) and argv[0] == "--reset"
    if reset:
        argv = argv[1:]
    try:
        steps = reset_demo(get_settings()) if reset else prepare(get_settings())
        for line in steps:
            logger.info(line)
    except Exception as error:
        logger.error("Cannot prepare the database: %s", error)
        sys.exit(1)
    if argv:  # become the real command (same process: it gets Docker's stop signal)
        sys.stdout.flush()
        os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])
