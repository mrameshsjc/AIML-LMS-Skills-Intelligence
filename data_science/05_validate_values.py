"""
05 - Validate values: ranges, allowed values, formats, rules and references.

LESSON
    A value can be the right TYPE and still be WRONG. This script checks:

      ranges          current_level must be 1-5; score 0-100
      allowed values  status must be Enrolled, In Progress, Completed or Dropped
      formats         IDs like E1001, SK004, C-SQL-201; emails contain @
      dates           no date after the data's as-of date (2026-10-31)
      business rules  rules across columns of one row, e.g.
                      level_to > level_from; completed_date >= enrolled_date;
                      only completed courses have a score
      references      IDs that point to other files must exist there
                      (foreign keys), e.g. every skill_id in employee_skills.csv
                      must exist in skills.csv

    Useful Pandas:
      pd.to_numeric(col, errors="coerce")   text -> numbers (bad values become NaN)
      col.between(1, 5)                      True where 1 <= value <= 5
      col.isin(["a", "b"])                   True where the value is in the list
      ~mask                                  NOT: flips True and False

HOW TO RUN (from the project folder)
    PS> python data_science/05_validate_values.py
    PS> python data_science/05_validate_values.py --data data/raw/dirty

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   value, rule and reference issues; exit code 1 if any error
"""

import sys

import pandas as pd
from _common import explain, heading, parse_args, report

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import BUSINESS_RULES, Issue, validate_references, validate_values

args = parse_args("Lesson 05: check value ranges, rules and references.")
folder = resolve_folder(args.data)

heading("A small example first")
explain("""
Three skill levels, one of them out of range. between(1, 5) marks the valid ones;
~ flips the mask so we can keep the INVALID rows.
""")
levels = pd.DataFrame({"employee_id": ["E1001", "E1002", "E1003"], "current_level": [3, 7, 1]})
bad = ~levels["current_level"].between(1, 5)
print(levels.assign(valid=~bad).to_string(index=False))
print(f"\nInvalid rows:\n{levels[bad].to_string(index=False)}")

heading(f"Checking values in {folder}")
datasets: dict[str, pd.DataFrame] = {}
issues: list[Issue] = []
for name, schema in SCHEMAS.items():
    try:
        datasets[name] = load_raw(name, folder)
    except FileNotFoundError:
        print(f"  MISSING  {name}")
        continue
    found = validate_values(datasets[name], schema)
    issues += found
    rules = len(BUSINESS_RULES.get(name, []))
    print(f"  {'OK     ' if not found else 'PROBLEM'}  {name:<28}{rules} business rule(s)")

heading("Checking references between files (foreign keys)")
explain("""
For every link (e.g. employee_skills.skill_id -> skills.skill_id), each value must exist in the
other file. A missing target usually means a typo, or a row deleted from the other file.
""")
for name in datasets:
    for fk in SCHEMAS[name].foreign_keys:
        print(f"  {name}.{fk.column}  ->  {fk.ref_dataset}.{fk.ref_column}")
issues += validate_references(datasets)

sys.exit(report(issues, "value, rule and reference check"))
