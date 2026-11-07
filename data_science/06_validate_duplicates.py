"""
06 - Validate duplicates: is anything entered twice?

LESSON
    Three kinds of duplicates:

      exact duplicate rows   the whole row appears twice (copy-paste, double import)
      repeated primary key   two rows with the same ID, e.g. two rows for
                             E1031, or the same employee + skill twice with
                             different levels - which one is true?
      repeated unique value  e.g. the same email for two employees

    Useful Pandas:
      df.duplicated()                       True for the 2nd, 3rd ... copy of a row
      df.duplicated(keep=False)             True for EVERY copy (shows all involved)
      df.duplicated(subset=["a", "b"])      compare only columns a and b (a key)
      df.drop_duplicates()                  remove exact copies (cleaning, Phase 4)

HOW TO RUN (from the project folder)
    PS> python data_science/06_validate_duplicates.py
    PS> python data_science/06_validate_duplicates.py --data data/raw/dirty

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   duplicate issues and the duplicated rows themselves; exit code 1 if any error
"""

import sys

from _common import explain, heading, parse_args, report

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import Issue, validate_duplicates

args = parse_args("Lesson 06: find duplicate rows and keys.")
folder = resolve_folder(args.data)

heading(f"Checking duplicates in {folder}")
explain("""
For each file: exact duplicate rows, then the primary key (from schemas.py), then any column
that must be unique (e.g. email). keep=False marks every copy so you see all lines involved.
""")

issues: list[Issue] = []
for name, schema in SCHEMAS.items():
    try:
        df = load_raw(name, folder)
    except FileNotFoundError:
        print(f"  MISSING  {name}")
        continue
    found = validate_duplicates(df, schema)
    issues += found
    print(f"  {'OK     ' if not found else 'PROBLEM'}  {name:<28}key = {', '.join(schema.primary_key)}")
    key = list(schema.primary_key)
    if found and all(k in df.columns for k in key):
        repeated = df[df.duplicated(subset=key, keep=False)].sort_values(key)
        repeated.index = repeated.index + 2  # Pandas row number -> CSV line number
        repeated.index.name = "line"
        print(repeated.head(6).to_string())

sys.exit(report(issues, "duplicate check"))
