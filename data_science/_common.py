"""
Shared helpers for the numbered data_science scripts.

The scripts are meant to be read and run one by one, so each stays short and
focused on its lesson. Repeated plumbing lives here:
  - making `app` importable when a script is run directly;
  - the --data option (which folder to check);
  - printing headings and issue tables the same way everywhere.

WHY THE sys.path LINE
    When you run `python data_science/03_validate_schema.py`, Python looks for
    imports in the data_science folder, not the project folder, so `import app`
    would fail. Adding the project root to sys.path fixes that.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from app.data_processing.validators import Issue, issues_table  # noqa: E402

# Show wide tables in the terminal without wrapping or "..." in the middle.
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 60)


def parse_args(description: str, with_dataset: bool = False) -> argparse.Namespace:
    """Common command-line options.

    --data      folder with the 11 CSV files (default data/sample)
    --dataset   one file name, for scripts that look at a single file
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--data", default="data/sample", help="folder with the CSV files (default data/sample)"
    )
    if with_dataset:
        parser.add_argument(
            "--dataset", default="employees.csv", help="file to inspect (default employees.csv)"
        )
    return parser.parse_args()


def heading(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def explain(text: str) -> None:
    """Print a short explanation, indented so it stands apart from results."""
    for line in text.strip().splitlines():
        print(f"  | {line.strip()}")


def report(issues: list[Issue], what: str) -> int:
    """Print the issues table and return the exit code (1 if any error)."""
    heading(f"RESULT: {what}")
    if not issues:
        print("No problems found.")
        return 0
    table = issues_table(issues)
    print(table.to_string(index=False))
    errors = int((table["severity"] == "error").sum())
    warnings = len(table) - errors
    print(f"\n{errors} error(s), {warnings} warning(s).  'lines' = CSV line numbers (line 1 is the header).")
    return 1 if errors else 0
