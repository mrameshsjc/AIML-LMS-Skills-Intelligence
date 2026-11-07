"""
Tests for cleaning, the quality report and scripts 07, 08 and 15 (Phase 4).

THE MAIN PROMISES
    1. Cleaning the dirty data produces files that pass every validation check.
    2. Cleaning already-clean data changes nothing (byte for byte).
    3. Every quarantined row keeps its original line and a reason.

HOW TO RUN
    PS> pytest tests/unit/test_data_cleaning.py -v
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.data_processing.cleaning import LINE, CleaningReport, clean_all, clean_dataset, clean_folder
from app.data_processing.loader import SAMPLE_DIR, load_raw
from app.data_processing.quality_report import build_quality_report, markdown_table
from app.data_processing.schemas import SCHEMAS
from app.data_processing.validators import run_checks

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def dirty_folder(tmp_path_factory) -> Path:
    spec = importlib.util.spec_from_file_location("make_dirty_data", ROOT / "scripts" / "make_dirty_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path_factory.mktemp("dirty")
    module.make_dirty(folder)
    return folder


@pytest.fixture(scope="module")
def cleaned(dirty_folder, tmp_path_factory):
    target = tmp_path_factory.mktemp("processed")
    report = clean_folder(dirty_folder, target)
    return target, report


# --- Main promises ---------------------------------------------------------


def test_cleaned_dirty_data_passes_validation(cleaned):
    target, _ = cleaned
    issues = run_checks(target)
    assert issues == [], [i.as_dict() for i in issues]


def test_cleaning_clean_data_changes_nothing(tmp_path):
    report = clean_folder(SAMPLE_DIR, tmp_path)
    assert report.actions == [] and report.rejected == []
    for name in SCHEMAS:
        assert (tmp_path / name).read_bytes() == (SAMPLE_DIR / name).read_bytes(), name


def test_quarantined_rows_keep_line_and_reason(cleaned):
    target, report = cleaned
    rejected = pd.read_csv(target / "rejected_rows.csv")
    assert len(rejected) == len(report.rejected) > 0
    assert rejected["line"].min() >= 2  # line 1 is the header
    assert rejected["reason"].notna().all() and rejected["record"].notna().all()
    assert (target / "cleaning_log.csv").exists()


# --- Each fix does what it says --------------------------------------------


def test_expected_fixes_are_logged(cleaned):
    _, report = cleaned
    actions = {(a["dataset"], a["step"]) for a in report.actions}
    assert ("job_roles.csv", "columns") in actions  # seniority_level -> seniority
    assert ("courses.csv", "columns") in actions  # legacy_code dropped
    assert ("employees.csv", "dates") in actions  # DD/MM/YYYY rewritten
    assert ("training_history.csv", "categories") in actions  # Complete -> Completed
    assert ("training_history.csv", "numbers") in actions  # score 120 capped
    assert ("course_skills.csv", "rules") in actions  # swapped levels fixed
    assert ("employees.csv", "duplicates") in actions  # exact copies dropped


def test_fixed_values_are_correct(cleaned):
    target, _ = cleaned
    history = load_raw("training_history.csv", target)
    assert "Complete" not in set(history["status"])
    assert pd.to_numeric(history["score"]).max() == 100
    java = load_raw("course_skills.csv", target).set_index("course_id").loc["C-JAVA-201"]
    assert (java["level_from"], java["level_to"]) == ("2", "4")
    titles = load_raw("courses.csv", target)["course_title"]
    assert titles.str.startswith("Untitled course (").sum() == 2


def test_cascade_removes_rows_of_quarantined_employees(cleaned):
    target, report = cleaned
    quarantined = {
        r["record"].split(";")[0].split("=")[1] for r in report.rejected if r["dataset"] == "employees.csv"
    }
    assert len(quarantined) == 3
    for name in ("employee_skills.csv", "career_goals.csv", "training_history.csv"):
        assert not set(load_raw(name, target)["employee_id"]) & quarantined, name


def test_unknown_references_are_quarantined(cleaned):
    target, _ = cleaned
    assert "SK999" not in set(load_raw("employee_skills.csv", target)["skill_id"])
    assert "C-XYZ-101" not in set(load_raw("training_history.csv", target)["course_id"])


# --- Small hand-made examples ----------------------------------------------


def _clean_one(name: str, df: pd.DataFrame) -> tuple[pd.DataFrame | None, CleaningReport]:
    report = CleaningReport()
    return clean_dataset(df, SCHEMAS[name], report), report


def test_text_is_trimmed_and_case_fixed():
    df = pd.DataFrame({"level": ["1"], "label": ["  Beginner "], "description": ["x"]})
    out, report = _clean_one("skill_proficiency.csv", df)
    assert out.loc[0, "label"] == "Beginner"
    assert report.actions[0]["step"] == "text"


def test_missing_required_column_skips_file():
    df = pd.DataFrame({"level": ["1"], "label": ["a"]})  # no description column
    out, report = _clean_one("skill_proficiency.csv", df)
    assert out is None and report.skipped_datasets == ["skill_proficiency.csv"]


def test_conflicting_duplicates_keep_newest_assessment():
    df = pd.DataFrame({
        "employee_id": ["E1001", "E1001"],
        "skill_id": ["SK001", "SK001"],
        "current_level": ["2", "3"],
        "source": ["self", "assessment"],
        "assessed_date": ["2025-01-01", "2026-01-01"],
    })  # fmt: skip
    out, report = _clean_one("employee_skills.csv", df)
    assert out["current_level"].tolist() == ["3"]  # the newer assessment wins
    assert report.rejected[0]["line"] == 2


def test_optional_broken_reference_is_cleared_not_removed():
    employees = load_raw("employees.csv").head(3).copy()
    employees.loc[1, "manager_id"] = "E9999"
    cleaned_data, report = clean_all({"employees.csv": employees})
    assert len(cleaned_data["employees.csv"]) == 3
    assert pd.isna(cleaned_data["employees.csv"].loc[1, "manager_id"])
    assert report.actions[-1]["step"] == "references"
    assert LINE in cleaned_data["employees.csv"].columns


# --- Quality report ---------------------------------------------------------


def test_quality_report_pass_and_fail(dirty_folder):
    assert build_quality_report(SAMPLE_DIR).status == "PASS"
    dirty = build_quality_report(dirty_folder)
    assert dirty.status == "FAIL"
    assert "**FAIL**" in dirty.to_markdown()
    assert set(dirty.summary["status"]) <= {"PASS", "WARN", "FAIL"}


def test_markdown_table_escapes_pipes():
    table = markdown_table(pd.DataFrame({"a": ["x|y"], "b": [None]}))
    assert table.splitlines()[2] == "| x\\|y |  |"


# --- Scripts run end to end -------------------------------------------------


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "data_science" / script), *args], cwd=ROOT, capture_output=True, text=True
    )


def test_script_07_cleans_dirty_data(dirty_folder, tmp_path):
    result = _run("07_clean_data.py", "--data", str(dirty_folder), "--out", str(tmp_path))
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "No problems found." in result.stdout


def test_script_08_saves_seven_charts(tmp_path):
    result = _run("08_eda.py", "--out", str(tmp_path))
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert len(list(tmp_path.glob("*.png"))) == 7


def test_script_15_reports_status(dirty_folder, tmp_path):
    clean = _run("15_data_quality_report.py", "--out", str(tmp_path / "clean"))
    assert clean.returncode == 0 and "Overall status: PASS" in clean.stdout
    dirty = _run("15_data_quality_report.py", "--data", str(dirty_folder), "--out", str(tmp_path / "dirty"))
    assert dirty.returncode == 1 and "Overall status: FAIL" in dirty.stdout
    assert (tmp_path / "dirty" / "data_quality_report.md").exists()
