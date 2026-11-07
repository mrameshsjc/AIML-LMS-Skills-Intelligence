# LMS Skills Intelligence Engine

Standalone AI/ML application for an enterprise LMS: **skills-gap analysis, job-role matching, explainable training recommendations, personalised learning paths and an LLM + RAG learning assistant.**

| | |
| --- | --- |
| Project folder / Git repo | `AIML-LMS-Skills-Intelligence` |
| Current phase | **Phase 9 – Database (SQLite)** (Phases 1–8 on GitHub, CI green) |
| Python | 3.11 |
| LMS integration | Not in this project. The architecture is API-ready for it (later phase). |

> All data in this project is **synthetic**. No real employee data is used.

---

## 1. What is built so far (Phases 1–9)

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
| Docker | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Run anywhere with one command |
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

APIs 1 (`/skills/analyze`), 2 (`/roles/match`) and 3 (`/trainings/recommend`) are live. The other four (`/learning-path/{id}`, `/ai/chat`, `/ml/retrain`, `/rag/ingest`) are added in later phases. Full reference: [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md).

## 2. Folder structure

The full standalone structure is in place from Phase 1. Every folder has its own `README.md` explaining what goes in it and in which phase; folders marked *(later)* are filled as the phases progress. There is **no LMS integration code** in this project.

```
AIML-LMS-Skills-Intelligence/
├── app/                          # the engine (Python package)
│   ├── main.py                   # creates the FastAPI app – entry point        [Phase 1 ✓]
│   ├── core/                     # config.py, logging_config.py                [Phase 1 ✓]
│   ├── data_processing/          # schemas, loader, validators, cleaning, quality report  [Phases 3–4 ✓]
│   ├── api/v1/                   # health ✓, skills ✓, roles ✓, trainings ✓ (APIs 1–3); 4 more later  [Phase 7 ✓]
│   ├── schemas/                  # request/response models: common, skills, roles, trainings  [Phase 7 ✓]
│   ├── services/                 # upload, skill_analysis, role_matching/similarity, training_recommendation ✓  [Phases 4–7 ✓]
│   ├── domain/                   # Employee, Skill, JobRole … data classes     [Phase 5 ✓]
│   ├── repositories/             # base interface ✓, CSV ✓, SQLite ✓           [Phases 5, 9 ✓]
│   ├── database/                 # sqlite3 connection, migrations/*.sql, tables  [Phase 9 ✓]
│   ├── ml/                       # features, train, evaluate, registry, predict ✓; MLflow later  [Phase 8 ✓]
│   ├── rag/                      # load, chunk, embed, FAISS, retrieve         (later, 12–13)
│   ├── llm/                      # Ollama / hosted / fallback providers        (later, 11)
│   └── security/                 # auth, roles, rate limits, audit             (later, 17)
├── dashboard/                    # Streamlit UI: pages/, components/           (later, 4, 15)
├── data_science/                 # scripts 01–15 ✓                             [Phases 3–4, 8–9 ✓]
├── data/
│   ├── sample/                   # 11 synthetic CSV files                      [Phase 2 ✓]
│   ├── raw/  processed/  uploads/
├── documents/                    # sample knowledge documents for RAG          (later, 13)
├── vector_store/                 # saved FAISS indexes (not in Git)            (later, 12)
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
│   ├── unit/test_database.py, api/test_database_source.py # 22 + 5 checks   [Phase 9 ✓]
│   ├── unit/  integration/  security/
├── reports/                      # generated charts and reports (not in Git)   [Phase 4]
├── deployment/                   # docker/, kubernetes/, cloud/                (later, 18–20)
├── docs/                         # guides, added per phase
├── .github/workflows/ci.yml      # GitHub Actions: lint, test, Docker build    [Phase 1 ✓]
├── Dockerfile  docker-compose.yml  .dockerignore                              [Phase 1 ✓]
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
pytest -v              # expected: 239 passed (31 API + 208 unit)
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

## 6. Run with Docker

Docker Desktop must be running.

```powershell
docker compose up --build -d   # build the image and start in the background
docker compose ps              # wait until STATUS shows (healthy)
docker compose logs -f api     # follow logs (Ctrl+C to stop following)
docker compose down            # stop and remove the container (data volume is kept)
```

Then open http://127.0.0.1:8000/docs as before.

| Docker term | Meaning here |
| --- | --- |
| Image | The packaged app (Python 3.11 + libraries + code), built from `Dockerfile` |
| Container | A running copy of the image |
| Volume `lms_data` | Storage that survives container restarts (database and index files in later phases) |
| Health check | Docker calls `/api/v1/health` every 30 s and shows `healthy` or `unhealthy` |

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

## 10. Roadmap

Phase 1 ✓ → 2 synthetic datasets ✓ → 3 data validation ✓ → 4 cleaning, EDA, quality report, upload service ✓ → 5 skills analysis API ✓ → 6 role matching API ✓ → 7 recommendations API ✓ → 8 ML completion model ✓ → 9 database (SQLite) ✓ → 10 learning path → 11 Ollama LLM → 12 embeddings + FAISS → 13 RAG + chat → 14 all seven APIs tested → 15 Streamlit dashboard → 16 MLflow retraining → 17 security → 18 Docker hardening → 19 public demo → 20 Kubernetes → 21 full CI/CD with Snyk → 22 submission package.

The full plan, API contracts and database design are in the project blueprint (Enterprise LMS AI Intelligence Engine – Analysis & Technical Blueprint).

## 11. Future LMS integration

Not implemented here. The design keeps it possible without a rewrite: business logic will live in `app/services/`, independent of the UI; data will be read through repository interfaces (CSV/SQLite now, LMS MySQL later); and the seven `/api/v1` endpoints are stable contracts that the PHP/F3 backend can call.
