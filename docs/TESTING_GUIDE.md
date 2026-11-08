# Testing Guide

How the engine is tested, what each kind of test proves, and how to run them. All tests use **synthetic data**, temporary folders and fake servers, so they never touch your real index, database or models, and they never need Ollama.

## 1. The test pyramid

```
            ┌───────────────────────┐
            │  smoke test (running) │  scripts/api_smoke_test.py     a deployed server, real HTTP
            ├───────────────────────┤
            │  integration  (26)    │  tests/integration/            the APIs together, contracts
            │  dashboard  (24)      │  tests/dashboard/              each Streamlit page (AppTest)
            ├───────────────────────┤
            │  API  (106)           │  tests/api/                    each endpoint through FastAPI
            ├───────────────────────┤
            │  unit  (420)          │  tests/unit/                   functions and services alone
            │  security  (67)       │  tests/security/               login, access rules, limits, injection
            └───────────────────────┘
```

Many fast tests at the bottom, fewer and broader ones at the top. A failing unit test points to the exact function. A failing integration test means two parts disagree. A failing smoke test means the deployment is broken even though the code is fine.

| Layer | Folder | Proves | Example |
| --- | --- | --- | --- |
| Unit | `tests/unit/` | One function or service gives the right answer | The gap formula gives 37.5 for E1001; a PDF keeps its page numbers |
| API | `tests/api/` | Each endpoint validates input, returns the documented shape and errors | `POST /ai/chat` with `employee_id: "1001"` gives 422 |
| Integration | `tests/integration/` | The parts agree with each other; the contract is stable | API 4's step scores equal API 3's, for every employee |
| Security | `tests/security/` | Passwords, tokens, who-may-see-whom, rate limits, audit, prompt injection, upload checks | An employee's token cannot read E1002; a forged admin token is refused |
| Dashboard | `tests/dashboard/` | Each Streamlit page runs and shows the right numbers (AppTest, headless) | Skills page shows gap score 37.5 for E1001 |
| Smoke | `scripts/api_smoke_test.py` | A running server works end to end | Docker container: every API answers, upload → list → delete works |

## 2. Running the tests

```powershell
pytest                              # everything: about 643 tests
pytest -m "not slow"                # quick run while coding (skips the ~26 tests that start scripts or train models)
pytest tests/unit/test_chat.py -v   # one file, with each test's name
pytest -k "learning_path"           # tests whose name contains the text
pytest --lf                         # only the tests that failed last time
pytest --cov=app --cov-report=term-missing:skip-covered   # with a coverage report
```

In PyCharm: right-click `tests` (or one file) → *Run 'pytest in tests'*. The green and red icons next to each test function run that test alone.

**Slow tests** (`@pytest.mark.slow`) start a script in a separate process or train an ML model. They run in CI and in a full `pytest`; skip them with `-m "not slow"` for quick feedback.

## 3. What the integration tests guarantee (Phase 14)

`tests/integration/test_business_flow.py` follows the business flow from the requirements and checks every hand-over, **for all 100 employees**:

| Check | Why it matters |
| --- | --- |
| APIs 1 and 2 report the same gap score and match % for the same role | Two screens must never show different numbers |
| Every API 4 step from API 3's list has API 3's score and reason | The path explains the same recommendation |
| Completed courses never appear in APIs 3 or 4 | Basic trust in the recommendations |
| The assistant (API 5) repeats API 4's next action and gaps | The chat cannot contradict the path |
| CSV and SQLite give identical results through every service | Switching the data source changes nothing |
| An uploaded document reaches the assistant at once, and leaves when deleted | API 7 and API 5 work together |

`tests/integration/test_api_flow.py` runs one employee's whole journey over HTTP through the real FastAPI app: health → API 1 → 2 → 3 → 4 → 5 → upload → 5 again → delete.

## 4. Contract tests: protecting the API's clients

The dashboard (Phase 15) and, later, the PHP/F3 LMS depend on the exact request and response fields. `docs/api_contract.json` is the saved **contract**: for every business endpoint, the fields, types, required fields, allowed values, patterns and limits. Descriptions and examples are left out, so improving the documentation never counts as a change.

- `tests/integration/test_contract.py` compares the code with the snapshot.
- `tests/api/test_api_contract.py` checks that the published OpenAPI spec (what `/docs` shows) lists exactly the contract's endpoints and parameters, and that **every error from every endpoint** has the shared format `{"error": {"code", "message", "request_id"}}`.

**When a contract test fails:**
1. You did not mean to change the API: fix the code.
2. You did (a new field, a new endpoint): run `python scripts/update_api_contract.py`, review the Git diff of `docs/api_contract.json` (it shows exactly what clients will notice), and commit it with the code. A new optional response field is usually safe; removing or renaming a field, or making a request field required, breaks clients.

## 5. The smoke test

```powershell
uvicorn app.main:app                         # window 1
python scripts/api_smoke_test.py --admin-key <ADMIN_API_KEY>    # window 2
python scripts/api_smoke_test.py --base-url http://127.0.0.1:8000 --wait 60 --skip-upload
python scripts/api_smoke_test.py --username admin --password <password>   # a server with login on
```

It calls every API once and prints PASS / WARN / FAIL with timings:

```
PASS  API 1 skills analysis                          4 ms  ok
WARN  LLM status                                     2 ms  Using the fallback (no LLM) because: Cannot reach Ollama ...
PASS  API 7 upload                                 142 ms  ok
13 passed, 1 warnings, 0 failed
```

- **WARN** is information (no Ollama, no index yet, or a grounding warning from the model). Only **FAIL** gives exit code 1.
- With E1001 (the default) it also checks the known answers: gap score 37.5, C-SQL-201 first, projected match 100%.
- The upload check adds a uniquely named test document and deletes it again. Uploads are admin-only (Phase 17): without `--admin-key` (or an admin `--username`) it is skipped with a WARN. Use `--skip-upload` on a server where you do not want any change.
- Security checks (Phase 17): security headers present, `GET /auth/me`, and retraining **refused** without credentials. Logged in as an employee, the unknown-employee check expects `403 ACCESS_DENIED` instead of `404`.
- CI runs the same script against the Docker container after every push.

## 6. Test doubles: testing without the real thing

| Real component | Replaced in tests by | Where |
| --- | --- | --- |
| Ollama (chat and embeddings) | A **fake Ollama HTTP server** on a random local port, answering `/api/tags`, `/api/chat`, `/api/embed` | `tests/unit/conftest.py` |
| Ollama not running | A local port where nothing listens | `closed_port_url()` |
| The language model in services | `RecordingModel` / `FixedProvider`: fixed answers that record what they received | `test_chat.py`, `test_llm.py` |
| The completion model | Switched off (`USE_COMPLETION_MODEL=false`) or trained into a temp folder | `tests/api/conftest.py`, `test_completion_model.py` |
| Your index, uploads, database | Temporary folders (`tmp_path`) set through environment variables | many |
| Dependencies in the API | `app.dependency_overrides[...]` | `test_trainings_api.py`, `test_llm_api.py` |

The fake Ollama server tests the **real HTTP code**: requests, JSON, a missing model, timeouts, Ollama not running. Only the model's answer is fake.

## 7. Coverage

`pytest --cov=app` measures which lines of `app/` the tests run; CI prints the report on every push. The "Missing" column lists lines no test executes. Coverage shows what is **not** tested; a high number does not prove the tests check the right things. A minimum (for example `--cov-fail-under=85`) can be added to CI once the first report shows the current level.

## 8. Writing a new test

1. Put it in the right layer: a function or service → `unit`; an endpoint → `api`; several parts together → `integration`.
2. Name it after the behaviour: `test_completed_courses_never_come_back`, not `test_3`.
3. Arrange → act → assert: build the input, call one thing, check the result.
4. Use `tmp_path` for files and the fake Ollama server for model calls; never depend on your own `.env`, index or Ollama.
5. Mark it `@pytest.mark.slow` if it starts a subprocess or trains a model.
