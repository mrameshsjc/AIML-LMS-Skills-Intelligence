"""
Contract tests: the API's requests and responses do not change by accident (Phase 14).

docs/api_contract.json is the agreed shape of every business endpoint
(see app/schemas/contract.py). If this test fails:
  - an UNINTENDED change: fix the code;
  - an INTENDED change: run  python scripts/update_api_contract.py  and commit the
    reviewed docs/api_contract.json together with the code.

HOW TO RUN
    PS> pytest tests/integration/test_contract.py -v
"""

import json
from pathlib import Path

import pytest

from app.schemas.contract import ENDPOINTS, contract

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "api_contract.json"


@pytest.fixture(scope="module")
def saved() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_every_endpoint_is_in_the_snapshot(saved):
    assert sorted(saved["endpoints"]) == sorted(contract()["endpoints"])


@pytest.mark.parametrize("key", [f"{method} {path}" for _, method, path, *_ in ENDPOINTS])
def test_endpoint_matches_the_snapshot(saved, key):
    current = contract()["endpoints"][key]
    assert current == saved["endpoints"][key], (
        f"The contract of {key} changed. If intended: python scripts/update_api_contract.py, "
        "then review the diff."
    )


def test_error_format_matches_the_snapshot(saved):
    assert contract()["error"] == saved["error"]


def test_documentation_changes_are_not_contract_changes():
    schema = contract()["endpoints"]["POST /api/v1/ai/chat"]["request"]
    text = json.dumps(schema)
    assert '"description"' not in text and '"examples"' not in text
    assert schema["required"] == ["question"]  # what clients DO depend on is kept
    assert schema["properties"]["employee_id"]["anyOf"][0]["pattern"] == r"^E\d{4}$"


def test_fields_named_title_or_description_are_kept():
    response = contract()["endpoints"]["POST /api/v1/ai/chat"]["response"]
    assert "title" in response["$defs"]["SourceOut"]["properties"]  # a field, not documentation
    course = contract()["endpoints"]["POST /api/v1/trainings/recommend"]["response"]
    assert "description" in course["$defs"]["RecommendationOut"]["properties"]
