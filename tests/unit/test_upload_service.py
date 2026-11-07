"""
Tests for the CSV upload service (app/services/data_upload_service.py).

HOW TO RUN
    PS> pytest tests/unit/test_upload_service.py -v
"""

from pathlib import Path

import pytest

from app.data_processing.loader import SAMPLE_DIR
from app.services.data_upload_service import (
    UploadError,
    detect_dataset,
    save_upload,
    validate_upload,
)


def sample_bytes(name: str) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()


def test_valid_file_is_accepted_with_preview():
    result = validate_upload(sample_bytes("employee_skills.csv"), "employee_skills.csv")
    assert result.status == "valid"
    assert result.dataset == "employee_skills.csv" and result.detected_by == "file name"
    assert result.rows == 925 and len(result.preview) == 10


def test_dataset_is_detected_from_columns_when_name_differs():
    result = validate_upload(sample_bytes("courses.csv"), "export_2026_10.csv")
    assert result.dataset == "courses.csv" and result.detected_by == "columns"


def test_excel_utf8_bom_is_accepted():
    result = validate_upload(b"\xef\xbb\xbf" + sample_bytes("skills.csv"), "skills.csv")
    assert result.status == "valid"
    assert result.columns[0] == "skill_id"  # BOM not glued to the first column name


@pytest.mark.parametrize(
    "content, filename, message",
    [
        (b"", "skills.csv", "empty"),
        (b"a,b\n1,2\n", "skills.xlsx", "not a CSV"),
        (b"\xff\xfe\x00\x00", "skills.csv", "UTF-8"),
        (b"skill_id,skill_name,category,description\n", "skills.csv", "no data rows"),
        (b"foo,bar\n1,2\n", "unknown.csv", "Could not tell"),
    ],
)
def test_unreadable_files_raise_clear_errors(content, filename, message):
    with pytest.raises(UploadError, match=message):
        validate_upload(content, filename)


def test_size_limit():
    with pytest.raises(UploadError, match="limit"):
        validate_upload(sample_bytes("skills.csv"), "skills.csv", max_bytes=100)


def test_problems_in_upload_are_reported():
    text = sample_bytes("employee_skills.csv").decode()
    broken = text.replace("E1001,SK001,3,", "E1001,SK001,9,", 1).replace("E1001,SK004,", "E1001,SK999,", 1)
    result = validate_upload(broken.encode(), "employee_skills.csv")
    assert result.status == "invalid"
    found = {(i.check, i.column) for i in result.errors}
    assert ("values", "current_level") in found
    assert ("references", "skill_id") in found


def test_removing_a_used_skill_is_reported_in_dependent_files():
    lines = sample_bytes("skills.csv").decode().splitlines()
    without_sql = "\n".join(line for line in lines if not line.startswith("SK004,")) + "\n"
    result = validate_upload(without_sql.encode(), "skills.csv")
    affected = {i.dataset for i in result.errors}
    assert {"employee_skills.csv", "course_skills.csv", "role_required_skills.csv"} <= affected


def test_detect_dataset_by_name_is_case_insensitive():
    assert detect_dataset("Skills.CSV", []) == ("skills.csv", "file name")


def test_save_upload_refuses_invalid_files(tmp_path):
    content = sample_bytes("skills.csv")
    valid = validate_upload(content, "skills.csv")
    path = save_upload(content, valid, tmp_path)
    assert path.read_bytes() == content and path.name.endswith("_skills.csv")

    invalid = validate_upload(content.replace(b"SK001", b"SK001X", 1), "skills.csv")
    assert invalid.status == "invalid"
    with pytest.raises(UploadError, match="not saved"):
        save_upload(content, invalid, tmp_path)
    assert isinstance(save_upload(content, invalid, Path(tmp_path), allow_invalid=True), Path)
