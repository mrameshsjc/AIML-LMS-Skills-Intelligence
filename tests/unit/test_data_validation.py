"""
Tests for the data processing layer (Phase 3): loader, schemas and validators.

THE TWO MAIN PROMISES
    1. Clean data (data/sample) produces NO issues - no false alarms.
    2. Dirty data (17 planted defects) has EVERY defect found - no misses.

Plus small, focused tests that build tiny DataFrames by hand, so each rule
can be understood (and debugged) on its own.

HOW TO RUN
    PS> pytest tests/unit/test_data_validation.py -v
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.data_processing.loader import load_all, load_dataset, to_typed
from app.data_processing.schemas import DATASET_NAMES, SCHEMAS
from app.data_processing.validators import (
    invalid_type_mask,
    run_checks,
    validate_duplicates,
    validate_nulls,
    validate_references,
    validate_schema,
    validate_values,
)

ROOT = Path(__file__).resolve().parents[2]


def _load_dirty_module():
    spec = importlib.util.spec_from_file_location("make_dirty_data", ROOT / "scripts" / "make_dirty_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dirty_folder(tmp_path_factory) -> Path:
    """Create the dirty dataset once in a temporary folder."""
    folder = tmp_path_factory.mktemp("dirty")
    _load_dirty_module().make_dirty(folder)
    return folder


# --- The two main promises -------------------------------------------------


def test_clean_sample_data_has_no_issues():
    issues = run_checks()
    assert issues == [], [i.as_dict() for i in issues]


def test_every_planted_defect_is_found(dirty_folder):
    found = {(i.dataset, i.check, i.column) for i in run_checks(dirty_folder)}
    missed = [d for d in _load_dirty_module().DEFECTS if (d[1], d[2], d[3]) not in found]
    assert not missed, f"defects not detected: {missed}"


def test_dirty_data_reports_correct_line_numbers(dirty_folder):
    """The planted empty emails are in DataFrame rows 20-22, i.e. CSV lines 22-24."""
    issue = next(i for i in run_checks(dirty_folder) if i.dataset == "employees.csv" and i.check == "nulls")
    assert issue.lines == [22, 23, 24]
    assert issue.rows == 3


def test_missing_file_is_reported_not_crashed(tmp_path):
    issues = run_checks(tmp_path)  # empty folder
    assert {i.dataset for i in issues} == set(DATASET_NAMES)
    assert all(i.severity == "error" for i in issues)


# --- Loader ----------------------------------------------------------------


def test_load_all_returns_11_typed_datasets():
    data = load_all()
    assert set(data) == set(DATASET_NAMES)
    history = data["training_history.csv"]
    assert str(history["score"].dtype) == "Int64"
    assert pd.api.types.is_datetime64_any_dtype(history["enrolled_date"])
    assert str(data["courses.csv"]["is_active"].dtype) == "boolean"


def test_raw_loading_keeps_text_and_empty_cells():
    raw = load_dataset("employees.csv", typed=False)
    assert raw["manager_id"].isna().sum() == 10  # top managers have no manager
    assert raw.loc[0, "hire_date"] == "2021-06-14"  # still text


def test_unknown_dataset_name_is_rejected():
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_dataset("salaries.csv")


def test_to_typed_turns_bad_values_into_missing():
    schema = SCHEMAS["skill_proficiency.csv"]
    raw = pd.DataFrame({"level": ["1", "ten"], "label": ["a", "b"], "description": ["x", "y"]})
    typed = to_typed(raw, schema)
    assert typed["level"].tolist()[0] == 1
    assert pd.isna(typed["level"].tolist()[1])


# --- Small hand-made examples for each check -------------------------------


@pytest.mark.parametrize(
    "values, dtype, expected",
    [
        (["1", "2.5", "x", None], "int", [False, True, True, False]),
        (["1.5", "abc"], "float", [False, True]),
        (["2026-01-31", "31/01/2026", "2026-02-30"], "date", [False, True, True]),
        (["True", "False", "yes"], "bool", [False, False, True]),
    ],
)
def test_invalid_type_mask(values, dtype, expected):
    assert invalid_type_mask(pd.Series(values, dtype="object"), dtype).tolist() == expected


def test_schema_detects_missing_extra_and_reordered_columns():
    schema = SCHEMAS["skill_proficiency.csv"]
    missing = validate_schema(pd.DataFrame({"level": ["1"], "label": ["a"], "notes": ["x"]}), schema)
    assert {(i.column, i.severity) for i in missing} == {("description", "error"), ("notes", "warning")}

    reordered = validate_schema(pd.DataFrame({"label": ["a"], "level": ["1"], "description": ["x"]}), schema)
    assert [i.message for i in reordered] == ["Columns are in a different order."]


def test_nulls_only_flag_required_columns():
    schema = SCHEMAS["employees.csv"]
    df = pd.DataFrame({c: ["x"] for c in schema.column_names})
    df.loc[0, "manager_id"] = None  # optional: fine
    assert validate_nulls(df, schema) == []
    df.loc[0, "email"] = None  # required: error
    assert [i.column for i in validate_nulls(df, schema)] == ["email"]


def test_values_check_ranges_allowed_values_and_formats():
    schema = SCHEMAS["employee_skills.csv"]
    df = pd.DataFrame({
        "employee_id": ["E1001", "E1002", "E1003"],
        "skill_id": ["SK001", "SK001", "SK001"],
        "current_level": ["3", "6", "0"],
        "source": ["self", "boss", "manager"],
        "assessed_date": ["2026-01-01", "2026-01-01", "2030-01-01"],
    })  # fmt: skip
    messages = {(i.column, i.message) for i in validate_values(df, schema)}
    assert ("current_level", "Value is above the maximum of 5.") in messages
    assert ("current_level", "Value is below the minimum of 1.") in messages
    assert any(col == "source" for col, _ in messages)
    assert any(col == "assessed_date" and "after" in msg for col, msg in messages)


def test_training_business_rules():
    schema = SCHEMAS["training_history.csv"]
    df = pd.DataFrame({
        "enrollment_id": ["EN0001", "EN0002", "EN0003"],
        "employee_id": ["E1001"] * 3,
        "course_id": ["C-PY-101"] * 3,
        "status": ["Completed", "Dropped", "Completed"],
        "enrolled_date": ["2025-01-10", "2025-01-10", "2025-01-10"],
        "completed_date": [None, "2025-02-01", "2025-01-01"],
        "score": [None, "70", "80"],
        "attempts": ["1", "1", "1"],
    })  # fmt: skip
    rules = [i.message for i in validate_values(df, schema) if i.check == "rules"]
    assert len(rules) == 3  # missing date/score, dropped with a score, completed before enrolled


def test_references_find_unknown_ids():
    data = {
        "skills.csv": pd.DataFrame({"skill_id": ["SK001"]}),
        "employee_skills.csv": pd.DataFrame(
            {"employee_id": ["E1001", "E1001"], "skill_id": ["SK001", "SK999"]}
        ),
    }
    issues = validate_references(data)
    assert len(issues) == 1 and issues[0].column == "skill_id" and "SK999" in issues[0].message


def test_duplicates_ignore_empty_unique_values():
    schema = SCHEMAS["employees.csv"]
    df = pd.DataFrame({c: [f"{c}1", f"{c}2", f"{c}3"] for c in schema.column_names})
    df["email"] = [None, None, "a@example.com"]  # two empty emails are not duplicates of each other
    assert validate_duplicates(df, schema) == []
    df.loc[2, "employee_id"] = df.loc[1, "employee_id"]
    assert [i.column for i in validate_duplicates(df, schema)] == ["employee_id"]


# --- The learning scripts run end to end -----------------------------------

SCRIPTS = [
    "01_read_csv.py",
    "02_inspect_data.py",
    "03_validate_schema.py",
    "04_validate_nulls.py",
    "05_validate_values.py",
    "06_validate_duplicates.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_passes_on_clean_data(script):
    result = subprocess.run(
        [sys.executable, str(ROOT / "data_science" / script)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]


@pytest.mark.parametrize("script", SCRIPTS[2:])
def test_validation_script_fails_on_dirty_data(script, dirty_folder):
    result = subprocess.run(
        [sys.executable, str(ROOT / "data_science" / script), "--data", str(dirty_folder)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout[-2000:] + result.stderr[-2000:]
    assert "error(s)" in result.stdout
