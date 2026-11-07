"""
Move LMS data between DataFrames and the database (Phase 9).

PURPOSE
    save_datasets()  writes the 11 typed DataFrames (from loader.load_all) into
                     the 11 tables, replacing what was there.
    read_datasets()  reads the tables back into DataFrames with EXACTLY the
                     same columns and types as load_all(), so code written for
                     the CSV files (EDA, the ML features) works on the
                     database unchanged.

TABLE NAMES
    The file name without ".csv": skills.csv -> skills.

ORDER MATTERS
    A foreign key must point to an existing row, so parent tables are filled
    before child tables (skills before employee_skills) and emptied after them.
    employees.manager_id points to employees itself; a manager may appear later
    in the file than their team, so foreign-key checks are DEFERRED to the end
    of the transaction (PRAGMA defer_foreign_keys).

ONE TRANSACTION
    Everything is replaced in one transaction: if any row is refused, nothing
    changes and the old data stays. Readers never see a half-loaded database.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from app.data_processing.loader import to_typed
from app.data_processing.schemas import SCHEMAS

LOAD_ORDER = [
    "skills.csv",
    "skill_proficiency.csv",
    "job_roles.csv",
    "role_required_skills.csv",
    "courses.csv",
    "course_skills.csv",
    "course_prerequisites.csv",
    "employees.csv",
    "employee_skills.csv",
    "career_goals.csv",
    "training_history.csv",
]


def table_name(dataset: str) -> str:
    return dataset.removesuffix(".csv")


def _to_sql_value(value, dtype: str):
    """One Pandas value -> a value SQLite stores (None, int, float, str)."""
    if value is None or value is pd.NA or (not isinstance(value, str) and pd.isna(value)):
        return None
    if dtype == "bool":
        return int(bool(value))
    if dtype == "int":
        return int(value)
    if dtype == "float":
        return float(value)
    if dtype == "date":
        return pd.Timestamp(value).date().isoformat()
    return str(value)


def save_datasets(conn: sqlite3.Connection, datasets: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Replace all table contents with the given typed DataFrames. Returns rows per table."""
    counts: dict[str, int] = {}
    try:
        conn.execute("BEGIN")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for name in reversed(LOAD_ORDER):  # children first, so no foreign key is left dangling
            conn.execute(f"DELETE FROM {table_name(name)}")
        for name in LOAD_ORDER:
            schema = SCHEMAS[name]
            columns = list(schema.column_names)
            types = [schema.column(c).dtype for c in columns]
            rows = [
                tuple(_to_sql_value(v, t) for v, t in zip(row, types, strict=True))
                for row in datasets[name][columns].itertuples(index=False, name=None)
            ]
            placeholders = ", ".join("?" * len(columns))  # "?" = a parameter: never paste values into SQL
            conn.executemany(
                f"INSERT INTO {table_name(name)} ({', '.join(columns)}) VALUES ({placeholders})", rows
            )
            counts[table_name(name)] = len(rows)
        conn.execute("COMMIT")  # deferred foreign keys are checked here
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return counts


def read_datasets(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """All tables as typed DataFrames, keyed by file name, in the same shape as loader.load_all()."""
    datasets = {}
    for name in LOAD_ORDER:
        schema = SCHEMAS[name]
        # ORDER BY rowid = insertion order = the original file order, so results match the CSV version.
        raw = pd.read_sql_query(
            f"SELECT {', '.join(schema.column_names)} FROM {table_name(name)} ORDER BY rowid", conn
        )
        for spec in schema.columns:  # to_typed() expects booleans as the text True/False, like the CSV
            if spec.dtype == "bool":
                raw[spec.name] = raw[spec.name].map({1: "True", 0: "False"})
        datasets[name] = to_typed(raw, schema)
    return datasets


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table_name(n): conn.execute(f"SELECT COUNT(*) FROM {table_name(n)}").fetchone()[0] for n in LOAD_ORDER
    }
