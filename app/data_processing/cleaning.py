"""
Data cleaning: fix what can safely be fixed, set aside what cannot.

PURPOSE
    Turn raw LMS files (which may contain the problems found by validation)
    into clean files the engine can trust. Every change is LOGGED, and every row
    that cannot be fixed is QUARANTINED (kept aside with a reason) instead of
    silently deleted. Nothing disappears without a trace.

THE GOLDEN RULE OF CLEANING
    Only fix a value when the correct answer is clear. "Complete" is clearly
    "Completed"; 31/12/2020 is clearly 2020-12-31. But an empty skill level
    or a level of 7 has no clear correct value - guessing would put invented
    data into the recommendations. Such rows are quarantined, so someone can
    fix them at the source.

THE STEPS (in this order, per file; each one is a small function below)
    1. columns     rename known alternative names, drop unexpected columns
    2. text        trim spaces; empty text becomes missing
    3. categories  fix letter case and known typos ("complete" -> "Completed")
    4. dates       accept DD/MM/YYYY etc. and rewrite as YYYY-MM-DD
    5. numbers     remove non-numbers; cap or quarantine out-of-range values
    6. missing     fill where a safe rule exists, otherwise quarantine
    7. rules       fix swapped level_from/level_to; quarantine other rule breaks
    8. duplicates  drop exact copies; keep one row per key, quarantine the rest
    Then, across files:
    9. references  rows pointing to missing IDs are quarantined (required
                   columns) or the reference is cleared (optional columns).
                   Repeated until nothing changes, because removing one row
                   can break references in another file (a "cascade").

OUTPUT
    cleaned DataFrames (same columns and order as the schema) + a
    CleaningReport with two tables: actions (what changed) and rejected
    (quarantined rows, with their original CSV line and the reason).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS, DatasetSchema
from app.data_processing.validators import BUSINESS_RULES, invalid_type_mask

LINE = "_line"  # helper column: the row's original CSV line number (header = line 1)

# ---------------------------------------------------------------------------
# Cleaning policies: the decisions, kept apart from the code that applies them.
# Change a policy here; the steps below follow it.
# ---------------------------------------------------------------------------

# Known alternative column names -> the schema's name.
COLUMN_ALIASES: dict[str, dict[str, str]] = {
    "job_roles.csv": {"seniority_level": "seniority", "level": "seniority"},
    "employees.csv": {"mail": "email", "email_address": "email", "date_of_joining": "hire_date"},
}

# Known typos per column name (applied in any file that has the column).
# Letter case is fixed automatically, so only real misspellings are listed.
VALUE_TYPOS: dict[str, dict[str, str]] = {
    "status": {
        "complete": "Completed",
        "done": "Completed",
        "inprogress": "In Progress",
        "in-progress": "In Progress",
        "enroled": "Enrolled",
        "dropout": "Dropped",
    },
    "difficulty": {"basic": "Beginner", "intermediate level": "Intermediate", "expert": "Advanced"},
}

# Date formats accepted on input, tried in this order. Output is always YYYY-MM-DD.
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")

# Out-of-range numbers: "cap" moves the value to the nearest limit; anything not
# listed is quarantined. Capping is only safe where the meaning is obvious
# (a score above 100 is a data-entry slip for 100).
CAP_OUT_OF_RANGE = {("training_history.csv", "score")}

# Empty required values that can be filled safely: (file, column) -> rule.
#   ("median_by", group_column)   median of the column within the same group
#   ("template", text)            fixed text built from other columns
FILL_MISSING = {
    ("courses.csv", "duration_hours"): ("median_by", "difficulty"),
    ("courses.csv", "course_title"): ("template", "Untitled course ({course_id})"),
}

# When the same key appears twice with different values, keep the row with the
# most recent date in this column (ties: the earliest line in the file).
NEWEST_BY = {"employee_skills.csv": "assessed_date", "career_goals.csv": "set_date"}


@dataclass
class CleaningReport:
    """Everything cleaning did: changes made and rows set aside."""

    actions: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    skipped_datasets: list[str] = field(default_factory=list)

    def log(self, step: str, dataset: str, column: str, rows: int, action: str) -> None:
        if rows:
            self.actions.append(
                {"step": step, "dataset": dataset, "column": column, "rows": rows, "action": action}
            )

    def reject(self, dataset: str, rows: pd.DataFrame, reason: str) -> None:
        """Quarantine rows: keep their original line and content, with the reason."""
        for _, row in rows.iterrows():
            record = "; ".join(f"{k}={v}" for k, v in row.items() if k != LINE and pd.notna(v))
            self.rejected.append(
                {"dataset": dataset, "line": int(row[LINE]), "reason": reason, "record": record}
            )

    def actions_table(self) -> pd.DataFrame:
        return pd.DataFrame(self.actions, columns=["step", "dataset", "column", "rows", "action"])

    def rejected_table(self) -> pd.DataFrame:
        return pd.DataFrame(self.rejected, columns=["dataset", "line", "reason", "record"])


def _quarantine(
    df: pd.DataFrame, mask: pd.Series, report: CleaningReport, name: str, reason: str
) -> pd.DataFrame:
    """Move rows where mask is True into the report; return the remaining rows."""
    if mask.any():
        report.reject(name, df[mask], reason)
    return df[~mask]


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------
def _fix_columns(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame | None:
    name = schema.name
    renames = {
        a: c for a, c in COLUMN_ALIASES.get(name, {}).items() if a in df.columns and c not in df.columns
    }
    for old, new in renames.items():
        report.log("columns", name, new, len(df), f"renamed column '{old}' to '{new}'")
    df = df.rename(columns=renames)

    extra = [c for c in df.columns if c not in schema.column_names and c != LINE]
    for col in extra:
        report.log("columns", name, col, len(df), "dropped unexpected column")

    missing = [c for c in schema.column_names if c not in df.columns]
    if missing:
        report.log("columns", name, ", ".join(missing), len(df), "FILE SKIPPED: required column missing")
        report.skipped_datasets.append(name)
        return None
    return df[[LINE, *schema.column_names]]  # schema order, extras dropped


def _fix_text(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    for col in schema.column_names:
        original = df[col]
        stripped = original.str.strip()
        stripped = stripped.mask(stripped == "")  # blank text -> missing
        changed = original.notna() & (stripped.isna() | (stripped != original))
        if changed.any():
            df[col] = stripped
            report.log("text", schema.name, col, int(changed.sum()), "trimmed spaces / emptied blank text")
    return df


def _fix_categories(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    for spec in schema.columns:
        if spec.allowed is None:
            continue
        lookup = {a.lower(): a for a in spec.allowed}
        lookup |= {k.lower(): v for k, v in VALUE_TYPOS.get(spec.name, {}).items()}
        col = df[spec.name]
        fixed = col.map(lambda v, lk=lookup: lk.get(v.lower(), v) if isinstance(v, str) else v)
        changed = col.notna() & (fixed != col)
        if changed.any():
            df[spec.name] = fixed
            examples = ", ".join(
                sorted({f"'{a}'->'{b}'" for a, b in zip(col[changed], fixed[changed], strict=True)})
            )
            report.log("categories", schema.name, spec.name, int(changed.sum()), f"standardised {examples}")
    return df


def _parse_date(value: str) -> str | None:
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _fix_dates(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    for spec in schema.columns:
        if spec.dtype != "date":
            continue
        col = df[spec.name]
        parsed = col.map(lambda v: _parse_date(v) if isinstance(v, str) else None)
        reformatted = col.notna() & parsed.notna() & (parsed != col)
        unreadable = col.notna() & parsed.isna()
        if reformatted.any():
            report.log("dates", schema.name, spec.name, int(reformatted.sum()), "rewrote date as YYYY-MM-DD")
        if unreadable.any():
            report.log("dates", schema.name, spec.name, int(unreadable.sum()), "removed unreadable date")
        df[spec.name] = parsed.where(col.notna(), None)
    return df


def _format_number(value: float, dtype: str) -> str:
    return str(int(value)) if dtype == "int" else str(float(value))


def _fix_numbers(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    for spec in schema.columns:
        if spec.dtype not in ("int", "float"):
            continue
        bad = invalid_type_mask(df[spec.name], spec.dtype)
        if bad.any():
            examples = ", ".join(sorted(set(df.loc[bad, spec.name]))[:3])
            df.loc[bad, spec.name] = None
            report.log(
                "numbers", schema.name, spec.name, int(bad.sum()), f"removed non-numeric value ({examples})"
            )

        numbers = pd.to_numeric(df[spec.name], errors="coerce")
        never = pd.Series(False, index=df.index)
        low = numbers < spec.min_value if spec.min_value is not None else never
        high = numbers > spec.max_value if spec.max_value is not None else never
        if not (low | high).any():
            continue
        if (schema.name, spec.name) in CAP_OUT_OF_RANGE:
            df.loc[low, spec.name] = _format_number(spec.min_value, spec.dtype)
            df.loc[high, spec.name] = _format_number(spec.max_value, spec.dtype)
            report.log(
                "numbers",
                schema.name,
                spec.name,
                int((low | high).sum()),
                f"capped to the range {spec.min_value:g}-{spec.max_value:g}",
            )
        else:
            df = _quarantine(
                df,
                low | high,
                report,
                schema.name,
                f"{spec.name} outside {spec.min_value:g}-{spec.max_value:g}",
            )
    return df


def _fill_missing(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    for spec in schema.columns:
        if not spec.required:
            continue
        missing = df[spec.name].isna()
        if not missing.any():
            continue
        rule = FILL_MISSING.get((schema.name, spec.name))
        if rule and rule[0] == "median_by":
            group = rule[1]
            numbers = pd.to_numeric(df[spec.name], errors="coerce")
            medians = numbers.groupby(df[group]).median()
            fill = df.loc[missing, group].map(medians)
            df.loc[missing, spec.name] = fill.map(
                lambda v, dtype=spec.dtype: None if pd.isna(v) else _format_number(v, dtype)
            )
            report.log(
                "missing",
                schema.name,
                spec.name,
                int(fill.notna().sum()),
                f"filled with the median for the same {group}",
            )
        elif rule and rule[0] == "template":
            df.loc[missing, spec.name] = df.loc[missing].apply(lambda r, t=rule[1]: t.format(**r), axis=1)
            report.log(
                "missing", schema.name, spec.name, int(missing.sum()), f"filled with '{rule[1]}' (review)"
            )
        still_missing = df[spec.name].isna()
        df = _quarantine(df, still_missing, report, schema.name, f"required value missing: {spec.name}")
    return df


def _fix_rules(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    if schema.name == "course_skills.csv":
        start = pd.to_numeric(df["level_from"], errors="coerce")
        end = pd.to_numeric(df["level_to"], errors="coerce")
        swapped = end < start
        if swapped.any():
            df.loc[swapped, ["level_from", "level_to"]] = df.loc[
                swapped, ["level_to", "level_from"]
            ].to_numpy()
            report.log(
                "rules", schema.name, "level_from, level_to", int(swapped.sum()), "swapped back into order"
            )
    for rule in BUSINESS_RULES.get(schema.name, []):
        df = _quarantine(df, rule.check(df).fillna(False).astype(bool), report, schema.name, rule.message)
    return df


def _fix_duplicates(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame:
    exact = df.duplicated(subset=list(schema.column_names), keep="first")
    if exact.any():
        report.log("duplicates", schema.name, "*", int(exact.sum()), "removed exact duplicate rows")
        df = df[~exact]

    # Decide which copy of a repeated key to keep: newest date first, then earliest line.
    newest = NEWEST_BY.get(schema.name)
    if newest:
        df = df.sort_values([newest, LINE], ascending=[False, True], na_position="last")
    else:
        df = df.sort_values(LINE)
    for key in (schema.primary_key, *schema.unique):
        repeated = df.duplicated(subset=list(key), keep="first") & df[list(key)].notna().all(axis=1)
        df = _quarantine(df, repeated, report, schema.name, f"duplicate {', '.join(key)} (another row kept)")
    return df.sort_values(LINE)


STEPS = (_fix_text, _fix_categories, _fix_dates, _fix_numbers, _fill_missing, _fix_rules, _fix_duplicates)


def clean_dataset(df: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> pd.DataFrame | None:
    """Clean one raw DataFrame. Returns None if the file cannot be used at all."""
    df = df.copy()
    df.insert(0, LINE, df.index + 2)
    df = _fix_columns(df, schema, report)
    if df is None:
        return None
    for step in STEPS:
        df = step(df, schema, report)
    return df


def _fix_references(cleaned: dict[str, pd.DataFrame], report: CleaningReport) -> None:
    """Remove or clear broken references, repeating until nothing changes."""
    changed = True
    while changed:
        changed = False
        for name in list(cleaned):
            schema = SCHEMAS[name]
            for fk in schema.foreign_keys:
                parent = cleaned.get(fk.ref_dataset)
                if parent is None:
                    continue
                df = cleaned[name]
                bad = df[fk.column].notna() & ~df[fk.column].isin(set(parent[fk.ref_column].dropna()))
                if not bad.any():
                    continue
                changed = True
                if schema.column(fk.column).required:
                    cleaned[name] = _quarantine(
                        df, bad, report, name, f"{fk.column} not found in {fk.ref_dataset}"
                    )
                else:
                    df = df.copy()
                    df.loc[bad, fk.column] = None
                    cleaned[name] = df
                    report.log(
                        "references",
                        name,
                        fk.column,
                        int(bad.sum()),
                        f"cleared: not found in {fk.ref_dataset}",
                    )


def clean_all(datasets: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], CleaningReport]:
    """Clean every given raw dataset, then fix references across them."""
    report = CleaningReport()
    cleaned: dict[str, pd.DataFrame] = {}
    for name, schema in SCHEMAS.items():
        if name in datasets:
            result = clean_dataset(datasets[name], schema, report)
            if result is not None:
                cleaned[name] = result
    _fix_references(cleaned, report)
    return cleaned, report


def clean_folder(source: str | Path | None, target: str | Path) -> CleaningReport:
    """Read the 11 raw files from `source`, clean them and write the results to `target`.

    Writes the cleaned CSV files plus cleaning_log.csv and rejected_rows.csv.
    Missing input files are noted in the report and skipped.
    """
    raw: dict[str, pd.DataFrame] = {}
    missing_files = []
    for name in SCHEMAS:
        try:
            raw[name] = load_raw(name, source)
        except FileNotFoundError:
            missing_files.append(name)
    cleaned, report = clean_all(raw)
    report.skipped_datasets += missing_files

    out = resolve_folder(target)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in cleaned.items():
        df.drop(columns=[LINE]).to_csv(out / name, index=False, lineterminator="\n", encoding="utf-8")
    report.actions_table().to_csv(out / "cleaning_log.csv", index=False, lineterminator="\n")
    report.rejected_table().to_csv(out / "rejected_rows.csv", index=False, lineterminator="\n")
    return report
