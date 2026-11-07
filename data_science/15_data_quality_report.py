"""
15 - Data quality report: one summary of every check.

LESSON
    Scripts 03-06 each look at one kind of problem. This script runs them all
    and writes a report you can share: a status per file (PASS / WARN / FAIL)
    and the full list of issues. It is the "is this data fit to use?" answer
    in one page.

    Run it on raw data before cleaning and on cleaned data after, and compare.

HOW TO RUN (from the project folder)
    PS> python data_science/15_data_quality_report.py
    PS> python data_science/15_data_quality_report.py --data data/raw/dirty --out reports/quality_dirty

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   --out (default reports/quality):
           data_quality_report.md   readable report (opens nicely in PyCharm / GitHub)
           data_quality_issues.csv  every issue, for Excel or Pandas
         exit code 1 if any file FAILs
"""

import argparse
import sys

from _common import heading

from app.data_processing.loader import resolve_folder
from app.data_processing.quality_report import build_quality_report

parser = argparse.ArgumentParser(description="Lesson 15: data quality report.")
parser.add_argument("--data", default="data/sample", help="folder with the CSV files (default data/sample)")
parser.add_argument(
    "--out", default="reports/quality", help="folder for the report (default reports/quality)"
)
args = parser.parse_args()

report = build_quality_report(args.data)
out = resolve_folder(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / "data_quality_report.md").write_text(report.to_markdown(), encoding="utf-8")
report.issues.to_csv(out / "data_quality_issues.csv", index=False, lineterminator="\n")

heading(f"Data quality: {report.folder}")
print(report.summary.to_string(index=False))
print(f"\nOverall status: {report.status}")
print(f"Report written to {out / 'data_quality_report.md'}")
print(f"Issues written to {out / 'data_quality_issues.csv'} ({len(report.issues)} rows)")
sys.exit(1 if report.status == "FAIL" else 0)
