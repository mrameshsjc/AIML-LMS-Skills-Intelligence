"""
Data validation: find problems in the LMS CSV files before we use them.

PURPOSE
    Every check here returns a list of `Issue` objects. An Issue says WHAT is
    wrong, WHERE (file, column, CSV line numbers) and HOW SERIOUS it is:
      error   - the data is wrong and must be fixed before use;
      warning - suspicious but usable (for example, an extra column).

THE FIVE CHECKS (each one has a learning script in data_science/)
    1. validate_schema      03_validate_schema.py      right columns? right types?
    2. validate_nulls       04_validate_nulls.py       empty values where not allowed?
    3. validate_values      05_validate_values.py      ranges, allowed values, ID formats,
                                                       dates not in the future, business rules
    4. validate_references  05_validate_values.py      do IDs point to existing rows?
    5. validate_duplicates  06_validate_duplicates.py  repeated rows or keys?

WHY RAW TEXT INPUT
    Checks work on the RAW DataFrame (every value as text, see loader.py), so
    a bad value such as "ten" in a number column is reported, not hidden.

CSV LINE NUMBERS
    Pandas numbers rows from 0, and line 1 of a CSV file is the header.
    So DataFrame row i is CSV line i + 2. Issues report CSV line numbers,
    which you can find directly in Excel or PyCharm.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import DATA_AS_OF, SCHEMAS, TRAINING_STATUSES, DatasetSchema

MAX_EXAMPLES = 5  # how many example lines to show per issue


@dataclass
class Issue:
    """One problem found in the data."""

    dataset: str
    check: str  # schema | nulls | values | rules | references | duplicates
    severity: str  # error | warning
    column: str
    message: str
    rows: int = 0  # how many rows are affected (0 = whole file/column)
    lines: list[int] = field(default_factory=list)  # example CSV line numbers

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "check": self.check,
            "severity": self.severity,
            "column": self.column,
            "rows": self.rows,
            "lines": ", ".join(map(str, self.lines)),
            "message": self.message,
        }


def _lines(mask: pd.Series) -> list[int]:
    """CSV line numbers (header = line 1) of the first rows where mask is True."""
    return [int(i) + 2 for i in mask[mask].index[:MAX_EXAMPLES]]


def _issue(
    schema: DatasetSchema, check: str, column: str, mask: pd.Series, message: str, severity: str = "error"
) -> list[Issue]:
    """Create an Issue from a True/False mask of bad rows, or nothing if no row is bad."""
    count = int(mask.sum())
    if count == 0:
        return []
    return [Issue(schema.name, check, severity, column, message, count, _lines(mask))]


# ---------------------------------------------------------------------------
# Type conversion helpers: which non-empty values cannot be read as the type?
# ---------------------------------------------------------------------------
def invalid_type_mask(series: pd.Series, dtype: str) -> pd.Series:
    """True where a non-empty value cannot be converted to `dtype`."""
    present = series.notna()
    if dtype == "int":
        numbers = pd.to_numeric(series, errors="coerce")
        return present & (numbers.isna() | (numbers % 1 != 0))
    if dtype == "float":
        return present & pd.to_numeric(series, errors="coerce").isna()
    if dtype == "date":
        return present & pd.to_datetime(series, format="%Y-%m-%d", errors="coerce").isna()
    if dtype == "bool":
        return present & ~series.isin(["True", "False"])
    return pd.Series(False, index=series.index)


# ---------------------------------------------------------------------------
# 1. Schema: columns and types
# ---------------------------------------------------------------------------
def validate_schema(df: pd.DataFrame, schema: DatasetSchema) -> list[Issue]:
    """Check column names, column order and value types."""
    issues: list[Issue] = []
    expected, actual = list(schema.column_names), list(df.columns)

    for col in expected:
        if col not in actual:
            issues.append(Issue(schema.name, "schema", "error", col, "Required column is missing."))
    for col in actual:
        if col not in expected:
            issues.append(
                Issue(schema.name, "schema", "warning", col, "Unexpected column (will be ignored).")
            )
    if set(expected) == set(actual) and expected != actual:
        issues.append(Issue(schema.name, "schema", "warning", "*", "Columns are in a different order."))

    for spec in schema.columns:
        if spec.name in df.columns and spec.dtype != "string":
            fmt = {"date": " (expected YYYY-MM-DD)", "bool": " (expected True or False)"}.get(spec.dtype, "")
            issues += _issue(
                schema,
                "schema",
                spec.name,
                invalid_type_mask(df[spec.name], spec.dtype),
                f"Value is not a valid {spec.dtype}{fmt}.",
            )
    return issues


# ---------------------------------------------------------------------------
# 2. Nulls: empty values in required columns
# ---------------------------------------------------------------------------
def validate_nulls(df: pd.DataFrame, schema: DatasetSchema) -> list[Issue]:
    """Required columns must not contain empty values."""
    issues: list[Issue] = []
    for spec in schema.columns:
        if spec.required and spec.name in df.columns:
            issues += _issue(schema, "nulls", spec.name, df[spec.name].isna(), "Required value is empty.")
    return issues


def null_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Table of empty values per column: count and percentage (used by script 04)."""
    counts = df.isna().sum()
    return pd.DataFrame({"empty": counts, "percent": (counts / max(len(df), 1) * 100).round(1)})


# ---------------------------------------------------------------------------
# 3. Values: ranges, allowed values, ID formats, dates, business rules
# ---------------------------------------------------------------------------
def validate_values(df: pd.DataFrame, schema: DatasetSchema) -> list[Issue]:
    """Check each value against its column's rules, then the file's business rules.

    Values with the wrong type are skipped here; validate_schema reports them.
    """
    issues: list[Issue] = []
    for spec in schema.columns:
        if spec.name not in df.columns:
            continue
        col = df[spec.name]

        if spec.dtype in ("int", "float"):
            numbers = pd.to_numeric(col, errors="coerce")
            if spec.min_value is not None:
                issues += _issue(
                    schema,
                    "values",
                    spec.name,
                    numbers < spec.min_value,
                    f"Value is below the minimum of {spec.min_value:g}.",
                )
            if spec.max_value is not None:
                issues += _issue(
                    schema,
                    "values",
                    spec.name,
                    numbers > spec.max_value,
                    f"Value is above the maximum of {spec.max_value:g}.",
                )

        if spec.dtype == "date":
            dates = pd.to_datetime(col, format="%Y-%m-%d", errors="coerce")
            issues += _issue(
                schema,
                "values",
                spec.name,
                dates > pd.Timestamp(DATA_AS_OF),
                f"Date is after the data's as-of date ({DATA_AS_OF}).",
            )

        if spec.allowed is not None:
            bad = col.notna() & ~col.isin(spec.allowed)
            issues += _issue(
                schema, "values", spec.name, bad, f"Value is not one of: {', '.join(spec.allowed)}."
            )

        if spec.pattern is not None:
            bad = col.notna() & ~col.astype("string").str.fullmatch(spec.pattern).fillna(False).astype(bool)
            issues += _issue(schema, "values", spec.name, bad, "Value does not match the expected format.")

    for rule in BUSINESS_RULES.get(schema.name, []):
        if all(c in df.columns for c in rule.columns):
            issues += _issue(schema, "rules", ", ".join(rule.columns), rule.check(df), rule.message)
    return issues


@dataclass(frozen=True)
class BusinessRule:
    """A rule that compares several columns of the same row.

    `check(df)` returns True for every row that BREAKS the rule.
    """

    columns: tuple[str, ...]
    message: str
    check: Callable[[pd.DataFrame], pd.Series]


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def _date(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")


def _status(df: pd.DataFrame, *values: str) -> pd.Series:
    return df["status"].isin(values)


BUSINESS_RULES: dict[str, list[BusinessRule]] = {
    "course_skills.csv": [
        BusinessRule(
            ("level_from", "level_to"),
            "level_to must be higher than level_from.",
            lambda df: _num(df, "level_to") <= _num(df, "level_from"),
        ),
    ],
    "course_prerequisites.csv": [
        BusinessRule(
            ("course_id", "prerequisite_course_id"),
            "A course cannot require itself.",
            lambda df: df["course_id"] == df["prerequisite_course_id"],
        ),
    ],
    "employees.csv": [
        BusinessRule(
            ("employee_id", "manager_id"),
            "An employee cannot be their own manager.",
            lambda df: df["employee_id"] == df["manager_id"],
        ),
    ],
    # Status rules only look at rows whose status is valid; an invalid status is
    # already reported once by the allowed-values check.
    "training_history.csv": [
        BusinessRule(
            ("status", "completed_date", "score"),
            "Completed courses need a completed_date and a score.",
            lambda df: _status(df, "Completed") & (df["completed_date"].isna() | df["score"].isna()),
        ),
        BusinessRule(
            ("status", "completed_date", "score"),
            "Only completed courses may have a completed_date or a score.",
            lambda df: (
                _status(df, *[s for s in TRAINING_STATUSES if s != "Completed"])
                & (df["completed_date"].notna() | df["score"].notna())
            ),
        ),
        BusinessRule(
            ("enrolled_date", "completed_date"),
            "completed_date is before enrolled_date.",
            lambda df: _date(df, "completed_date") < _date(df, "enrolled_date"),
        ),
    ],
}


# ---------------------------------------------------------------------------
# 4. References (foreign keys): IDs must point to existing rows
# ---------------------------------------------------------------------------
def validate_references(datasets: dict[str, pd.DataFrame]) -> list[Issue]:
    """Check every foreign key across the loaded datasets."""
    issues: list[Issue] = []
    for name, df in datasets.items():
        schema = SCHEMAS[name]
        for fk in schema.foreign_keys:
            parent = datasets.get(fk.ref_dataset)
            if fk.column not in df.columns or parent is None or fk.ref_column not in parent.columns:
                continue  # missing column/file: reported by other checks
            valid = set(parent[fk.ref_column].dropna())
            bad = df[fk.column].notna() & ~df[fk.column].isin(valid)
            examples = ", ".join(sorted(set(df.loc[bad, fk.column]))[:3])
            issues += _issue(
                schema,
                "references",
                fk.column,
                bad,
                f"Value not found in {fk.ref_dataset}.{fk.ref_column} (e.g. {examples}).",
            )
    return issues


# ---------------------------------------------------------------------------
# 5. Duplicates: repeated rows, primary keys and unique columns
# ---------------------------------------------------------------------------
def validate_duplicates(df: pd.DataFrame, schema: DatasetSchema) -> list[Issue]:
    """Find exact duplicate rows, repeated primary keys and repeated unique values.

    `keep=False` marks EVERY copy (not just the second one), so you can see
    all lines involved.
    """
    issues = _issue(schema, "duplicates", "*", df.duplicated(keep=False), "Exact duplicate rows.")
    for key in (schema.primary_key, *schema.unique):
        if all(k in df.columns for k in key):
            label = "Primary key" if key == schema.primary_key else "Unique value"
            # Empty keys are reported by validate_nulls; do not also count them as duplicates.
            filled = df[list(key)].notna().all(axis=1)
            repeated = df.duplicated(subset=list(key), keep=False) & filled
            issues += _issue(
                schema, "duplicates", ", ".join(key), repeated, f"{label} appears more than once."
            )
    return issues


# ---------------------------------------------------------------------------
# Run everything
# ---------------------------------------------------------------------------
CHECKS = {
    "schema": validate_schema,
    "nulls": validate_nulls,
    "values": validate_values,
    "duplicates": validate_duplicates,
}


def run_checks(
    folder: str | Path | None = None,
    checks: tuple[str, ...] = ("schema", "nulls", "values", "references", "duplicates"),
) -> list[Issue]:
    """Load all 11 files (raw) from `folder` and run the chosen checks.

    A missing file is itself reported as an error, and the other files are
    still checked.
    """
    datasets: dict[str, pd.DataFrame] = {}
    issues: list[Issue] = []
    for name, schema in SCHEMAS.items():
        try:
            datasets[name] = load_raw(name, folder)
        except FileNotFoundError:
            issues.append(Issue(name, "schema", "error", "*", f"File not found in {resolve_folder(folder)}."))
            continue
        for check in checks:
            if check in CHECKS:
                issues += CHECKS[check](datasets[name], schema)
    if "references" in checks:
        issues += validate_references(datasets)
    return issues


def issues_table(issues: list[Issue]) -> pd.DataFrame:
    """Turn issues into a DataFrame for printing or saving as CSV."""
    columns = ["dataset", "check", "severity", "column", "rows", "lines", "message"]
    return pd.DataFrame([i.as_dict() for i in issues], columns=columns)
