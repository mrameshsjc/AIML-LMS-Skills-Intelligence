"""
Settings every test starts from (Phase 17), applied BEFORE the app is imported.

    AUTH_ENABLED=false     a developer's .env may switch login on; the existing tests
                           expect the open local mode. Login tests switch it on themselves.
    ADMIN_API_KEY          a known key, so tests can call the admin endpoints (API 6 and 7).
    AUDIT_LOG_FILE         a temporary file: tests must not fill the project's logs/ folder.
    USERS_FILE             a temporary file: tests must not see (or change) real accounts.

The rate limiter counts in memory across requests, so it is emptied before each test.
"""

import os
import tempfile
from pathlib import Path

import pytest

TEST_ADMIN_KEY = "test-admin-key"
_TEMP = Path(tempfile.mkdtemp(prefix="lms-tests-"))

os.environ["AUTH_ENABLED"] = "false"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY
os.environ["AUDIT_LOG_FILE"] = str(_TEMP / "audit.jsonl")
os.environ["USERS_FILE"] = str(_TEMP / "users.json")
os.environ["APP_PROFILE"] = "local"  # a public-demo .env would refuse to start without login


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    from app.security.rate_limit import LIMITER

    LIMITER.reset()
    yield
