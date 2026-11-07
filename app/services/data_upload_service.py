"""
CSV upload service: check an uploaded file before it is accepted.

PURPOSE
    One reusable service for every place a user can upload LMS data: the
    Streamlit dashboard's upload page and, later, an API endpoint or the LMS
    itself. It answers three questions:

      1. Can we read it?        size limit, .csv extension, UTF-8 text, real CSV
      2. Which dataset is it?   from the file name, or else from its columns
      3. Is the data valid?     schema, empty values, ranges and rules,
                                duplicates, AND references to the other files

    It returns an UploadResult with a preview, the issues and a status, so a
    user interface only has to display it.

WHY A SERVICE (NOT CODE INSIDE THE UI)
    Streamlit, FastAPI and the LMS all need the same rules. Writing them once
    here means the dashboard and the API can never disagree about whether a
    file is valid. The service has no UI or web code, so it is easy to test.

REFERENCES
    An uploaded employee_skills.csv is checked against the CURRENT
    skills.csv and employees.csv (default: data/sample). Uploading a new
    skills.csv also re-checks the files that point to it: removing a skill
    that employees still hold is reported as a problem.

INPUT     the raw bytes of the file and its original file name
OUTPUT    UploadResult (or UploadError with a message a user can understand)
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import (
    Issue,
    validate_duplicates,
    validate_nulls,
    validate_references,
    validate_schema,
    validate_values,
)

MAX_UPLOAD_BYTES = (
    10 * 1024 * 1024
)  # 10 MB: far above any LMS export we expect, small enough to protect memory
PREVIEW_ROWS = 10
MIN_COLUMN_MATCH = 0.6  # at least 60 % of a dataset's columns must match to recognise it by its columns


class UploadError(Exception):
    """The file cannot be processed at all (wrong type, empty, unreadable...)."""


@dataclass
class UploadResult:
    dataset: str
    filename: str
    rows: int
    columns: list[str]
    preview: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)
    detected_by: str = "file name"  # or "columns"

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def status(self) -> str:
        """valid | valid_with_warnings | invalid"""
        if self.errors:
            return "invalid"
        return "valid_with_warnings" if self.warnings else "valid"


def read_csv_bytes(content: bytes, filename: str, max_bytes: int = MAX_UPLOAD_BYTES) -> pd.DataFrame:
    """Turn uploaded bytes into a raw (all-text) DataFrame, or raise UploadError."""
    if not filename.lower().endswith(".csv"):
        raise UploadError(f"'{filename}' is not a CSV file. Please upload a .csv file.")
    if len(content) == 0:
        raise UploadError("The file is empty.")
    if len(content) > max_bytes:
        raise UploadError(
            f"The file is {len(content) / 1_048_576:.1f} MB; the limit is {max_bytes / 1_048_576:.0f} MB."
        )
    try:
        # "utf-8-sig" also accepts the invisible marker (BOM) Excel adds when saving "CSV UTF-8".
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'.") from exc
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise UploadError(f"The file could not be read as CSV: {exc}") from exc
    if df.empty:
        raise UploadError("The file has a header but no data rows.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_dataset(filename: str, columns: list[str]) -> tuple[str, str]:
    """Work out which of the 11 datasets the file is. Returns (dataset, how)."""
    base = Path(filename).name.lower()
    if base in SCHEMAS:
        return base, "file name"
    scores = {
        name: len(set(columns) & set(schema.column_names)) / len(schema.column_names)
        for name, schema in SCHEMAS.items()
    }
    best = max(scores, key=lambda n: (scores[n], -len(SCHEMAS[n].column_names)))
    if scores[best] >= MIN_COLUMN_MATCH:
        return best, "columns"
    raise UploadError(
        "Could not tell which dataset this file is. Name it like one of: "
        + ", ".join(SCHEMAS)
        + ", or make sure its column headers match."
    )


def validate_upload(
    content: bytes,
    filename: str,
    dataset: str | None = None,
    reference_folder: str | Path | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> UploadResult:
    """Read, identify and validate an uploaded CSV file.

    `dataset` forces the dataset type (otherwise it is detected).
    `reference_folder` holds the current versions of the other files used for
    the reference checks (default data/sample).
    """
    df = read_csv_bytes(content, filename, max_bytes)
    if dataset is None:
        dataset, how = detect_dataset(filename, list(df.columns))
    elif dataset not in SCHEMAS:
        raise UploadError(f"Unknown dataset '{dataset}'.")
    else:
        how = "chosen by user"

    schema = SCHEMAS[dataset]
    issues = validate_schema(df, schema) + validate_nulls(df, schema)
    issues += validate_values(df, schema) + validate_duplicates(df, schema)

    # References: combine the upload with the current versions of the other files.
    others: dict[str, pd.DataFrame] = {}
    for name in SCHEMAS:
        if name == dataset:
            continue
        try:
            others[name] = load_raw(name, reference_folder)
        except FileNotFoundError:
            continue  # without the other file, its references cannot be checked
    issues += validate_references({dataset: df, **others}) if others else []
    # Keep reference issues that involve the uploaded file: its own links, or files linking to it.
    issues = [
        i
        for i in issues
        if i.dataset == dataset
        or any(fk.ref_dataset == dataset and fk.column == i.column for fk in SCHEMAS[i.dataset].foreign_keys)
    ]

    return UploadResult(
        dataset=dataset,
        filename=filename,
        rows=len(df),
        columns=list(df.columns),
        preview=df.head(PREVIEW_ROWS),
        issues=issues,
        detected_by=how,
    )


def save_upload(content: bytes, result: UploadResult, folder: str | Path = "data/uploads",
                allow_invalid: bool = False) -> Path:  # fmt: skip
    """Store an accepted upload as data/uploads/<timestamp>_<dataset>.

    Invalid files are refused unless allow_invalid=True (for example to keep a
    copy for later cleaning). The original file is never modified.
    """
    if result.status == "invalid" and not allow_invalid:
        raise UploadError(f"{result.filename} has {len(result.errors)} error(s) and was not saved.")
    target = resolve_folder(folder)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{datetime.now():%Y%m%d-%H%M%S}_{result.dataset}"
    path.write_bytes(content)
    return path
