"""
02 - Inspect the data: what is in each file?

LESSON
    Before checking or using data, LOOK at it. This script shows the standard
    Pandas inspection tools on one file, then a quick overview of all 11 files.

      info()           columns, types and how many values are filled in
      describe()       statistics: count, mean, min, max, most common value
      value_counts()   how often each value appears in a column
      nunique()        how many different values each column has
      filtering        df[df["column"] == value] keeps matching rows
      groupby          split rows into groups and summarise each group

HOW TO RUN (from the project folder)
    PS> python data_science/02_inspect_data.py
    PS> python data_science/02_inspect_data.py --dataset training_history.csv
    PS> python data_science/02_inspect_data.py --data data/raw/dirty

INPUT    data/sample/*.csv (or --data <folder>)
OUTPUT   printed tables
"""

import pandas as pd
from _common import explain, heading, parse_args

from app.data_processing.loader import load_dataset, load_raw, resolve_folder
from app.data_processing.schemas import DATASET_NAMES

args = parse_args("Lesson 02: inspect a dataset.", with_dataset=True)
folder = resolve_folder(args.data)
name = args.dataset
df = load_raw(name, folder)

# ---------------------------------------------------------------------------
heading(f"1. {name}: first and last rows")
print(df.head(3).to_string())
print("...")
print(df.tail(2).to_string())

# ---------------------------------------------------------------------------
heading("2. info(): columns, filled-in values and types")
explain("""
'Non-Null Count' = how many cells have a value. If it is less than the number of rows,
some cells are empty. (All types show as text here because we loaded the raw file.)
""")
df.info()

# ---------------------------------------------------------------------------
heading("3. describe(): statistics")
explain("""
describe() summarises each column. Text, numbers and dates get different statistics:
- text:     count (filled cells), unique (different values), top (most common), freq (how often)
- numbers:  mean (average), std (spread), min, 25% / 50% (median) / 75% (quartiles), max
- dates:    how many are filled in, and the first and last date
""")
typed = load_dataset(name, folder, typed=True)
numbers = typed.select_dtypes(include="number").columns
dates = typed.select_dtypes(include="datetime").columns
text = [c for c in typed.columns if c not in numbers and c not in dates]
print("Text columns:")
print(typed[text].describe().T.to_string())
if len(numbers):
    print("\nNumber columns:")
    print(typed[numbers].astype(float).describe().T.round(2).to_string())
if len(dates):
    print("\nDate columns:")
    print(
        pd.DataFrame(
            {
                "filled": typed[dates].count(),
                "first": typed[dates].min().dt.date,
                "last": typed[dates].max().dt.date,
            }
        ).to_string()
    )

# ---------------------------------------------------------------------------
heading("4. nunique() and value_counts(): how varied is each column?")
print(df.nunique().to_frame("different values").to_string())
low_variety = [c for c in df.columns if 1 < df[c].nunique() <= 12]
for col in low_variety[:3]:
    print(f"\nvalue_counts() of '{col}':")
    print(df[col].value_counts(dropna=False).to_string())

# ---------------------------------------------------------------------------
heading("5. Filtering and grouping (examples on employees.csv)")
emp = load_raw("employees.csv", folder)
explain("""
Filtering: emp[emp["location"] == "Chennai"] keeps only the rows where the condition is True.
Grouping:  emp.groupby("department").size() counts employees per department.
""")
chennai = emp[emp["location"] == "Chennai"]
print(f"Employees in Chennai: {len(chennai)} of {len(emp)}")
print(chennai[["employee_id", "first_name", "last_name", "department"]].head().to_string(index=False))
print("\nEmployees per department:")
print(emp.groupby("department").size().sort_values(ascending=False).to_string())

# ---------------------------------------------------------------------------
heading("6. Overview of all 11 files")
explain("""
A first health check across files: size, empty cells and exact duplicate rows.
Empty cells are not always wrong: completed_date and score stay empty until a course is completed,
and top managers have no manager_id. Scripts 03-06 decide what is really a problem.
""")
rows = []
for n in DATASET_NAMES:
    d = load_raw(n, folder)
    rows.append({
        "file": n,
        "rows": len(d),
        "columns": d.shape[1],
        "empty cells": int(d.isna().sum().sum()),
        "duplicate rows": int(d.duplicated().sum()),
        "memory KB": round(d.memory_usage(deep=True).sum() / 1024, 1),
    })  # fmt: skip
print(pd.DataFrame(rows).to_string(index=False))
