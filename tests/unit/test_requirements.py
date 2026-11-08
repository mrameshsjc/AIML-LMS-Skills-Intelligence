"""
The slim requirement files for the free hosts (Phase 19) must stay in step with
requirements.txt: same packages, same version ranges - only fewer of them.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def pins(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-r"):
            continue
        name = line.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower()
        result[name] = line
    return result


FULL = pins(ROOT / "requirements.txt")


@pytest.mark.parametrize("file", ["requirements-api.txt", "dashboard/requirements.txt"])
def test_slim_file_is_a_subset_with_the_same_versions(file):
    slim = pins(ROOT / file)
    assert slim, file
    for name, line in slim.items():
        assert FULL.get(name) == line, f"{file}: '{line}' differs from requirements.txt"


def test_api_file_has_what_the_api_imports():
    assert {"fastapi", "uvicorn", "pandas", "scikit-learn", "pyjwt", "python-multipart"} <= set(
        pins(ROOT / "requirements-api.txt")
    )
    assert "streamlit" not in pins(ROOT / "requirements-api.txt")


def test_dashboard_file_has_streamlit_and_the_shared_services():
    slim = pins(ROOT / "dashboard/requirements.txt")
    assert {"streamlit", "fastapi", "pandas", "scikit-learn", "pyjwt"} <= set(slim)
    assert "uvicorn" not in slim
