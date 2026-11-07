"""
14 - Save the LMS data into a SQLite database, and query it with SQL.

LESSON
    CSV files are fine for learning, but a real application keeps its data in
    a DATABASE: the database enforces the rules itself (keys, references,
    allowed values), many users can read and write safely, and SQL answers
    questions without loading everything into memory.

    This script:
      1. validates the CSV folder (the same checks as scripts 03-06), and
         refuses to continue if there are errors;
      2. creates the database and its tables by running the MIGRATIONS
         (app/database/migrations/*.sql) that have not run yet;
      3. replaces the table contents with the CSV data, in one transaction;
      4. answers three questions with SQL (JOIN, GROUP BY, constraints).

    SQLite stores the whole database in one file, data/lms_ai.db. Open it in
    PyCharm (Database tool window, or the free "DB Browser for SQLite") to
    browse the tables.

HOW TO RUN (from the project folder)
    PS> python data_science/14_save_to_database.py
    PS> python data_science/14_save_to_database.py --data data/processed --db data/lms_ai.db

THEN USE IT IN THE API
    In .env set DATA_SOURCE=database, and restart uvicorn.

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   the SQLite file --db (default data/lms_ai.db; git-ignored)
"""

import argparse
import sqlite3
import sys
from contextlib import closing

import pandas as pd
from _common import explain, heading, report

from app.data_processing.loader import load_all, resolve_folder
from app.data_processing.validators import run_checks
from app.database.connection import connect
from app.database.migrate import applied_migrations, apply_migrations
from app.database.tables import save_datasets

parser = argparse.ArgumentParser(description="Lesson 14: save the data to SQLite and query it.")
parser.add_argument(
    "--data", default="data/sample", help="folder with the 11 CSV files (default data/sample)"
)
parser.add_argument("--db", default="data/lms_ai.db", help="SQLite file to create or update")
args = parser.parse_args()

heading(f"1. Validate {resolve_folder(args.data)}")
if report(run_checks(args.data), "the CSV files") != 0:
    sys.exit("Fix the errors first, or clean the data with 07_clean_data.py and use --data data/processed.")

url = f"sqlite:///{args.db}"
with closing(connect(url, create_folder=True)) as conn:
    heading("2. Create or update the tables (migrations)")
    ran = apply_migrations(conn)
    print(f"Ran now: {ran or 'nothing - the database was already up to date'}")
    print(f"Applied in total: {applied_migrations(conn)}")
    explain("""
A migration runs only once per database. Run this script again: 'Ran now' is empty, the data is reloaded.
""")

    heading("3. Load the data (one transaction: all rows or none)")
    counts = save_datasets(conn, load_all(args.data))
    print(pd.Series(counts, name="rows").to_string())
    print(f"\nDatabase file: {resolve_folder(args.db)}")

    heading("4a. SQL JOIN: E1001's skills against the Data Engineer requirements")
    gaps = pd.read_sql_query(
        """
        SELECT s.skill_name                               AS skill,
               r.required_level                           AS required,
               COALESCE(e.current_level, 0)               AS current,
               MAX(r.required_level - COALESCE(e.current_level, 0), 0) AS gap
        FROM role_required_skills AS r
        JOIN skills AS s ON s.skill_id = r.skill_id
        LEFT JOIN employee_skills AS e                    -- LEFT: keep skills E1001 does not have
               ON e.skill_id = r.skill_id AND e.employee_id = ?
        WHERE r.role_id = (SELECT role_id FROM job_roles WHERE role_title = 'Data Engineer')
        ORDER BY r.rowid
        """,
        conn,
        params=("E1001",),
    )
    print(gaps.to_string(index=False))
    score = 100 * gaps["gap"].sum() / gaps["required"].sum()  # all weights are 1.0 in the sample data
    print(
        f"\ngap score = 100 x {gaps['gap'].sum()} / {gaps['required'].sum()} = {score:.1f}  (API 1 says 37.5)"
    )
    explain("""
JOIN combines rows of two tables that share a key. LEFT JOIN keeps every requirement even when the
employee has no row for that skill (current becomes NULL, and COALESCE turns it into 0).
""")

    heading("4b. SQL GROUP BY: completion rate per course difficulty")
    rates = pd.read_sql_query(
        """
        SELECT c.difficulty,
               COUNT(*)                                            AS finished,
               ROUND(AVG(CASE WHEN t.status = 'Completed' THEN 1.0 ELSE 0 END), 3) AS completion_rate
        FROM training_history AS t
        JOIN courses AS c ON c.course_id = t.course_id
        WHERE t.status IN ('Completed', 'Dropped')
        GROUP BY c.difficulty
        ORDER BY completion_rate DESC
        """,
        conn,
    )
    print(rates.to_string(index=False))
    explain("The same numbers as the Pandas groupby in script 09: SQL and Pandas are two ways to ask.")

    heading("4c. Constraints: the database refuses bad data by itself")
    attempts = [
        (
            "a skill for an employee who does not exist (FOREIGN KEY)",
            "INSERT INTO employee_skills VALUES ('E9999', 'SK001', 3, 'self', '2026-10-01')",
        ),
        (
            "a skill level of 7 (CHECK level BETWEEN 1 AND 5)",
            "INSERT INTO employee_skills VALUES ('E1001', 'SK042', 7, 'self', '2026-10-01')",
        ),
        (
            "the same skill twice for E1001 (PRIMARY KEY)",
            "INSERT INTO employee_skills SELECT * FROM employee_skills WHERE employee_id = 'E1001' LIMIT 1",
        ),
    ]
    for what, sql in attempts:
        try:
            conn.execute(sql)
            print(f"  accepted?! {what}")
        except sqlite3.IntegrityError as error:
            print(f"  refused: {what}\n           -> {error}")
        finally:
            conn.rollback()  # leave the database exactly as loaded
    explain("""
Validation in Python (scripts 03-06) explains problems to people; constraints in the database are the
last line of defence, so no program can store a broken row, however it was written.
Next: set DATA_SOURCE=database in .env and restart uvicorn - the APIs now read from this file.
""")
