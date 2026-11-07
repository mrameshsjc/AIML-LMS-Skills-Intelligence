"""
07 - Clean the data: fix what is safe, quarantine the rest.

LESSON
    Validation (scripts 03-06) tells us WHAT is wrong. Cleaning decides what
    to DO about it. The rule we follow: fix a value only when the right answer
    is clear; otherwise set the row aside ("quarantine") with a reason, so
    nobody uses invented data and nothing is lost without a trace.

      Fixed automatically                       Quarantined (needs a person)
      ----------------------------------------  ---------------------------------
      renamed column  seniority_level           empty or out-of-range skill level
      extra column    legacy_code (dropped)     empty email (cannot invent one)
      'Complete' -> 'Completed'                 completed before enrolled
      31/12/2020 -> 2020-12-31                  unknown IDs (SK999, C-XYZ-101)
      score 120 -> 100 (capped)                 2nd copy of a repeated key
      empty course duration -> median           rows linked to a quarantined row
      swapped level_from / level_to             (the "cascade")
      exact duplicate rows (dropped)

    All policies live in app/data_processing/cleaning.py (top of the file),
    so they can be changed without touching the steps.

HOW TO RUN (from the project folder)
    PS> python scripts/make_dirty_data.py
    PS> python data_science/07_clean_data.py --data data/raw/dirty

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   --out (default data/processed):
           the 11 cleaned CSV files
           cleaning_log.csv    every change made
           rejected_rows.csv   every quarantined row, its original line and the reason
         then the cleaned files are validated again; exit code 1 if errors remain
"""

import argparse
import sys

from _common import explain, heading, report

from app.data_processing.cleaning import clean_folder
from app.data_processing.loader import resolve_folder
from app.data_processing.validators import run_checks

parser = argparse.ArgumentParser(description="Lesson 07: clean the data.")
parser.add_argument(
    "--data", default="data/sample", help="folder with the raw CSV files (default data/sample)"
)
parser.add_argument(
    "--out", default="data/processed", help="folder for the cleaned files (default data/processed)"
)
args = parser.parse_args()
source, target = resolve_folder(args.data), resolve_folder(args.out)

heading(f"1. Before: validation of {source}")
before = run_checks(source)
errors = sum(i.severity == "error" for i in before)
print(f"{errors} error(s), {len(before) - errors} warning(s)")

heading("2. Cleaning")
explain("""
Each file goes through the same steps: columns, text, categories, dates, numbers, missing values,
business rules, duplicates. Then references between files are checked, repeatedly, because
quarantining one row (e.g. an employee) can leave other rows pointing at nothing.
""")
result = clean_folder(source, target)

heading("3. What was fixed (cleaning_log.csv)")
actions = result.actions_table()
print(actions.to_string(index=False) if len(actions) else "Nothing needed fixing.")

heading("4. What was quarantined (rejected_rows.csv)")
rejected = result.rejected_table()
if len(rejected):
    summary = rejected.groupby(["dataset", "reason"]).size().reset_index(name="rows")
    print(summary.to_string(index=False))
    print(f"\n{len(rejected)} row(s) set aside. Each keeps its original line number and full content.")
    explain("""
    Rows marked 'not found in employees.csv' are the cascade: their employee was quarantined
    (for example for a missing email), so their skills, goals and training cannot stay either.
    Fix the employee at the source and re-run, and they all come back.
    """)
else:
    print("No rows were set aside.")
if result.skipped_datasets:
    print(f"\nFiles that could not be cleaned (missing or unusable): {', '.join(result.skipped_datasets)}")

heading(f"5. After: validation of the cleaned files in {target}")
sys.exit(report(run_checks(target), "validation after cleaning"))
