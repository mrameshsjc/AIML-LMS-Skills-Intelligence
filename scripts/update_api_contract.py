"""
Save the current API contract to docs/api_contract.json (Phase 14).

Run this ONLY for an intended change to a request or response (a new field,
a new endpoint), then review the Git diff of docs/api_contract.json: it shows
exactly what API clients - the dashboard and the LMS - will notice.

HOW TO RUN (from the project folder)
    PS> python scripts/update_api_contract.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.contract import contract  # noqa: E402

target = ROOT / "docs" / "api_contract.json"
old = target.read_text(encoding="utf-8") if target.exists() else ""
new = json.dumps(contract(), indent=2, sort_keys=True) + "\n"
target.write_text(new, encoding="utf-8", newline="\n")
print(
    "docs/api_contract.json "
    + ("is unchanged." if new == old else "was updated - review the diff before committing.")
)
