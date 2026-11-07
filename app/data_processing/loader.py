"""
Loading the LMS CSV files with Pandas.

PURPOSE
    Read CSV files into Pandas DataFrames in two ways:

    1. RAW (`typed=False`): every value is kept exactly as text. This is what the
       validation checks need: if a file says duration_hours = "ten", we want to
       SEE "ten" and report it, not have Pandas silently turn it into NaN.

    2. TYPED (`typed=True`): numbers become numbers, dates become dates and
       True/False become booleans, using the types in `schemas.py`. This is what
       the analysis code in later phases uses, after the data has passed validation.

WHAT IS A DATAFRAME?
    A table in memory: rows and named columns, like a spreadsheet sheet.
    `df["current_level"]` is one column (a "Series"); `df.head()` shows the first
    5 rows; `df.shape` is (rows, columns).

WHY THESE read_csv OPTIONS
    dtype=str              keep every value as text (no guessing of types)
    keep_default_na=False  do not treat words like "NA" or "null" as missing...
    na_values=[""]         ...only a truly empty cell counts as missing (NaN)
    These make the result predictable on every machine and Pandas version.

HOW TO TRY IT
    PS> python -c "from app.data_processing.loader import load_dataset as ld; print(ld('employees.csv'))"
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.data_processing.schemas import DATASET_NAMES, SCHEMAS, DatasetSchema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


def resolve_folder(folder: str | Path | None) -> Path:
    """Turn a folder argument into an absolute path (relative paths start at the project root)."""
    if folder is None:
        return SAMPLE_DIR
    path = Path(folder)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_raw(name: str, folder: str | Path | None = None) -> pd.DataFrame:
    """Read one CSV file with every value as text; empty cells become NaN.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = resolve_folder(folder) / name
    if not path.exists():
        raise FileNotFoundError(f"{name} not found in {path.parent}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")


def to_typed(df: pd.DataFrame, schema: DatasetSchema) -> pd.DataFrame:
    """Convert raw text columns to the types declared in the schema.

    Values that cannot be converted become missing (NaN/NaT) instead of
    crashing. That is why validation must run BEFORE this step: it reports
    such values so they can be fixed, rather than letting them disappear.

    Integer columns use Pandas' nullable "Int64" type (capital I), which can
    hold missing values. The normal int64 type cannot.
    """
    typed = df.copy()
    for spec in schema.columns:
        if spec.name not in typed.columns:
            continue  # missing column: reported by schema validation
        col = typed[spec.name]
        if spec.dtype == "int":
            typed[spec.name] = pd.to_numeric(col, errors="coerce").round().astype("Int64")
        elif spec.dtype == "float":
            typed[spec.name] = pd.to_numeric(col, errors="coerce").astype("Float64")
        elif spec.dtype == "date":
            typed[spec.name] = pd.to_datetime(col, format="%Y-%m-%d", errors="coerce")
        elif spec.dtype == "bool":
            typed[spec.name] = col.map({"True": True, "False": False}).astype("boolean")
    return typed


def load_dataset(name: str, folder: str | Path | None = None, typed: bool = True) -> pd.DataFrame:
    """Load one LMS dataset by file name, e.g. `load_dataset("courses.csv")`."""
    if name not in SCHEMAS:
        raise ValueError(f"Unknown dataset {name!r}. Known: {', '.join(DATASET_NAMES)}")
    raw = load_raw(name, folder)
    return to_typed(raw, SCHEMAS[name]) if typed else raw


def load_all(folder: str | Path | None = None, typed: bool = True) -> dict[str, pd.DataFrame]:
    """Load all 11 datasets into a dict {file name: DataFrame}."""
    return {name: load_dataset(name, folder, typed) for name in DATASET_NAMES}
