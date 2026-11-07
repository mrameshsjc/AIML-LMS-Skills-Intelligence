"""
Schema migrations (Phase 9): create and evolve the tables step by step.

WHAT IS A MIGRATION?
    A numbered SQL file that changes the database structure: 0001 creates the
    tables, a later 0002 might add a column. Each database remembers which
    migrations it has run (table schema_migrations), so running
    apply_migrations() again only runs the NEW files. This is how a team keeps
    every copy of the database (laptops, test, production) in the same shape.

    Tools such as Alembic (for SQLAlchemy) or Flyway do exactly this, with
    more features. This small runner shows the idea in 40 lines.

RULES
    - Files live in app/database/migrations/ and are named NNNN_description.sql.
    - They run in number order, each inside a transaction: a file runs
      completely or not at all.
    - Never edit a file that has already run somewhere. Add a new one.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def available_migrations(folder: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(folder.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def applied_migrations(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def apply_migrations(conn: sqlite3.Connection, folder: Path = MIGRATIONS_DIR) -> list[str]:
    """Run every migration not yet applied. Returns the names of the ones that ran."""
    done = set(applied_migrations(conn))
    ran = []
    for file in available_migrations(folder):
        if file.stem in done:
            continue
        # executescript() would commit on its own, so the transaction is written out explicitly:
        # if any statement fails, ROLLBACK undoes the whole file.
        try:
            conn.executescript(
                "BEGIN;\n"
                + file.read_text(encoding="utf-8")
                + f"\nINSERT INTO schema_migrations VALUES ('{file.stem}', "
                f"'{datetime.now(UTC).isoformat(timespec='seconds')}');\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        ran.append(file.stem)
    return ran
