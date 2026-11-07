"""
Make a "dirty" copy of the LMS data with known, planted problems (Phase 3).

PURPOSE
    Real data is never perfect. To learn validation, and to PROVE our checks
    work, we copy the clean files from data/sample and deliberately break them
    in 17 documented ways (the DEFECTS list below). The validation scripts must
    find every one; tests/unit/test_data_validation.py checks that they do.

WHY PLANTED DEFECTS
    If you only ever test on clean data, a checker that finds nothing looks the
    same as a checker that works. Planting known problems is a simple way to
    test the tester.

OUTPUT
    data/raw/dirty/*.csv              the 11 files, some with problems
    data/raw/dirty/PLANTED_DEFECTS.md the list of problems (the "answer key")
    data/raw is git-ignored: regenerate this copy any time.

HOW TO RUN (PowerShell, from the project folder)
    PS> python scripts/make_dirty_data.py
    PS> python data_science/03_validate_schema.py --data data/raw/dirty
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DEFAULT_OUT = ROOT / "data" / "raw" / "dirty"

# The answer key. Each defect says which file, which check should catch it and
# in which column. The tests use exactly this list.
DEFECTS = [
    ("D01", "courses.csv", "schema", "legacy_code", "Unexpected extra column `legacy_code` added."),
    ("D02", "job_roles.csv", "schema", "seniority", "Column `seniority` renamed to `seniority_level`."),
    ("D03", "courses.csv", "schema", "duration_hours", "duration_hours written as the word 'ten'."),
    ("D04", "employees.csv", "schema", "hire_date", "hire_date in DD/MM/YYYY format instead of YYYY-MM-DD."),
    ("D05", "employees.csv", "nulls", "email", "email emptied in 3 rows."),
    ("D06", "employee_skills.csv", "nulls", "current_level", "current_level emptied in 4 rows."),
    ("D07", "courses.csv", "nulls", "course_title", "course_title emptied in 2 rows."),
    (
        "D08",
        "employee_skills.csv",
        "values",
        "current_level",
        "current_level set to 7 (3 rows) and 0 (1 row).",
    ),
    ("D09", "training_history.csv", "values", "score", "score of 120 on a completed course."),
    ("D10", "training_history.csv", "values", "status", "status misspelled as 'Complete' in 2 rows."),
    (
        "D11",
        "course_skills.csv",
        "rules",
        "level_from, level_to",
        "level_from and level_to swapped in 1 row.",
    ),
    (
        "D12",
        "training_history.csv",
        "rules",
        "enrolled_date, completed_date",
        "completed_date set before enrolled_date in 1 row.",
    ),
    ("D13", "employees.csv", "duplicates", "*", "2 employee rows copied exactly."),
    (
        "D14",
        "employee_skills.csv",
        "duplicates",
        "employee_id, skill_id",
        "Same employee and skill entered twice with different levels (2 rows).",
    ),
    ("D15", "training_history.csv", "duplicates", "enrollment_id", "One enrollment_id reused for a new row."),
    ("D16", "employee_skills.csv", "references", "skill_id", "skill_id SK999 does not exist (2 rows)."),
    ("D17", "training_history.csv", "references", "course_id", "course_id C-XYZ-101 does not exist (1 row)."),
]


def _read(name: str) -> pd.DataFrame:
    # Read everything as text so the files are copied exactly.
    return pd.read_csv(SAMPLE / name, dtype=str, keep_default_na=False)


def make_dirty(out_dir: Path) -> None:
    """Copy data/sample to out_dir and plant every defect in DEFECTS."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    frames = {p.name: _read(p.name) for p in sorted(SAMPLE.glob("*.csv"))}

    # --- courses.csv: D01, D03, D07 -----------------------------------------
    courses = frames["courses.csv"]
    courses["legacy_code"] = "OLD-" + courses.index.astype(str)  # D01
    courses.loc[4, "duration_hours"] = "ten"  # D03
    courses.loc[[10, 11], "course_title"] = ""  # D07

    # --- job_roles.csv: D02 ---------------------------------------------------
    frames["job_roles.csv"] = frames["job_roles.csv"].rename(columns={"seniority": "seniority_level"})

    # --- employees.csv: D04, D05, D13 ----------------------------------------
    emp = frames["employees.csv"]
    y, m, d = emp.loc[7, "hire_date"].split("-")
    emp.loc[7, "hire_date"] = f"{d}/{m}/{y}"  # D04
    emp.loc[[20, 21, 22], "email"] = ""  # D05
    frames["employees.csv"] = pd.concat([emp, emp.loc[[30, 31]]], ignore_index=True)  # D13

    # --- employee_skills.csv: D06, D08, D14, D16 ------------------------------
    es = frames["employee_skills.csv"]
    es.loc[[40, 41, 42, 43], "current_level"] = ""  # D06
    es.loc[[50, 51, 52], "current_level"] = "7"  # D08
    es.loc[53, "current_level"] = "0"  # D08
    es.loc[[60, 300], "skill_id"] = "SK999"  # D16 (rows of two different employees)
    repeat = es.loc[[70, 71]].copy()
    repeat["current_level"] = repeat["current_level"].map(lambda v: "1" if v != "1" else "2")
    frames["employee_skills.csv"] = pd.concat([es, repeat], ignore_index=True)  # D14

    # --- course_skills.csv: D11 -----------------------------------------------
    cs = frames["course_skills.csv"]
    i = cs.index[cs["course_id"] == "C-JAVA-201"][0]  # 2 -> 4 becomes 4 -> 2: valid levels, wrong order
    cs.loc[i, ["level_from", "level_to"]] = [cs.loc[i, "level_to"], cs.loc[i, "level_from"]]  # D11

    # --- training_history.csv: D09, D10, D12, D15, D17 ------------------------
    th = frames["training_history.csv"]
    completed = th.index[th["status"] == "Completed"]
    th.loc[completed[5], "score"] = "120"  # D09
    th.loc[completed[[10, 11]], "status"] = "Complete"  # D10
    row = completed[15]
    enrolled = pd.Timestamp(th.loc[row, "enrolled_date"])
    th.loc[row, "completed_date"] = (enrolled - pd.Timedelta(days=10)).strftime("%Y-%m-%d")  # D12
    th.loc[th.index[20], "course_id"] = "C-XYZ-101"  # D17
    reused = th.loc[[th.index[30]]].copy()
    reused["course_id"] = th.loc[th.index[31], "course_id"]
    frames["training_history.csv"] = pd.concat([th, reused], ignore_index=True)  # D15

    for name, df in frames.items():
        df.to_csv(out_dir / name, index=False, lineterminator="\n", encoding="utf-8")

    lines = [
        "# Planted defects (answer key)",
        "",
        "| ID | File | Check that should find it | Column | Defect |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [f"| {i} | `{f}` | {c} | `{col}` | {desc} |" for i, f, c, col, desc in DEFECTS]
    (out_dir / "PLANTED_DEFECTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a dirty copy of the LMS data.")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output folder (default data/raw/dirty)"
    )
    out = parser.parse_args().out
    out = out if out.is_absolute() else ROOT / out
    if not (SAMPLE / "employees.csv").exists():
        sys.exit("data/sample is empty. Run: python scripts/generate_synthetic_data.py")
    make_dirty(out)
    print(f"Dirty data written to {out}")
    print(f"{len(DEFECTS)} defects planted; answer key: {out / 'PLANTED_DEFECTS.md'}")


if __name__ == "__main__":
    main()
