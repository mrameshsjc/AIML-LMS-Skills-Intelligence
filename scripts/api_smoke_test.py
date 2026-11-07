"""
Smoke test for a RUNNING engine: call every API once over real HTTP (Phase 14).

WHAT IS A SMOKE TEST?
    A quick check that a deployed system basically works ("does it smoke when
    switched on?"). Unit and integration tests check the code; this checks a
    running server - on your PC, in Docker, in CI, or the public demo later.

WHAT IT CHECKS
    health, LLM and index status, APIs 1-5 and 7 (upload -> list -> delete a
    small test document), and the shared error format. With the sample data
    and E1001 it also checks the known answers (gap score 37.5, C-SQL-201 first, ...).
    It uses only Python's standard library, so it runs anywhere Python does.

HOW TO RUN
    PS> uvicorn app.main:app            (in one window)
    PS> python scripts/api_smoke_test.py
    PS> python scripts/api_smoke_test.py --base-url http://127.0.0.1:8000 --wait 60 --skip-upload

EXIT CODE
    0 = every check passed (WARN lines are information, e.g. "Ollama not running")
    1 = at least one check FAILED
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description="Smoke-test a running LMS Skills Intelligence Engine.")
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument(
    "--employee", default="E1001", help="employee to test with (sample-data answers need E1001)"
)
parser.add_argument("--wait", type=float, default=0, help="seconds to wait for the server to come up")
parser.add_argument(
    "--timeout", type=float, default=180, help="seconds per request (the first LLM call is slow)"
)
parser.add_argument("--skip-upload", action="store_true", help="do not upload/delete a test document (API 7)")
args = parser.parse_args()

BASE = args.base_url.rstrip("/")
LOCAL = urlparse(BASE).hostname in {"localhost", "127.0.0.1", "::1"}
# Local servers are called directly; a company proxy must not intercept (or block) them.
OPENER = (
    urllib.request.build_opener(urllib.request.ProxyHandler({})) if LOCAL else urllib.request.build_opener()
)
SAMPLE = args.employee == "E1001"  # the known answers below are for the sample data and E1001


@dataclass
class Reply:
    status: int
    body: dict
    ms: int


def call(
    method: str, path: str, body: dict | None = None, multipart: tuple[str, bytes] | None = None
) -> Reply:
    headers = {"X-Request-ID": f"smoke-{uuid.uuid4().hex[:8]}"}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    elif multipart is not None:
        boundary = uuid.uuid4().hex
        name, content = multipart
        data = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with OPENER.open(request, timeout=args.timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:  # 4xx/5xx still carry a JSON body
        status, raw = error.code, error.read()
    ms = int((time.perf_counter() - start) * 1000)
    try:
        return Reply(status, json.loads(raw or b"{}"), ms)
    except json.JSONDecodeError:
        return Reply(status, {"raw": raw[:200].decode(errors="replace")}, ms)


results: list[tuple[str, str, int, str]] = []  # (PASS/WARN/FAIL, name, ms, detail)


def check(name: str, reply: Reply, *conditions: tuple[bool, str], warn: bool = False) -> None:
    """Record PASS if the status is 200 and every (condition, explanation) holds."""
    problems = [] if reply.status == 200 else [f"HTTP {reply.status}: {json.dumps(reply.body)[:200]}"]
    if not problems:
        problems = [text for ok, text in conditions if not ok]
    verdict = "PASS" if not problems else ("WARN" if warn else "FAIL")
    results.append((verdict, name, reply.ms, "; ".join(problems) or "ok"))


def wait_for_server() -> bool:
    deadline = time.time() + args.wait
    while True:
        try:
            if call("GET", "/api/v1/health").status == 200:
                return True
        except OSError:
            pass
        if time.time() >= deadline:
            return False
        time.sleep(2)


def run() -> None:
    e = args.employee
    health = call("GET", "/api/v1/health")
    check("Health", health, (health.body.get("status") == "ok", "status is not ok"))

    llm = call("GET", "/api/v1/health/llm")
    check("LLM status", llm, (llm.body.get("provider") == "ollama", llm.body.get("detail", "")), warn=True)
    rag = call("GET", "/api/v1/health/rag")
    check(
        "Document index status", rag, (rag.body.get("ready") is True, rag.body.get("detail", "")), warn=True
    )

    r = call("POST", "/api/v1/skills/analyze", {"employee_id": e, "target_role_id": "R004"})
    check(
        "API 1 skills analysis",
        r,
        (isinstance(r.body.get("gap_score"), int | float), "no gap_score"),
        (
            not SAMPLE or r.body.get("gap_score") == 37.5,
            f"gap_score {r.body.get('gap_score')}, expected 37.5",
        ),
    )

    r = call("POST", "/api/v1/roles/match", {"employee_id": e})
    titles = [m["title"] for m in r.body.get("matches", [])]
    check(
        "API 2 role matching",
        r,
        (bool(titles), "no matches"),
        (not SAMPLE or "Data Engineer" in titles, f"Data Engineer not in {titles}"),
    )

    r = call("POST", "/api/v1/trainings/recommend", {"employee_id": e})
    courses = [c["course_id"] for c in r.body.get("recommendations", [])]
    check(
        "API 3 recommendations",
        r,
        (all("reason" in c for c in r.body.get("recommendations", [])), "a recommendation has no reason"),
        (not SAMPLE or courses[:1] == ["C-SQL-201"], f"first course {courses[:1]}, expected C-SQL-201"),
    )

    r = call("GET", f"/api/v1/learning-path/{e}")
    progress = r.body.get("progress", {})
    check(
        "API 4 learning path",
        r,
        (bool(r.body.get("next_action")), "no next_action"),
        (not SAMPLE or progress.get("projected_match_percentage") == 100.0, f"projected {progress}"),
    )

    r = call("POST", "/api/v1/ai/chat", {"question": "Which skills are required for an AI Engineer?"})
    check(
        "API 5 assistant (role question)",
        r,
        ("role_requirements" in r.body.get("intents", []), f"intents {r.body.get('intents')}"),
        (bool(r.body.get("answer")), "empty answer"),
    )
    r = call("POST", "/api/v1/ai/chat", {"question": "What are my current skill gaps?", "employee_id": e})
    check(
        f"API 5 assistant (personal, via {r.body.get('provider', '?')})",
        r,
        ("my_learning_path" in r.body.get("intents", []), f"intents {r.body.get('intents')}"),
    )
    warnings = r.body.get("grounding_warnings") or []
    check(
        "API 5 grounding check", r, (not warnings, f"the model went beyond the facts: {warnings}"), warn=True
    )

    if not args.skip_upload:
        name = f"smoke_test_{uuid.uuid4().hex[:8]}.csv"
        content = f"check,value\nsmoke test,{name}\n".encode()  # unique content: never a duplicate
        r = call("POST", "/api/v1/rag/ingest", multipart=(name, content))
        check("API 7 upload", r, (r.body.get("status") == "added", f"status {r.body.get('status')}"))
        if r.status == 200:
            listed = call("GET", "/api/v1/rag/documents")
            sources = {d["source"] for d in listed.body.get("documents", [])}
            check("API 7 list documents", listed, (name in sources, f"{name} not listed"))
            gone = call("DELETE", f"/api/v1/rag/documents/{name}")
            check(
                "API 7 delete",
                gone,
                (gone.body.get("status") == "deleted", f"status {gone.body.get('status')}"),
            )

    r = call("GET", "/api/v1/learning-path/E9999")
    error = r.body.get("error", {})
    results.append(
        (
            "PASS"
            if r.status == 404 and error.get("code") == "EMPLOYEE_NOT_FOUND" and error.get("request_id")
            else "FAIL",
            "Error format (unknown employee)",
            r.ms,
            "ok" if r.status == 404 else f"HTTP {r.status}: {json.dumps(r.body)[:200]}",
        )
    )


if __name__ == "__main__":
    print(f"Smoke test of {BASE} (employee {args.employee})\n")
    if not wait_for_server():
        sys.exit(f"FAIL  The server at {BASE} is not answering. Start it with: uvicorn app.main:app")
    run()
    width = max(len(name) for _, name, _, _ in results)
    for verdict, name, ms, detail in results:
        print(f"{verdict:4}  {name:<{width}}  {ms:>6} ms  {detail}")
    failed = sum(1 for verdict, *_ in results if verdict == "FAIL")
    warned = sum(1 for verdict, *_ in results if verdict == "WARN")
    print(f"\n{len(results) - failed - warned} passed, {warned} warnings, {failed} failed")
    sys.exit(1 if failed else 0)
