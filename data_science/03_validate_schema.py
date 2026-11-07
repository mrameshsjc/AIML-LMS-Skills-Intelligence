"""
03 - Validate the schema: right columns, right types?

LESSON
    A schema is the agreed shape of a file: which columns exist, in which
    order, and what type of value each column holds (see
    app/data_processing/schemas.py). This script compares every file with its
    schema and reports:

      missing column      (error)    a column the engine needs is not there
      unexpected column   (warning)  an extra column; it will be ignored
      different order     (warning)  same columns, different order
      wrong type          (error)    e.g. "ten" in a number column, or a date
                                     not written as YYYY-MM-DD

WHY IT COMES FIRST
    Every later check looks up columns by name. If a column is missing or
    renamed, those checks cannot run for it, so we find that out first.

HOW TO RUN (from the project folder)
    PS> python data_science/03_validate_schema.py                       # clean data
    PS> python scripts/make_dirty_data.py                               # once
    PS> python data_science/03_validate_schema.py --data data/raw/dirty # dirty data

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   a table of schema issues; exit code 1 if any error (useful in CI)
"""

import sys

from _common import explain, heading, parse_args, report

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import Issue, validate_schema

args = parse_args("Lesson 03: validate columns and types.")
folder = resolve_folder(args.data)

heading(f"Checking columns and types in {folder}")
explain("""
For each file: expected columns (from schemas.py) vs actual columns (from the CSV header),
then every non-text value is checked: can it be read as an int / float / date / bool?
""")

issues: list[Issue] = []
for name, schema in SCHEMAS.items():
    try:
        df = load_raw(name, folder)
    except FileNotFoundError as exc:
        issues.append(Issue(name, "schema", "error", "*", str(exc)))
        print(f"  MISSING  {name}")
        continue
    found = validate_schema(df, schema)
    issues += found
    print(f"  {'OK     ' if not found else 'PROBLEM'}  {name:<28}{len(df.columns):>3} columns")
    missing = [c for c in schema.column_names if c not in df.columns]
    extra = [c for c in df.columns if c not in schema.column_names]
    if missing or extra:
        print(f"           expected but missing: {missing or '-'}")
        print(f"           present but unexpected: {extra or '-'}")

sys.exit(report(issues, "schema check"))
