"""
Database connection (Phase 9).

PURPOSE
    One place that turns the DATABASE_URL setting into an open SQLite
    connection, configured the same way every time.

WHY SQLITE, AND WHY PLAIN sqlite3
    SQLite keeps the whole database in ONE file (data/lms_ai.db) and needs no
    server, so it is ideal for a first local version. Python ships with the
    sqlite3 module, so nothing extra is installed.
    The cost: SQLite only. A later phase can move to SQLAlchemy, which speaks
    both SQLite and MySQL; then only this layer and the repository change,
    because the services talk to the LmsRepository interface, not to SQL.

URL FORMAT (same style as SQLAlchemy, so .env does not change later)
    sqlite:///./data/lms_ai.db     a file, relative to the project folder
    sqlite:////abs/path/lms.db     an absolute path (four slashes)
    sqlite:///:memory:             a throw-away database in memory (tests)

THREE SETTINGS APPLIED TO EVERY CONNECTION
    PRAGMA foreign_keys = ON   SQLite does NOT check foreign keys unless asked,
                               for historical reasons. We always ask.
    row_factory = sqlite3.Row  rows can be read by column name: row["skill_id"]
    timeout = 10               wait up to 10 s if another process is writing
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data_processing.loader import PROJECT_ROOT

SQLITE_PREFIX = "sqlite:///"


class DatabaseUrlError(ValueError):
    """The DATABASE_URL cannot be used by this version of the engine."""


class DatabaseNotReadyError(RuntimeError):
    """The database file exists but has no LMS tables or data yet."""


def sqlite_path(database_url: str) -> str:
    """The file path inside a sqlite:/// URL (or ':memory:')."""
    if not database_url.startswith(SQLITE_PREFIX):
        scheme = database_url.split(":", 1)[0]
        raise DatabaseUrlError(
            f"DATABASE_URL '{scheme}:...' is not supported yet: this version uses SQLite only "
            "(e.g. sqlite:///./data/lms_ai.db). MySQL support is planned for a later phase."
        )
    path = database_url[len(SQLITE_PREFIX) :]
    if path in ("", ":memory:"):
        return ":memory:"
    file = Path(path)
    return str(file if file.is_absolute() else (PROJECT_ROOT / file).resolve())


def connect(database_url: str, create_folder: bool = False) -> sqlite3.Connection:
    """Open a configured connection. Close it when done (use contextlib.closing)."""
    path = sqlite_path(database_url)
    if path != ":memory:":
        folder = Path(path).parent
        if create_folder:
            folder.mkdir(parents=True, exist_ok=True)
        elif not Path(path).exists():
            raise FileNotFoundError(
                f"Database file not found: {path}. Create it with: python data_science/14_save_to_database.py"
            )
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
