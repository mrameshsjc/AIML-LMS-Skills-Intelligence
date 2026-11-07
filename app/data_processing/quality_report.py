"""
Data quality report: one summary of every check, per file.

PURPOSE
    Run all validation checks on a folder and turn the results into:
      - a summary table per file: rows, errors, warnings, status;
      - the full issue list;
      - a Markdown report that reads well on GitHub or in PyCharm.

STATUS
    PASS   no errors and no warnings
    WARN   warnings only (usable, worth a look)
    FAIL   at least one error (fix or clean before use)

    "rows flagged" adds up the rows of every error, so a row with two problems
    counts twice. It shows how much needs attention, not an exact row count.

WHY MARKDOWN WITHOUT EXTRA LIBRARIES
    Pandas' own to_markdown() needs the optional "tabulate" package. A
    10-line helper avoids one more dependency for one table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.data_processing.loader import load_raw, resolve_folder
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import issues_table, run_checks


@dataclass
class QualityReport:
    folder: Path
    summary: pd.DataFrame
    issues: pd.DataFrame

    @property
    def status(self) -> str:
        statuses = set(self.summary["status"])
        return "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"

    def to_markdown(self) -> str:
        counts = self.summary["status"].value_counts()
        lines = [
            "# Data Quality Report",
            "",
            f"- Folder: `{self.folder}`",
            f"- Generated: {datetime.now():%Y-%m-%d %H:%M}",
            f"- Overall status: **{self.status}** "
            f"({counts.get('PASS', 0)} pass, {counts.get('WARN', 0)} warn, {counts.get('FAIL', 0)} fail)",
            "",
            "## Summary per file",
            "",
            markdown_table(self.summary),
            "",
            "## Issues",
            "",
            markdown_table(self.issues) if len(self.issues) else "No issues found.",
            "",
            "Line numbers are CSV lines (line 1 is the header). "
            "See docs/DATA_PIPELINE_GUIDE.md for what each check means.",
        ]
        return "\n".join(lines) + "\n"


def markdown_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table (pipes in values are escaped)."""

    def cell(value: object) -> str:
        return "" if pd.isna(value) else str(value).replace("|", "\\|")

    header = "| " + " | ".join(df.columns) + " |"
    divider = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, divider, *rows])


def build_quality_report(folder: str | Path | None = None) -> QualityReport:
    """Run every check on `folder` and summarise the results per file."""
    issues = issues_table(run_checks(folder))
    rows = []
    for name in SCHEMAS:
        try:
            row_count = len(load_raw(name, folder))
        except FileNotFoundError:
            row_count = 0
        mine = issues[issues["dataset"] == name]
        errors = int((mine["severity"] == "error").sum())
        warnings = int((mine["severity"] == "warning").sum())
        rows.append({
            "file": name,
            "rows": row_count,
            "errors": errors,
            "warnings": warnings,
            "rows flagged": int(mine.loc[mine["severity"] == "error", "rows"].sum()),
            "status": "FAIL" if errors else "WARN" if warnings else "PASS",
        })  # fmt: skip
    return QualityReport(resolve_folder(folder), pd.DataFrame(rows), issues)
