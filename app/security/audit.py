"""
Audit log (Phase 17).

WHAT IT IS FOR
    Answering, after the fact: who did what, when, and was it allowed?
    "Which account retrained the model on Monday?", "Who looked at E1001's
    gaps?", "Were there many refused logins last night?"

WHAT IS WRITTEN (one JSON line per API request, to AUDIT_LOG_FILE)
    time, request_id, user, role, method, path, status, client IP, duration.
    Admin actions and refusals (401/403/429) are what reviewers usually look for.

WHAT IS NOT WRITTEN
    Request bodies: no questions, passwords, tokens, file contents or skill
    data. The log must not become a second copy of personal data.
    (The employee ID in a URL path is kept: it says WHOSE data was viewed.)

The file is append-only from the application's point of view; rotate or ship
it to a central log system in production.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.data_processing.loader import resolve_folder

_LOCK = threading.Lock()


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        file = Path(path)
        self.path = file if file.is_absolute() else resolve_folder(file.parent) / file.name

    def write(self, **entry) -> None:
        record = {"time": datetime.now(UTC).isoformat(timespec="milliseconds"), **entry}
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def read(self, limit: int = 100) -> list[dict]:
        """The latest entries, newest first."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in reversed(lines) if line.strip()]
