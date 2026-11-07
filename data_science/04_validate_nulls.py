"""
04 - Validate nulls: are required values filled in?

LESSON
    A "null" (NaN in Pandas) is an empty cell. Some columns may be empty by
    design - for example manager_id is empty for top managers, and
    completed_date is empty until a course is finished. Others must ALWAYS have
    a value, such as employee_id or current_level.

    The schema marks each column as required or optional. This script:
      1. counts empty cells per column with df.isna().sum();
      2. reports an error for every REQUIRED column that has empty cells.

    Useful Pandas:
      df.isna()          True/False table: is each cell empty?
      df.isna().sum()    number of empty cells per column
      df[df["col"].isna()]  the rows where "col" is empty

HOW TO RUN (from the project folder)
    PS> python data_science/04_validate_nulls.py
    PS> python data_science/04_validate_nulls.py --data data/raw/dirty

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   empty-cell counts per file, then the issues; exit code 1 if any error
"""

import sys

from _common import explain, heading, parse_args, report

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import Issue, null_summary, validate_nulls

args = parse_args("Lesson 04: find empty values.")
folder = resolve_folder(args.data)

heading(f"Empty cells per column in {folder}")
explain("""
Only columns with at least one empty cell are listed. 'required' comes from schemas.py:
an empty cell in a required column is an error; in an optional column it is expected.
""")

issues: list[Issue] = []
for name, schema in SCHEMAS.items():
    try:
        df = load_raw(name, folder)
    except FileNotFoundError:
        print(f"\n{name}: file not found (see script 03)")
        continue
    summary = null_summary(df)
    summary = summary[summary["empty"] > 0]
    if summary.empty:
        print(f"\n{name}: no empty cells")
    else:
        required = {c.name: c.required for c in schema.columns}
        summary["required"] = [required.get(c, "not in schema") for c in summary.index]
        print(f"\n{name}:")
        print(summary.to_string())
    issues += validate_nulls(df, schema)

sys.exit(report(issues, "null check"))
