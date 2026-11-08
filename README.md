# LMS Skills Intelligence Engine

Standalone AI/ML application for an enterprise LMS: **skills-gap analysis, job-role matching, explainable training recommendations, personalised learning paths and an LLM + RAG learning assistant.**

| | |
| --- | --- |
| Project folder / Git repo | `AIML-LMS-Skills-Intelligence` |
| Current phase | **Phase 20 – Kubernetes with Minikube: Deployments, Services, ConfigMap, Secret, PV/PVC, probes, limits, autoscaling** (Phases 1–19 on GitHub, CI green) |
| **Live demo** | Dashboard: **https://lms-skills-intelligence.streamlit.app** · API: **https://lms-skills-api.onrender.com/api/v1** · Swagger: **https://lms-skills-api.onrender.com/docs** (synthetic data, no account needed; the API wakes in about a minute after a quiet period) |
| Python | 3.11 |
| LMS integration | Not in this project. The architecture is API-ready for it (later phase). |

> All data in this project is **synthetic**. No real employee data is used.

---

## 1. What is built so far (Phases 1–20)

| Item | File(s) | Why it exists |
| --- | --- | --- |
| FastAPI app with Swagger UI | `app/main.py` | Entry point; every API is plugged in here |
| Health endpoint | `app/api/v1/health.py` | Proves the service is up; used by Docker and CI |
| Settings from `.env` | `app/core/config.py` | No hard-coded config or secrets |
| Logging with request IDs | `app/core/logging_config.py` | Trace each request through the logs |
| Standard error format | `app/main.py` | One error shape for every endpoint |
| Tests | `tests/api/test_health.py` | 6 automated API checks |
| Setup checker | `scripts/verify_phase1.py` | One command: PASS/FAIL for setup, server, health, Swagger, tests, lint |
| Full folder structure | every folder + its `README.md` | Shows where each later phase's code goes |
| Docker | `Dockerfile`, `compose.yaml`, `.dockerignore` | Run anywhere with one command (hardened in Phase 18) |
| CI/CD | `.github/workflows/ci.yml` | Lint, test and build on every push |
| Code quality | `pyproject.toml`, `.pre-commit-config.yaml` | Ruff lint + format, automatic before commits |
| **Phase 2:** data generator | `scripts/generate_synthetic_data.py` | Creates 11 consistent CSV files from a fixed seed |
| **Phase 2:** synthetic data | `data/sample/*.csv` | 100 employees, 42 skills, 13 roles, 80 courses, 554 enrolments |
| **Phase 2:** data tests | `tests/unit/test_synthetic_data.py` | 48 checks: columns, keys, references, rules, loops, the worked example |
| **Phase 2:** data dictionary | `docs/DATA_DICTIONARY.md` | Every file and column explained, with a relationship diagram |
| **Phase 3:** data rules | `app/data_processing/schemas.py` | Columns, types, ranges, allowed values, keys and references for all 11 files |
| **Phase 3:** loading + checks | `app/data_processing/loader.py`, `validators.py` | Raw and typed loading; schema, null, value, rule, reference and duplicate checks |
| **Phase 3:** learning scripts | `data_science/01_read_csv.py` … `06_validate_duplicates.py` | Pandas step by step, with explanations printed as they run |
| **Phase 3:** practice data | `scripts/make_dirty_data.py` | A copy with 17 planted problems; the checks must find them all |
| **Phase 3:** tests + guide | `tests/unit/test_data_validation.py`, `docs/DATA_PIPELINE_GUIDE.md` | 28 checks; a beginner's walkthrough of every script |
| **Phase 4:** cleaning | `app/data_processing/cleaning.py`, `data_science/07_clean_data.py` | Fixes what is safe, quarantines the rest with reasons; dirty data → 0 errors |
| **Phase 4:** EDA | `data_science/08_eda.py` | 7 Matplotlib charts with the key findings |
| **Phase 4:** quality report | `app/data_processing/quality_report.py`, `data_science/15_data_quality_report.py` | PASS/WARN/FAIL per file, as Markdown + CSV |
| **Phase 4:** upload service | `app/services/data_upload_service.py` | Checks an uploaded CSV: readable, which dataset, valid incl. references |
| **Phase 4:** tests | `tests/unit/test_data_cleaning.py`, `test_upload_service.py` | 29 checks |
| **Phase 5:** API 1 | `POST /api/v1/skills/analyze` | Gaps, gap score, match %, explained suggestions, what-if levels |
| **Phase 5:** layers | `app/domain`, `app/repositories`, `app/services/skill_analysis.py`, `app/schemas`, `app/api` | Data source swappable; logic reusable by dashboard and Phase 6 |
| **Phase 5:** tests + docs | `tests/unit/test_skill_analysis.py`, `tests/api/test_skills_api.py`, `docs/API_DOCUMENTATION.md` | 21 + 8 checks; full endpoint reference |
| **Phase 6:** API 2 | `POST /api/v1/roles/match` | All roles ranked by match %, readiness, explanations; same numbers as API 1 |
| **Phase 6:** first ML | `app/services/role_similarity.py` | TF-IDF + cosine similarity (scikit-learn) for related roles |
| **Phase 6:** tests + docs | `tests/unit/test_role_matching.py`, `tests/api/test_roles_api.py`, `docs/ML_MODEL_GUIDE.md` | 23 + 6 checks; algorithm guide |
| **Phase 7:** API 3 | `POST /api/v1/trainings/recommend` | Courses for each gap, hybrid score with its parts, plain-language reasons |
| **Phase 7:** tests + docs | `tests/unit/test_training_recommendation.py`, `tests/api/test_trainings_api.py` | 21 + 5 checks; API and ML guide sections |
| **Phase 8:** ML engine | `app/ml/` (features, train, evaluate, model_registry, predict) | Predicts course completion; no leakage; versioned models with rollback |
| **Phase 8:** ML scripts | `data_science/09_feature_engineering.py` … `13_predict.py` | Features → split → train/compare → evaluate → predict, step by step |
| **Phase 8:** API 3 + model | `app/api/dependencies.py` | API 3 uses the model's completion probability when one is registered |
| **Phase 8:** tests + docs | `tests/unit/test_completion_model.py`, `docs/ML_MODEL_GUIDE.md` section 5 | 16 + 1 checks; model guide |
| **Phase 9:** database | `app/database/` (connection, migrate, tables, `migrations/0001_create_lms_tables.sql`) | 11 SQLite tables with keys, references and CHECK rules; versioned migrations |
| **Phase 9:** SQL repository | `app/repositories/sqlite_repository.py` | `DATA_SOURCE=database` makes the APIs read from SQLite, with identical answers |
| **Phase 9:** learning script | `data_science/14_save_to_database.py` | Validate → migrate → load in one transaction → JOIN, GROUP BY and constraint examples |
| **Phase 9:** tests + docs | `tests/unit/test_database.py`, `tests/api/test_database_source.py`, `docs/DATABASE_GUIDE.md` | 22 + 5 checks; database guide |
| **Phase 10:** API 4 | `GET /api/v1/learning-path/{employee_id}` | The courses that close every gap, prerequisites first, with progress and the next action |
| **Phase 10:** path engine | `app/services/learning_path.py` | Greedy course selection + topological sort; completed courses count as evidence |
| **Phase 10:** tests + docs | `tests/unit/test_learning_path.py`, `tests/api/test_learning_path_api.py` | 15 + 5 checks (incl. all 1,300 employee × role paths); API and ML guide sections |
| **Phase 11:** LLM layer | `app/llm/` (Ollama, fallback, auto choice, prompts, guardrails) | Local language model with a labelled no-LLM fallback; data stays on the machine |
| **Phase 11:** explanations | `app/services/explanation_service.py`, API 4 `?explain=true`, `GET /api/v1/health/llm` | Plain-language learning paths, grounded in the engine's facts and checked |
| **Phase 11:** check + tests + docs | `scripts/check_llm.py`, `tests/unit/test_llm.py`, `tests/api/test_llm_api.py`, `docs/LLM_RAG_GUIDE.md` | 24 + 4 checks with a fake Ollama server; LLM guide |
| **Phase 12:** documents | `documents/` (8 samples: Markdown, PDF, Word), `scripts/generate_documents.py` | Policies, FAQ, guides, plus a course catalogue and role profiles generated from the data |
| **Phase 12:** RAG search | `app/rag/` (loader, chunking, embeddings, vector store, index) | Ollama `nomic-embed-text` or TF-IDF embeddings; FAISS or NumPy search; one index per tenant |
| **Phase 12:** scripts + tests + docs | `scripts/build_index.py`, `scripts/search_documents.py`, `GET /api/v1/health/rag`, `tests/unit/test_rag.py` | 36 + 2 checks; LLM guide section 10 |
| **Phase 13:** API 5 | `POST /api/v1/ai/chat`, `app/services/chat_service.py`, `scripts/ask.py` | Answers from LMS data + cited documents; says when it does not know; conversations |
| **Phase 13:** API 7 | `POST /api/v1/rag/ingest`, `GET`/`DELETE /api/v1/rag/documents`, `app/services/ingestion_service.py` | Upload PDF/DOCX/TXT/CSV/MD; updates, duplicate detection, deletion, rollback |
| **Phase 13:** tests + docs | `tests/unit/test_chat.py`, `test_ingestion.py`, `tests/api/test_chat_api.py`, `test_rag_api.py` | 19 + 14 + 3 unit, 8 API checks; LLM guide section 11, API docs |
| **Phase 14:** integration tests | `tests/integration/test_business_flow.py`, `test_api_flow.py` | The APIs agree for all 100 employees; the full journey over HTTP |
| **Phase 14:** API contract | `app/schemas/contract.py`, `docs/api_contract.json`, `scripts/update_api_contract.py`, `tests/api/test_api_contract.py` | Request/response shapes cannot change by accident; every error has the shared format |
| **Phase 14:** smoke test + CI | `scripts/api_smoke_test.py`, `.github/workflows/ci.yml` | Every API over real HTTP against a running server (and the CI container); coverage report |
| **Phase 14:** guide | `docs/TESTING_GUIDE.md`, `@pytest.mark.slow` | Test layers, test doubles, contract workflow; `pytest -m "not slow"` for quick runs |
| **Phase 15:** dashboard | `dashboard/Home.py` + 8 pages, `.streamlit/config.toml` | Home, data upload, skills, roles, recommendations, learning path, AI assistant, documents, models |
| **Phase 15:** same services | `dashboard/components/` (data.py, ui.py) | Pages use the API's own services, so the numbers always match Swagger |
| **Phase 15:** tests + docs | `tests/unit/test_dashboard_data.py`, `tests/dashboard/test_pages.py`, `docs/DASHBOARD_GUIDE.md` | 9 helper tests + 16 AppTest page tests; dashboard guide; `dashboard` service in Docker Compose |
| **Phase 16:** API 6 | `POST /api/v1/ml/retrain` (admin key), `GET /api/v1/ml/status` | Validate → train → evaluate → compare with the current model → quality gate → register → promote only if approved |
| **Phase 16:** MLflow + security | `app/ml/retraining.py`, `app/ml/tracking.py`, `app/core/security.py`, `scripts/retrain.py` | Runs, metrics and approved versions in MLflow (alias `champion`); `X-Admin-Key` protects admin actions |
| **Phase 16:** tests + docs | `tests/unit/test_retraining.py`, `tests/api/test_ml_api.py`, ML guide section 7 | 15 + 6 checks; all seven APIs documented |
| **Phase 17:** login + roles | `app/security/` (passwords, users, tokens, access), `app/api/v1/auth.py`, `scripts/create_user.py` | JWT login; employees see only themselves, managers their team, admins everyone; tenants kept apart |
| **Phase 17:** admin protection | `app/api/dependencies.py` (`require_admin`) | API 6 and API 7 upload/delete: admin login or `X-Admin-Key`; dashboard pages 1, 7, 8 admin-only |
| **Phase 17:** abuse + audit | `app/security/rate_limit.py`, `audit.py`, `app/main.py` | Rate limits (429 + Retry-After), security headers, CORS, audit log, refuses to start with unsafe settings |
| **Phase 17:** AI + upload safety | `app/security/prompt_injection.py`, `uploads.py` | 4 prompt-injection layers in the assistant and uploads; renamed executables refused |
| **Phase 17:** tests + docs | `tests/security/`, `tests/api/test_auth_api.py`, `docs/SECURITY_GUIDE.md` | 64 + 14 + 4 dashboard checks; security guide |
| **Phase 18:** hardened image | `Dockerfile`, `.dockerignore` | Two stages, non-root user 10001, read-only code, no secrets, pinned base image |
| **Phase 18:** Compose | `compose.yaml`, `deployment/docker/compose.prod.yaml` | api + dashboard (+ mlflow, ollama profiles); 7 persistent volumes; read-only, no capabilities, localhost ports, limits |
| **Phase 18:** start step | `app/core/prepare.py` | Empty volumes become a working system: database + document index on first start |
| **Phase 18:** tests + docs | `tests/unit/test_docker_config.py`, `test_prepare.py`, CI hardened run, `docs/DOCKER_GUIDE.md` | 26 + 6 checks; PowerShell guide to build, run, stop, inspect, debug |
| **Phase 19:** hosting decision | `docs/PUBLIC_DEPLOYMENT_GUIDE.md` | Streamlit Community Cloud, Hugging Face Spaces, Render, Railway and others compared; dashboard on Streamlit Community Cloud, API on Render (both free) |
| **Phase 19:** public demo mode | `GUEST_ACCESS`, `BOOTSTRAP_ADMIN_PASSWORD`, `PREPARE_TRAIN_MODEL` | Visitors browse read-only without an account; admin from a secret; first model at start for the metrics |
| **Phase 19:** hosted LLM option | `app/llm/hosted_provider.py` (`LLM_PROVIDER=hosted`) | Any OpenAI-compatible service, explicit approval required; labelled fallback when unavailable |
| **Phase 19:** demo reset + hosting files | `POST /api/v1/admin/reset-demo`, `render.yaml`, `requirements-api.txt`, `dashboard/requirements.txt`, `deployment/cloud/` | Reset mechanism; Render Blueprint; slim installs for the free tiers; Streamlit secrets template |
| **Phase 19:** tests | `test_hosted_llm.py`, `test_prepare_hf_space.py`, `test_admin_api.py`, guest tests | 34 new checks |
| **Phase 20:** Kubernetes manifests | `deployment/kubernetes/` (kustomization, namespace, ConfigMap, PV + PVC, Deployments, Services, HPA, PDB) | API with 2–4 replicas and rolling updates, dashboard, shared persistent volume, readiness/liveness probes, resource limits, hardened pods |
| **Phase 20:** multi-replica ready | `app/api/dependencies.py`, `app/core/prepare.py` | Index and current model reload when another pod changes them; start step locked so one pod builds |
| **Phase 20:** tests + docs | `tests/unit/test_kubernetes_manifests.py`, CI `kubectl kustomize`, `docs/KUBERNETES_GUIDE.md` | 14 manifest checks + concurrent start test; PowerShell guide incl. Docker vs Kubernetes, scaling, rollback |

**All seven APIs are live:** 1 (`/skills/analyze`), 2 (`/roles/match`), 3 (`/trainings/recommend`), 4 (`/learning-path/{id}`), 5 (`/ai/chat`), 6 (`/ml/retrain`, admin) and 7 (`/rag/ingest`, admin). With `AUTH_ENABLED=true` they need a login (`/auth/token`). Full reference: [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md).

## 2. Folder structure

The full standalone structure is in place from Phase 1. Every folder has its own `README.md` explaining what goes in it and in which phase; folders marked *(later)* are filled as the phases progress. There is **no LMS integration code** in this project.

```
AIML-LMS-Skills-Intelligence/
├── app/                          # the engine (Python package)
│   ├── main.py                   # creates the FastAPI app – entry point        [Phase 1 ✓]
│   ├── core/                     # config.py, logging_config.py                [Phase 1 ✓]
│   ├── data_processing/          # schemas, loader, validators, cleaning, quality report  [Phases 3–4 ✓]
│   ├── api/v1/                   # health ✓, skills ✓, roles ✓, trainings ✓, learning_path ✓ (APIs 1–4); 3 more later  [Phase 10 ✓]
│   ├── schemas/                  # request/response models: common, skills, roles, trainings, learning_path  [Phase 10 ✓]
│   ├── services/                 # upload, skill_analysis, role_matching/similarity, training_recommendation, learning_path ✓  [Phases 4–10 ✓]
│   ├── domain/                   # Employee, Skill, JobRole … data classes     [Phase 5 ✓]
│   ├── repositories/             # base interface ✓, CSV ✓, SQLite ✓           [Phases 5, 9 ✓]
│   ├── database/                 # sqlite3 connection, migrations/*.sql, tables  [Phase 9 ✓]
│   ├── ml/                       # features, train, evaluate, registry, predict ✓; MLflow later  [Phase 8 ✓]
│   ├── rag/                      # load, chunk, embed, FAISS/NumPy store, search ✓  [Phases 12–13 ✓]
│   ├── llm/                      # Ollama + fallback providers, prompts, guardrails ✓  [Phase 11 ✓]
│   └── security/                 # auth, roles, rate limits, audit             (later, 17)
├── dashboard/                    # Streamlit UI: Home.py, pages/ (8), components/  [Phase 15 ✓]
├── data_science/                 # scripts 01–15 ✓                             [Phases 3–4, 8–9 ✓]
├── data/
│   ├── sample/                   # 11 synthetic CSV files                      [Phase 2 ✓]
│   ├── raw/  processed/  uploads/
├── documents/                    # 8 sample knowledge documents (md, pdf, docx)  [Phase 12 ✓]
├── vector_store/                 # saved knowledge indexes (not in Git)        [Phase 12 ✓]
├── models/                       # trained model versions (not in Git)         [Phase 8 ✓]
├── notebooks/                    # optional exploration notebooks
├── migrations/                   # reserved for Alembic (SQL migrations are in app/database/)
├── scripts/
│   ├── verify_phase1.py          # checks setup, starts API, runs tests        [Phase 1 ✓]
│   ├── generate_synthetic_data.py  # creates data/sample                       [Phase 2 ✓]
│   └── make_dirty_data.py        # data/raw/dirty with 17 planted defects       [Phase 3 ✓]
├── tests/
│   ├── api/test_health.py        # 6 tests                                     [Phase 1 ✓]
│   ├── unit/test_synthetic_data.py # 48 data checks                            [Phase 2 ✓]
│   ├── unit/test_data_validation.py # 28 validation checks                     [Phase 3 ✓]
│   ├── unit/test_data_cleaning.py, test_upload_service.py # 29 checks        [Phase 4 ✓]
│   ├── unit/test_skill_analysis.py, api/test_skills_api.py # 21 + 8 checks  [Phase 5 ✓]
│   ├── unit/test_role_matching.py, api/test_roles_api.py # 23 + 6 checks   [Phase 6 ✓]
│   ├── unit/test_training_recommendation.py, api/test_trainings_api.py # 21 + 5  [Phase 7 ✓]
│   ├── unit/test_completion_model.py # 16 checks (+1 API)                   [Phase 8 ✓]
│   ├── unit/test_database.py, api/test_database_source.py # 22 + 6 checks   [Phase 9 ✓]
│   ├── unit/test_learning_path.py, api/test_learning_path_api.py # 15 + 5  [Phase 10 ✓]
│   ├── unit/test_llm.py, api/test_llm_api.py # 24 + 4 checks (fake Ollama)  [Phase 11 ✓]
│   ├── unit/test_rag.py, api/test_rag_api.py # 39 + 4 checks               [Phases 12–13 ✓]
│   ├── unit/test_chat.py, test_ingestion.py, api/test_chat_api.py # 19 + 14 + 6  [Phase 13 ✓]
│   ├── integration/              # business flow, HTTP journey, API contract (24)  [Phase 14 ✓]
│   ├── api/test_api_contract.py  # OpenAPI = contract; error format of every endpoint (20)  [Phase 14 ✓]
│   ├── dashboard/test_pages.py   # every Streamlit page with AppTest (16)          [Phase 15 ✓]
│   ├── unit/test_retraining.py, api/test_ml_api.py # 15 + 6 checks            [Phase 16 ✓]
│   ├── security/, api/test_auth_api.py # 64 + 14 checks (login, roles, limits, injection) [Phase 17 ✓]
│   ├── unit/test_docker_config.py, test_prepare.py # 26 + 6 checks            [Phase 18 ✓]
│   ├── unit/test_hosted_llm.py, test_prepare_hf_space.py, api/test_admin_api.py [Phase 19 ✓]
│   ├── unit/test_kubernetes_manifests.py # 14 checks                        [Phase 20 ✓]
│   ├── unit/  integration/  security/
├── reports/                      # generated charts and reports (not in Git)   [Phase 4]
├── deployment/                   # docker/, kubernetes/, cloud/                (later, 18–20)
├── docs/                         # guides, added per phase
├── .github/workflows/ci.yml      # GitHub Actions: lint, test, Docker build    [Phase 1 ✓]
├── Dockerfile  compose.yaml  .dockerignore   # hardened, start step, volumes   [Phases 1, 18 ✓]
├── requirements.txt  requirements-dev.txt  pyproject.toml  .pre-commit-config.yaml
├── .env.example  .gitignore
└── README.md
```

## 3. Prerequisites (Windows 11)

| Tool | Check in PowerShell | Get it |
| --- | --- | --- |
| Python 3.11 | `py -3.11 --version` | python.org → Windows installer; tick "Add python.exe to PATH" |
| Git | `git --version` | git-scm.com |
| PyCharm | — | Community or Professional |
| Docker Desktop (for section 6) | `docker --version` and `docker compose version` | docker.com; Compose 2.24 or newer |

## 4. Set up and run in PyCharm

1. **Open the project:** PyCharm → *File → Open* → select the `AIML-LMS-Skills-Intelligence` folder.
2. **Create the virtual environment** in PyCharm's Terminal (PowerShell):

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell says *running scripts is disabled*, run this once, then activate again:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

   Your prompt now starts with `(.venv)`.

3. **Tell PyCharm to use it:** *File → Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter → Existing* → `.venv\Scripts\python.exe`.
4. **Install libraries:**

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements-dev.txt
   ```

5. **Create your settings file:**

   ```powershell
   Copy-Item .env.example .env
   ```

6. **Run the API:**

   ```powershell
   uvicorn app.main:app --reload
   ```

   Expected output (times and IDs will differ):

   ```
   INFO:     Will watch for changes in these directories: [...]
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
   2026-11-07 10:30:00 | INFO     | app.main | req=- | LMS Skills Intelligence Engine v0.1.0 started (env=development, profile=local)
   INFO:     Application startup complete.
   ```

7. **Open Swagger UI:** http://127.0.0.1:8000/docs → expand **GET /api/v1/health** → *Try it out* → *Execute*. Expected response body:

   ```json
   {
     "status": "ok",
     "app_name": "LMS Skills Intelligence Engine",
     "version": "0.1.0",
     "environment": "development",
     "profile": "local",
     "timestamp": "2026-11-07T05:00:00.123456Z"
   }
   ```

   The terminal logs one line per request, for example `req=3f2a9c1e | GET /api/v1/health -> 200 (1.8 ms)`.

8. **Verify everything in one go** (stop the server first with Ctrl+C, or use a second terminal):

   ```powershell
   python scripts/verify_phase1.py
   ```

   Expected last line: `Phase 1 verified: 10/10 checks passed.` Any `FAIL` line tells you what to fix.

**Optional – run with PyCharm's green button:** *Run → Edit Configurations → + → Python*. Choose *Module name* `uvicorn`, Parameters `app.main:app --reload`, and set Working directory to the project folder.

## 5. Tests and code quality

```powershell
pytest -v              # expected: 465 passed (344 unit + 79 API + 26 integration + 16 dashboard)
pytest -m "not slow"   # quick run (skips tests that start scripts or train models)
ruff check .           # expected: All checks passed!
ruff format --check .  # expected: N files already formatted
pre-commit install     # one time: runs Ruff automatically before each commit
```

In PyCharm you can also right-click the `tests` folder → *Run 'pytest in tests'*.

## 5a. Synthetic data (Phase 2)

The engine is developed on **synthetic** LMS data: realistic but invented, so no real employee data is ever used. The files are already in `data/sample/`. To recreate them:

```powershell
python scripts/generate_synthetic_data.py
```

Expected output:

```
Writing synthetic LMS data to ...\data\sample (seed 42, as of 2026-10-31)
  skills.csv                     42 rows
  skill_proficiency.csv           5 rows
  job_roles.csv                  13 rows
  role_required_skills.csv       87 rows
  courses.csv                    80 rows
  course_skills.csv              84 rows
  course_prerequisites.csv       61 rows
  employees.csv                 100 rows
  employee_skills.csv           925 rows
  career_goals.csv               63 rows
  training_history.csv          554 rows
Done: 11 files written.
```

- **Same seed, same files.** Seed 42 always gives identical data, and a test fails if the CSVs are edited by hand.
- **The worked example is built in.** Employee **E1001** is the Software Developer from the requirements who wants to become a Data Engineer (Python 3/4, SQL 2/4, AWS 1/3, Machine Learning 2/2, Docker 2/3).
- **Every column is explained** in [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).
- Run only the data tests with `pytest tests/unit -v` (expected: `48 passed`).

## 5b. Data validation with Pandas (Phase 3)

Install the new libraries once (Pandas and NumPy were added to `requirements.txt`):

```powershell
pip install -r requirements-dev.txt
```

Run the learning scripts from the project folder, in order:

```powershell
python data_science/01_read_csv.py           # DataFrames and reading CSV files
python data_science/02_inspect_data.py       # head, info, describe, value_counts, groupby
python data_science/03_validate_schema.py    # columns and types
python data_science/04_validate_nulls.py     # empty values
python data_science/05_validate_values.py    # ranges, allowed values, rules, references
python data_science/06_validate_duplicates.py
```

On the clean data, scripts 03–06 each end with `No problems found.` Then practise on data with planted problems:

```powershell
python scripts/make_dirty_data.py
python data_science/05_validate_values.py --data data/raw/dirty
```

The step-by-step explanation, the answer key and the expected results are in [`docs/DATA_PIPELINE_GUIDE.md`](docs/DATA_PIPELINE_GUIDE.md).

## 5c. Cleaning, charts and quality report (Phase 4)

Install the new library once (Matplotlib was added to `requirements.txt`):

```powershell
pip install -r requirements-dev.txt
```

Then clean the practice data, draw the charts and write the reports:

```powershell
python scripts/make_dirty_data.py
python data_science/07_clean_data.py --data data/raw/dirty                  # 19 errors -> No problems found
python data_science/08_eda.py                                                # 7 charts in reports/eda
python data_science/15_data_quality_report.py --data data/raw/dirty --out reports/quality_dirty
python data_science/15_data_quality_report.py --data data/processed --out reports/quality_processed
```

Cleaned files go to `data/processed/`, together with `cleaning_log.csv` (every change) and `rejected_rows.csv` (every row set aside, with its line and reason). Section 6 of [`docs/DATA_PIPELINE_GUIDE.md`](docs/DATA_PIPELINE_GUIDE.md) explains each step, the charts' findings and the upload service.

## 5d. API 1: Skills Analysis (Phase 5)

Start the server and open Swagger UI:

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs → **1. Skills Analysis → POST /api/v1/skills/analyze** → *Try it out*. Use the first example (`E1001`, `R004`) and click *Execute*. Expected: `"gap_score": 37.5`, `"match_percentage": 62.5`, and suggestions starting with *"Raise AWS (mandatory) from level 1 to 3."*

Or from PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/skills/analyze -ContentType "application/json" -Body '{"employee_id": "E1001", "target_role_id": "R004"}'
```

The API serves the CSV files in `DATA_DIR` (default `data/sample`). Every field, the formulas, the errors and a worked example are in [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md).

## 5e. API 2: Job Role Matching (Phase 6)

Install the new library once (`scikit-learn` was added to `requirements.txt`):

```powershell
pip install -r requirements-dev.txt
```

Then in Swagger UI: **2. Job Role Matching → POST /api/v1/roles/match → Try it out** with `{"employee_id": "E1001"}`. Expected:
- Software Developer (current role, 100%) is first, then QA Engineer and Data Engineer at 62.5%.
- `target` is Data Engineer, rank 3.
- `related_roles` starts with Machine Learning Engineer (similarity 0.72).

Endpoint reference: [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md). How TF-IDF similarity works: [`docs/ML_MODEL_GUIDE.md`](docs/ML_MODEL_GUIDE.md).

## 5f. API 3: Training Recommendations (Phase 7)

In Swagger UI: **3. Training Recommendations → POST /api/v1/trainings/recommend → Try it out** with `{"employee_id": "E1001"}`. Expected order:

1. `C-SQL-201` (score 1.00)
2. `C-PY-201` (0.95)
3. `C-AWS-101` (0.66)
4. `C-AWS-201` (0.41, "Complete first: C-AWS-101")
5. `C-DOCKER-201` (1.00, but Docker is optional for Data Engineer, so it comes last)

Each course comes with its score parts and a reason. The score formula and the example are in [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md); why it is designed this way is in [`docs/ML_MODEL_GUIDE.md`](docs/ML_MODEL_GUIDE.md) section 4.

## 5g. Course-completion model (Phase 8)

```powershell
python data_science/09_feature_engineering.py
python data_science/10_split_data.py
python data_science/11_train_model.py      # saves models/completion_model_v1.joblib
python data_science/12_evaluate_model.py   # expected: roc_auc 0.693 (baseline 0.5)
python data_science/13_predict.py
```

Restart uvicorn, then call API 3 again for E1001: the same five courses in the same order, now with a `completion_probability` (C-SQL-201: 0.59, score 0.94), and a note that the model was trained on synthetic data. Without a trained model, API 3 works exactly as in Phase 7. Model files are not committed to Git, and the Docker image does not contain one. How it works: [`docs/ML_MODEL_GUIDE.md`](docs/ML_MODEL_GUIDE.md) section 5.

## 5h. Database (Phase 9)

```powershell
python data_science/14_save_to_database.py   # validates, creates data/lms_ai.db, loads 11 tables, runs SQL examples
```

Expected: 11 tables loaded (for example `employee_skills 925`), `gap score = 100 x 6 / 16 = 37.5` computed in SQL, and three bad inserts refused by the database.

To make the API read from the database, set `DATA_SOURCE=database` in `.env` and restart uvicorn. APIs 1–3 give exactly the same answers as with the CSV files. The database file is not committed to Git. Run script 14 again after changing the CSV files. How it works: [`docs/DATABASE_GUIDE.md`](docs/DATABASE_GUIDE.md).

## 5i. API 4: Personalised Learning Path (Phase 10)

In Swagger UI: **4. Learning Path → GET /api/v1/learning-path/{employee_id} → Try it out** with `E1001`. Expected:

1. `C-SQL-201` (21 h)
2. `C-PY-201`
3. `C-AWS-101`
4. `C-AWS-201`, after step 3 (its prerequisite)
5. `C-DOCKER-201` (optional skill, so last)

Progress: match 62.5 % now and 100 % after 5 steps (90 hours). Next action: "Enrol in C-SQL-201 …". Try `target_role_id=R009`, or `include_optional=false`. How the path is built: [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md) (API 4) and [`docs/ML_MODEL_GUIDE.md`](docs/ML_MODEL_GUIDE.md) section 6.

## 5j. Language model with Ollama (Phase 11)

The engine works without a language model. With **Ollama** running, it can also explain results in plain language. Everything runs on your PC.

```powershell
# one time (see docs/LLM_RAG_GUIDE.md; low space on C:? set OLLAMA_MODELS to D: first)
ollama pull llama3.2:3b
python scripts/check_llm.py        # expected: "OK    Ollama is running with llama3.2:3b." and an explanation
```

Then, in Swagger UI:
- **Health → GET /api/v1/health/llm** shows `available: true` and the installed models.
- **4. Learning Path → E1001 with `explain = true`** returns an `explanation` written by the model, with the `facts` it was given and `grounding_warnings` (empty is good).

Without Ollama (`LLM_PROVIDER=auto`), the same request returns a labelled "Fallback - no LLM" list of facts, and `notes` says why. Guide: [`docs/LLM_RAG_GUIDE.md`](docs/LLM_RAG_GUIDE.md).

## 5k. Document search (Phase 12)

The assistant (Phase 13) will answer from **approved documents** in `documents/`. Phase 12 builds the search:

```powershell
pip install -r requirements.txt              # adds pypdf and faiss-cpu
ollama pull nomic-embed-text                 # optional, ~270 MB: search by meaning (else TF-IDF, by words)
python scripts/build_index.py                # expected: "Indexed 8 documents as 132 chunks"
python scripts/search_documents.py "How many times can I retake a course?"
```

Each result shows a score, the source file, the section and (for PDFs) the page. **Health → GET /api/v1/health/rag** in Swagger shows what the index contains. Guide: [`docs/LLM_RAG_GUIDE.md`](docs/LLM_RAG_GUIDE.md) section 10.

## 5l. AI assistant and document uploads (Phase 13)

```powershell
pip install -r requirements.txt     # adds python-multipart (file uploads)
python scripts/build_index.py
python scripts/ask.py "What are my current skill gaps?" --employee E1001
python scripts/ask.py "How many learning hours do I have per year?"
```

In Swagger UI:
- **5. AI Assistant → POST /api/v1/ai/chat**: try the examples. Each answer lists `intents` (what was looked up), `facts`, `sources` [S1]… and `grounding_warnings`.
- **7. Knowledge Documents → POST /api/v1/rag/ingest**: upload a `.pdf`, `.docx`, `.txt`, `.csv` or `.md`. The next question can use it at once. `GET /api/v1/rag/documents` lists what is indexed; `DELETE` removes an upload.

Without Ollama, a labelled fallback lists the facts and passages instead of writing an answer. Guide: [`docs/LLM_RAG_GUIDE.md`](docs/LLM_RAG_GUIDE.md) section 11; reference: [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md) (APIs 5 and 7).

## 5m. Testing everything together (Phase 14)

```powershell
pytest                                   # 414 tests: unit, API, integration
uvicorn app.main:app                     # then, in a second window:
python scripts/api_smoke_test.py         # every API over real HTTP: PASS / WARN / FAIL with timings
```

- **Integration tests** check that the APIs never contradict each other, for all 100 employees: the same gap score in APIs 1 and 2, the same course scores in APIs 3 and 4, and the assistant repeating the path's next action.
- **Contract tests** keep every request and response shape stable for the dashboard and the future LMS integration (`docs/api_contract.json`). After an intended API change, run `python scripts/update_api_contract.py` and review the diff.
- **CI** now runs the smoke-test script against the Docker container and prints a coverage report.

Guide: [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md).

## 5n. Dashboard (Phase 15)

```powershell
pip install -r requirements.txt     # adds streamlit
streamlit run dashboard/Home.py      # opens http://localhost:8501
```

Nine pages: **Home** (totals, completion, gaps, top recommendations), **Data upload**, **Skills analysis**, **Role matching**, **Recommendations**, **Learning path** (with an LLM explanation), **AI assistant** (chat with sources), **Document management** and **Model management** (admin). The selected employee is remembered across pages; E1001 is the default. The dashboard uses the same services as the API, so it does not need uvicorn running. Guide: [`docs/DASHBOARD_GUIDE.md`](docs/DASHBOARD_GUIDE.md).

## 5o. API 6: controlled retraining with MLflow (Phase 16)

```powershell
pip install -r requirements.txt     # adds mlflow
python -c "import secrets; print(secrets.token_urlsafe(32))"   # put the output in .env: ADMIN_API_KEY=...
python scripts/retrain.py --reason "first run"                 # or API 6 / the dashboard's Model page
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db        # see the runs at http://127.0.0.1:5000
```

In Swagger: **6. ML Model Management → POST /api/v1/ml/retrain** with your key in `x-admin-key`. The response shows the **quality gate** (minimum ROC AUC 0.60, better than chance, no drop versus the current model on the same test rows) and whether the new version was **promoted**. Every run saves a new version; only approved ones become current; old versions stay for rollback. `GET /api/v1/ml/status` lists versions and runs. Guide: [`docs/ML_MODEL_GUIDE.md`](docs/ML_MODEL_GUIDE.md) section 7.

## 5p. Security: login, roles, rate limits, audit (Phase 17)

Locally nothing changes: login is **off** by default and the sidebar / log say so. To try login:

```powershell
pip install -r requirements.txt                                   # adds pyjwt
python -c "import secrets; print(secrets.token_urlsafe(48))"      # .env: AUTH_SECRET_KEY=<output>, AUTH_ENABLED=true
python scripts/create_demo_users.py                               # employee (E1001), manager (E1064), admin; passwords shown once
uvicorn app.main:app --reload                                     # Swagger: the Authorize button
python scripts/api_smoke_test.py --username admin --password <admin password>
```

Log in as `employee` and `GET /api/v1/learning-path/E1002` gives **403**; as `manager` you see E1064's team; only `admin` (or `X-Admin-Key`) may retrain or upload. Every API call is written to `logs/audit.jsonl`. The assistant refuses "ignore your instructions…" questions and uploads with hidden instructions. Guide: [`docs/SECURITY_GUIDE.md`](docs/SECURITY_GUIDE.md).

## 5q. Public demo: Streamlit Community Cloud + Render (Phase 19)

| Part | Host (free) | How |
| --- | --- | --- |
| Dashboard | Streamlit Community Cloud | share.streamlit.io → Create app → repo, branch `main`, file `dashboard/Home.py`, Python 3.11, secrets from `deployment/cloud/streamlit/secrets.toml.example` |
| API + Swagger | Render | render.com → New → Blueprint → this repo (`render.yaml`); enter the admin password |

Both redeploy automatically on every push to `main`. Visitors browse as read-only guests; uploads, retraining and the demo reset are admin-only. Without a hosted LLM the assistant answers in a clearly labelled fallback mode. Full steps, the hosting comparison, verification checklist, walkthrough and known limitations: [`docs/PUBLIC_DEPLOYMENT_GUIDE.md`](docs/PUBLIC_DEPLOYMENT_GUIDE.md).

## 5r. Kubernetes with Minikube (Phase 20)

```powershell
minikube start --driver=docker --cpus=4 --memory=6144
minikube addons enable metrics-server
minikube image build -t aiml-lms-skills-intelligence:dev .
kubectl apply -f deployment/kubernetes/namespace.yaml
Copy-Item deployment/kubernetes/secret.example.env deployment/kubernetes/secret.env   # fill in your values
kubectl -n lms-skills create secret generic lms-secrets --from-env-file=deployment/kubernetes/secret.env
kubectl apply -k deployment/kubernetes
kubectl -n lms-skills get pods -w
kubectl -n lms-skills port-forward service/lms-api 18000:80    # http://127.0.0.1:18000/docs
```

Two API replicas (autoscaled 2–4), the dashboard, and one persistent volume for the database, index, uploads, models and accounts. Pods have readiness and liveness probes, resource limits, and run as non-root with a read-only filesystem. Full guide with Docker vs Kubernetes, scaling, rolling updates, rollback and troubleshooting: [`docs/KUBERNETES_GUIDE.md`](docs/KUBERNETES_GUIDE.md).

## 6. Run with Docker (hardened in Phase 18)

Docker Desktop must be running. Full guide with build, run, stop, inspect and debug commands: [`docs/DOCKER_GUIDE.md`](docs/DOCKER_GUIDE.md).

```powershell
docker compose up --build -d          # build the image, start api + dashboard (first start about a minute)
docker compose ps                     # wait until both show (healthy)
docker compose logs api | Select-String prepare   # the start step: database + index created on first start
docker compose down                   # stop (volumes - your data - are kept; add -v for a fresh start)
docker compose --profile mlflow up -d # optional: MLflow UI at http://127.0.0.1:5000
```

Then open http://127.0.0.1:8000/docs (API) and http://127.0.0.1:8501 (dashboard). On the first start the API container prepares its empty volumes by itself: the SQLite database with the synthetic data and the document index. No manual `build_index.py` is needed.

| | |
| --- | --- |
| Services | `api`, `dashboard`; optional `mlflow` (profile `mlflow`) and `ollama` (profile `llm`) |
| Volumes | database, document index, uploads, model versions, MLflow runs, accounts, audit log |
| Hardening | non-root user 10001, two-stage image, read-only filesystem, no Linux capabilities, ports on 127.0.0.1 only, memory limits, rotated logs, no secrets in the image |
| Shared server | `docker compose -f compose.yaml -f deployment/docker/compose.prod.yaml up -d` (login on, secret required) |
| CI | builds the image, checks the non-root user, runs it hardened on empty volumes, smoke test |

## 7. GitHub and CI/CD

Repository: **https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence**

### Branches

| Branch | Holds | Updated by |
| --- | --- | --- |
| `main` | Stable, reviewed releases only | Pull request from `development` |
| `development` | Day-to-day integrated work; all phases land here first | Pull requests from phase branches |
| `phase-N-...` | One phase's work in progress, e.g. `phase-4-cleaning-eda` | Your commits |

Flow: `phase-N-...` → pull request → `development` → (when a milestone is stable) pull request → `main`, plus a version tag.

### First push (one time)

Create an **empty** repository named `AIML-LMS-Skills-Intelligence` on GitHub (no README, .gitignore or licence), then:

```powershell
git init
git add .
git status                       # .env, .venv and data/raw must NOT be listed
git commit -m "Phases 1-3: FastAPI skeleton, synthetic LMS data, Pandas validation engine"
git branch -M main
git remote add origin https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence.git
git push -u origin main
git checkout -b development
git push -u origin development
```

### Each new phase

```powershell
git checkout development
git pull
git checkout -b phase-4-cleaning-eda
# ...work, test, then:
git add .
git commit -m "Phase 4: data cleaning, EDA, quality report"
git push -u origin phase-4-cleaning-eda
# On GitHub: open a pull request into development, wait for the green CI tick, merge.
```

### What CI does

`.github/workflows/ci.yml` runs on every push and pull request to `main` or `development`:

1. Installs Python 3.11 and `requirements-dev.txt`.
2. `ruff check` (lint) and `ruff format --check` (formatting).
3. `pytest` (all tests).
4. Builds the Docker image, starts it and calls `/api/v1/health`.

See the results in the repository's **Actions** tab. Never commit `.env`, passwords or keys; `.gitignore` already blocks `.env`.

## 8. Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test` or `production` |
| `APP_PROFILE` | `local` | `local`, `compose` or `public-demo` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `API_V1_PREFIX` | `/api/v1` | URL prefix for all v1 endpoints |
| `DATA_DIR` | `data/sample` | Folder with the 11 LMS CSV files the API serves (e.g. `data/processed`) |
| `DATA_SOURCE` | `csv` | `csv` (files in `DATA_DIR`) or `database` (`DATABASE_URL`; create it with script 14) |
| `MODEL_DIR` | `models` | Folder of the model registry (Phase 8) |
| `USE_COMPLETION_MODEL` | `true` | `false` makes API 3 ignore any trained model |
| `DATABASE_URL` | `sqlite:///./data/lms_ai.db` | SQLite file used when `DATA_SOURCE=database`. Only `sqlite:///` URLs in this version; MySQL later |
| `LLM_PROVIDER` | `auto` | `auto` (Ollama, else labelled fallback), `ollama` (only; 503 when down) or `fallback` (no model) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `llama3.2:3b` | Where Ollama runs and which model to use (`ollama list`) |
| `LLM_TIMEOUT_SECONDS` / `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `120` / `0.2` / `512` | Model call limits; the first call loads the model and is slow |
| `LLM_ALLOW_REMOTE` | `false` | Allow a non-local Ollama host. Only with approval: employee data would leave the machine |
| `DOCUMENTS_DIR` / `VECTOR_STORE_DIR` / `RAG_TENANT` | `documents` / `vector_store` / `default` | Documents to index, where indexes are saved, index folder name |
| `EMBEDDING_PROVIDER` / `OLLAMA_EMBED_MODEL` | `auto` / `nomic-embed-text` | Ollama embeddings when installed, else TF-IDF; or force `ollama` / `tfidf` |
| `VECTOR_BACKEND` | `auto` | FAISS if installed, else NumPy; or force `faiss` / `numpy` |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` / `RAG_TOP_K` | `800` / `120` / `4` | Chunk size and overlap (characters), results per search |
| `RAG_UPLOAD_DIR` / `RAG_MAX_UPLOAD_MB` | `data/uploads/documents` / `10` | Where API 7 stores uploads; largest upload |
| `RAG_MIN_SCORE` | empty | Minimum passage similarity for the assistant (empty = TF-IDF 0.08, Ollama 0.45) |
| `ADMIN_API_KEY` | empty | Key for admin actions (API 6, header `X-Admin-Key`). Empty = admin actions off. Keep it only in `.env` |
| `ML_MIN_ROC_AUC` / `ML_MAX_REGRESSION` / `ML_MIN_TRAINING_ROWS` | `0.60` / `0.01` / `200` | The retraining quality gate |
| `MLFLOW_ENABLED` / `MLFLOW_TRACKING_URI` / `MLFLOW_EXPERIMENT` | `auto` / empty / `completion-model` | MLflow if installed; empty URI = `mlruns/mlflow.db` |

## 9. Troubleshooting

| Problem | Fix |
| --- | --- |
| `py` is not recognised | Reinstall Python 3.11 with "Add to PATH", or use the full path to `python.exe` |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `ModuleNotFoundError: No module named 'app'` | Run commands from the project folder (the one containing `app/`) |
| `Address already in use` on port 8000 | `uvicorn app.main:app --reload --port 8001` |
| `ValidationError` at start-up | A value in `.env` is not allowed, e.g. `APP_ENV=dev`; use a value from section 8 |
| `docker compose` rejects `env_file` | Update Docker Desktop (Compose 2.24 or newer) |
| `Database file not found` / `has no LMS data` | Run `python data_science/14_save_to_database.py`, or set `DATA_SOURCE=csv` |
| Explanations say "Fallback - no LLM" | Ollama is not running or the model is missing: `python scripts/check_llm.py` tells you which |
| `No knowledge index in ...` | `python scripts/build_index.py`, then restart uvicorn |
| The assistant says it has no information | Check the passage scores with `scripts/search_documents.py`; see `RAG_MIN_SCORE` in the LLM guide |
| A contract test fails | Unintended: fix the code. Intended API change: `python scripts/update_api_contract.py`, review and commit `docs/api_contract.json` |
| Dashboard: `No module named 'app'` | Start it from the project folder: `streamlit run dashboard/Home.py` |
| API 6 answers 403 `ADMIN_ACTIONS_DISABLED` | Set `ADMIN_API_KEY` in `.env` and restart uvicorn |
| Retraining says `rejected_by_quality_gate` | Working as intended: the new model was not good enough; the current one stays. See `quality_gate` for the reason |

## 10. Roadmap

Phase 1 ✓ → 2 synthetic datasets ✓ → 3 data validation ✓ → 4 cleaning, EDA, quality report, upload service ✓ → 5 skills analysis API ✓ → 6 role matching API ✓ → 7 recommendations API ✓ → 8 ML completion model ✓ → 9 database (SQLite) ✓ → 10 learning path API ✓ → 11 Ollama LLM ✓ → 12 embeddings + FAISS ✓ → 13 RAG + chat ✓ → 14 all APIs tested together ✓ → 15 Streamlit dashboard ✓ → 16 MLflow retraining ✓ → 17 security → 18 Docker hardening → 19 public demo → 20 Kubernetes → 21 full CI/CD with Snyk → 22 submission package.

The full plan, API contracts and database design are in the project blueprint (Enterprise LMS AI Intelligence Engine – Analysis & Technical Blueprint).

## 11. Future LMS integration

Not implemented here. The design keeps it possible without a rewrite: business logic will live in `app/services/`, independent of the UI; data will be read through repository interfaces (CSV/SQLite now, LMS MySQL later); and the seven `/api/v1` endpoints are stable contracts that the PHP/F3 backend can call.
