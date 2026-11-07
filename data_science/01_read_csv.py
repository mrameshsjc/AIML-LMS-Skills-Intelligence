"""
01 - Create DataFrames and read CSV files with Pandas.

LESSON
    1. Build a DataFrame by hand (from a Python dict).
    2. Do a calculation on a whole column at once.
    3. Read one CSV file with pd.read_csv and look at it.
    4. Why we read raw text first, and convert types later.
    5. Load all 11 LMS files with our loader.

KEY IDEAS
    DataFrame   a table: rows + named columns (like one Excel sheet)
    Series      one column of a DataFrame
    dtype       the data type of a column (int64, float64, str, datetime64, ...)
    shape       (number of rows, number of columns)

HOW TO RUN (from the project folder)
    PS> python data_science/01_read_csv.py

INPUT    data/sample/*.csv (or --data <folder>)
OUTPUT   printed tables; nothing is written to disk
"""

import pandas as pd
from _common import explain, heading, parse_args  # sets up imports

from app.data_processing.loader import load_dataset, load_raw, resolve_folder
from app.data_processing.schemas import DATASET_NAMES

args = parse_args("Lesson 01: create DataFrames and read CSV files.")
folder = resolve_folder(args.data)

# ---------------------------------------------------------------------------
heading("1. Create a DataFrame by hand")
explain("""
A dict of lists becomes a table: each key is a column name, each list is that column.
This is the worked example from the requirements: E1001 wants to become a Data Engineer.
""")
example = pd.DataFrame(
    {
        "skill": ["Python", "SQL", "AWS", "Machine Learning", "Docker"],
        "current_level": [3, 2, 1, 2, 2],
        "required_level": [4, 4, 3, 2, 3],
    }
)
print(example)
print(f"\nshape = {example.shape}  ->  {example.shape[0]} rows, {example.shape[1]} columns")

# ---------------------------------------------------------------------------
heading("2. Calculate on whole columns at once")
explain("""
Pandas works on entire columns in one line (called "vectorised" operations) - no for-loop needed.
.clip(lower=0) turns negative gaps into 0: a skill above the required level has no gap.
""")
example["gap"] = (example["required_level"] - example["current_level"]).clip(lower=0)
print(example)
skills_with_gap = (example["gap"] > 0).sum()
print(f"\nTotal gap = {example['gap'].sum()} levels; skills with a gap: {skills_with_gap} of {len(example)}")

# ---------------------------------------------------------------------------
heading("3. Read one CSV file: training_history.csv")
explain("""
pd.read_csv reads a CSV file into a DataFrame. By default Pandas GUESSES each column's type.
head() shows the first rows; shape gives (rows, columns); dtypes shows the guessed types.
""")
history = pd.read_csv(folder / "training_history.csv")
print(history.head())
print(f"\nshape   = {history.shape}")
print(f"columns = {list(history.columns)}")
print("\nGuessed dtypes:")
print(history.dtypes.to_string())
explain("""
Look closely at two guesses:
- score became a DECIMAL type (float64) although scores are whole numbers: some cells are empty,
  and the classic int64 type cannot hold an empty value.
- the date columns stayed TEXT: Pandas does not turn text into dates unless asked.
""")

# ---------------------------------------------------------------------------
heading("4. Raw text first, types later")
explain("""
Our loader avoids guessing. It reads every value as TEXT first (load_raw), so validation can report a
value like "ten" in a number column instead of it silently becoming empty.
After validation, load_dataset(..., typed=True) converts columns to the types declared in schemas.py:
Int64 (capital I) = whole numbers that may be empty, datetime64 = dates, boolean = True/False.
""")
raw = load_raw("training_history.csv", folder)
typed = load_dataset("training_history.csv", folder, typed=True)
print(
    pd.DataFrame(
        {
            "pandas guess": history.dtypes.astype(str),
            "raw (load_raw)": raw.dtypes.astype(str),
            "typed (load_dataset)": typed.dtypes.astype(str),
        }
    )
)

# ---------------------------------------------------------------------------
heading("5. Load all 11 LMS files")
rows = []
for name in DATASET_NAMES:
    df = load_raw(name, folder)
    rows.append({"file": name, "rows": len(df), "columns": len(df.columns)})
overview = pd.DataFrame(rows)
print(overview.to_string(index=False))
print(f"\nTotal: {overview['rows'].sum()} rows in {len(overview)} files from {folder}")
