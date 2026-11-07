"""
Phase 1 verification: is the project set up and running correctly?

PURPOSE
    One command that checks everything Phase 1 promises and prints PASS/FAIL
    for each item, so you know exactly what works and what to fix.

WHY ONLY THE STANDARD LIBRARY
    This script must work even BEFORE you install anything, so it can tell you
    what is missing. It therefore uses only modules that ship with Python
    (subprocess, urllib, socket, ...), never FastAPI or pytest directly.

WHAT IT CHECKS
    1. Python version is 3.11 or newer.
    2. You are inside a virtual environment (.venv).
    3. All project folders and key files exist.
    4. .env exists (created from .env.example).
    5. Required libraries are installed.
    6. The API starts (uvicorn).
    7. GET /api/v1/health returns {"status": "ok"}.
    8. Swagger UI (/docs) loads.
    9. The automated tests pass (pytest).
   10. Ruff finds no lint problems.

HOW TO RUN (PowerShell, from the project folder, venv activated)
    PS> python scripts/verify_phase1.py

EXPECTED RESULT
    PASS  Python version                3.11.x
    PASS  Virtual environment           ...\\.venv
    ...
    PASS  Health endpoint               status=ok, version=0.1.0
    PASS  Swagger UI                    http://127.0.0.1:<port>/docs
    PASS  Tests (pytest)                6 passed in 0.5s
    PASS  Lint (ruff)                   All checks passed!
    ----------------------------------------------------------
    Phase 1 verified: 10/10 checks passed.

    The exit code is 0 when everything passes and 1 otherwise, so CI can use it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The project root is the folder that contains this script's parent folder.
ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = [
    # Application code
    "app/main.py",
    "app/core/config.py",
    "app/core/logging_config.py",
    "app/api/v1/health.py",
    "app/schemas",
    "app/services",
    "app/domain",
    "app/repositories",
    "app/database",
    "app/ml",
    "app/rag",
    "app/llm",
    "app/security",
    # Other project areas
    "dashboard",
    "data_science",
    "data/sample",
    "documents",
    "tests/api/test_health.py",
    "deployment",
    "docs",
    # Tooling
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    ".github/workflows/ci.yml",
    ".env.example",
    ".gitignore",
]

# Import name -> pip package name (they differ for some libraries).
REQUIRED_LIBRARIES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "pytest": "pytest",
    "httpx": "httpx",
}

results: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str = "") -> bool:
    """Store and print one check result."""
    results.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<30}{detail}")
    return ok


def check_python() -> None:
    v = sys.version_info
    record(v >= (3, 11), "Python version", f"{v.major}.{v.minor}.{v.micro} (need 3.11+)")


def check_venv() -> None:
    # Inside a venv, sys.prefix points at the venv and differs from base_prefix.
    in_venv = sys.prefix != sys.base_prefix
    detail = sys.prefix if in_venv else "not active -> run .\\.venv\\Scripts\\Activate.ps1"
    record(in_venv, "Virtual environment", detail)


def check_structure() -> None:
    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).exists()]
    detail = f"{len(REQUIRED_PATHS)} paths present" if not missing else "missing: " + ", ".join(missing)
    record(not missing, "Folder structure", detail)


def check_env_file() -> None:
    ok = (ROOT / ".env").exists()
    record(ok, ".env file", "found" if ok else "missing -> Copy-Item .env.example .env")


def check_libraries() -> bool:
    missing = [pip for mod, pip in REQUIRED_LIBRARIES.items() if importlib.util.find_spec(mod) is None]
    detail = "all installed" if not missing else "missing -> pip install -r requirements-dev.txt"
    return record(not missing, "Libraries", detail)


def _free_port() -> int:
    """Ask the operating system for an unused port, so we never clash with a running server."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, timeout: float = 3.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (local URL only)
        return resp.status, resp.read().decode("utf-8")


def check_running_server() -> None:
    """Start the real API with uvicorn, call it over HTTP, then stop it."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        # Wait up to 20 seconds for the server to answer.
        body = None
        for _ in range(40):
            if proc.poll() is not None:
                break  # server process exited (start-up error)
            try:
                status, body = _get(f"{base}/api/v1/health")
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.5)

        if body is None:
            output = proc.stdout.read() if proc.poll() is not None and proc.stdout else ""
            last_lines = " | ".join(output.strip().splitlines()[-3:]) or "no response within 20 s"
            record(False, "API starts", last_lines)
            record(False, "Health endpoint", "skipped (server did not start)")
            record(False, "Swagger UI", "skipped (server did not start)")
            return

        record(True, "API starts", f"uvicorn on {base}")
        data = json.loads(body)
        ok = status == 200 and data.get("status") == "ok"
        record(ok, "Health endpoint", f"status={data.get('status')}, version={data.get('version')}")

        docs_status, docs_body = _get(f"{base}/docs")
        record(docs_status == 200 and "swagger" in docs_body.lower(), "Swagger UI", f"{base}/docs")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_tests() -> None:
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    summary = (run.stdout.strip().splitlines() or ["no output"])[-1]
    record(run.returncode == 0, "Tests (pytest)", summary)


def check_ruff() -> None:
    ruff = shutil.which("ruff")
    if ruff is None:
        record(False, "Lint (ruff)", "ruff not found -> pip install -r requirements-dev.txt")
        return
    run = subprocess.run([ruff, "check", "."], cwd=ROOT, capture_output=True, text=True, timeout=120)
    summary = (run.stdout.strip().splitlines() or ["All checks passed!"])[-1]
    record(run.returncode == 0, "Lint (ruff)", summary)


def main() -> int:
    os.chdir(ROOT)
    print(f"Verifying Phase 1 in {ROOT}\n")

    check_python()
    check_venv()
    check_structure()
    check_env_file()
    if check_libraries():
        check_running_server()
        check_tests()
    else:
        for name in ("API starts", "Health endpoint", "Swagger UI", "Tests (pytest)"):
            record(False, name, "skipped (libraries missing)")
    check_ruff()

    passed = sum(ok for ok, _, _ in results)
    print("-" * 58)
    if passed == len(results):
        print(f"Phase 1 verified: {passed}/{len(results)} checks passed.")
        return 0
    print(f"{passed}/{len(results)} checks passed. Fix the FAIL lines above, then run this again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
