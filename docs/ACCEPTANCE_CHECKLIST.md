# Acceptance Checklist

Every public-demo acceptance criterion, with the evidence that it works. "Verified" means it was run and observed, not only written.

| | |
| --- | --- |
| Live dashboard | https://lms-skills-intelligence.streamlit.app |
| Live API / Swagger | https://lms-skills-api.onrender.com/api/v1 · https://lms-skills-api.onrender.com/docs |
| Repository | https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence |
| Checked | 8–9 November 2026 |

---

## 1. Acceptance criteria

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Project runs locally on Windows | ✅ Verified | Developed and run on Windows 11 (PowerShell, PyCharm): `uvicorn`, `streamlit`, `pytest` |
| 2 | All seven APIs work | ✅ Verified | Smoke test against the live API: APIs 1–5 pass. Jenkins smoke test on the development deployment: 17/17 including API 7 upload/list/delete. API 6 covered by `tests/api/test_ml_api.py` in CI, and refused without credentials on the live API |
| 3 | Swagger UI displays all seven APIs | ✅ Verified | Live `/docs`; `tests/api/test_api_contract.py` checks that the published OpenAPI matches `docs/api_contract.json` |
| 4 | Synthetic LMS data is available | ✅ Verified | 11 datasets in `data/sample/` (100 employees, 13 roles, 42 skills, 80 courses, 554 training records); validation scripts and 48 data tests |
| 5 | Employee skill analysis works | ✅ Verified | Live dashboard and API: E1001 → Data Engineer gap score 37.5, match 62.5 % |
| 6 | Job-role matching works | ✅ Verified | Live dashboard "Role Matching"; smoke test API 2 (Data Engineer among the matches) |
| 7 | Training recommendations work | ✅ Verified | Live: C-SQL-201 recommended first for E1001, with reason and score parts |
| 8 | Personalised learning path works | ✅ Verified | Live: 62.5 % → 100 %, 5 steps, 90 hours, next action C-SQL-201 |
| 9 | ML training and evaluation work | ✅ Verified | First model trained at start on every deployment ("Model: promoted: version 1, test ROC AUC 0.693"); metrics on the live Model Management page |
| 10 | Model retraining works with administrator controls | ✅ Verified | Live: retraining refused without credentials (401); "Administrators only" for guests; admin login shows the controls; quality gate tests in `tests/unit/test_retraining.py` |
| 11 | RAG ingestion works | ✅ Verified | Jenkins smoke test: API 7 upload → list → delete PASS; `tests/unit/test_ingestion.py` |
| 12 | FAISS index persists | ✅ Verified | FAISS backend where installed (Docker image, local); index on persistent volumes in Docker Compose (`lms_index`) and Kubernetes (PV/PVC); start step finds it "ready" on the next start. The free public demo uses the NumPy backend and rebuilds the index at start (documented) |
| 13 | AI assistant retrieves relevant documents | ✅ Verified | Live: "How many learning hours do I have per year?" answered from `learning_policy.md` with the passage shown; smoke test "Document index status" PASS |
| 14 | Streamlit dashboard works | ✅ Verified | Live dashboard: all 9 pages; AppTest page tests in CI |
| 15 | GitHub repository contains the complete source code | ✅ Verified | Branches `main` and `development`; every phase merged by pull request with green CI |
| 16 | Docker build succeeds | ✅ Verified | GitHub Actions on every push (build + hardened run + smoke test); Jenkins builds #1 and #2 |
| 17 | Deployment instructions are complete | ✅ Verified | `DOCKER_GUIDE.md`, `KUBERNETES_GUIDE.md`, `PUBLIC_DEPLOYMENT_GUIDE.md`, `JENKINS_CICD_GUIDE.md`; each followed end to end on Windows 11 |
| 18 | Public dashboard URL is accessible | ✅ Verified | https://lms-skills-intelligence.streamlit.app opened in a private browser window |
| 19 | Public users can interact with the demonstration | ✅ Verified | Guest mode: every employee selectable, all analyses and the assistant work without an account |
| 20 | Secrets and administrative operations are protected | ✅ Verified | Secrets only in host secret stores and git-ignored files; admin operations need an admin login or key (401/403 otherwise); live smoke test "Admin action refused without credentials" PASS |
| 21 | Suitable fallback if LLM inference is unavailable | ✅ Verified | Live assistant shows "Fallback mode – no language model…"; API answers carry `is_fallback: true`; with Ollama available the same code answers via the LLM (Jenkins smoke test "via ollama") |
| 22 | README explains the entire project | ✅ Verified | `README.md`: overview, live demo, architecture, quick start, documentation map, limitations |
| 23 | Screenshots and demo instructions are available | ✅ Demo instructions · screenshots being added | `DEMO_WALKTHROUGH.md`; screenshots go in `docs/screenshots/` with the file names listed there |

## 2. Deliverables

| # | Deliverable | Where |
| --- | --- | --- |
| 1 | Complete source code | `app/`, `dashboard/`, `scripts/`, `data_science/` |
| 2 | Synthetic LMS datasets | `data/sample/` (11 CSV files), generator `scripts/` |
| 3 | Seven working FastAPI APIs | `app/api/v1/` |
| 4 | Swagger documentation | `/docs` on any running API; `docs/API_DOCUMENTATION.md` |
| 5 | Working Streamlit dashboard | `dashboard/`; live URL |
| 6 | ML training and prediction | `app/ml/`; `docs/ML_MODEL_GUIDE.md` |
| 7 | LLM integration | `app/llm/` (Ollama, hosted, fallback) |
| 8 | RAG pipeline | `app/rag/`, `app/services/chat_service.py` |
| 9 | FAISS vector database | `app/rag/vector_store.py` |
| 10 | Controlled ML retraining | `app/ml/retraining.py`, API 6 |
| 11 | MLflow tracking | `app/ml/tracking.py`; `docker compose --profile mlflow up -d` |
| 12 | Docker configuration | `Dockerfile`, `compose.yaml`, `.dockerignore` |
| 13 | Kubernetes configuration | `deployment/kubernetes/` |
| 14 | Jenkinsfile | `Jenkinsfile`, `deployment/jenkins/` |
| 15 | Snyk configuration and instructions | `.snyk`, GitHub "Snyk security scan" job, `docs/SNYK_SECURITY_GUIDE.md` |
| 16 | Complete README | `README.md` |
| 17 | Project overview | `docs/PROJECT_OVERVIEW.md` |
| 18 | Architecture diagrams | `docs/ARCHITECTURE.md` |
| 19 | API documentation | `docs/API_DOCUMENTATION.md`, `docs/api_contract.json` |
| 20 | Screenshots | `docs/screenshots/` |
| 21 | Demo walkthrough | `docs/DEMO_WALKTHROUGH.md` |
| 22 | GitHub repository | https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence |
| 23 | Publicly accessible demo URL | https://lms-skills-intelligence.streamlit.app |
| 24 | Deployment instructions | `docs/PUBLIC_DEPLOYMENT_GUIDE.md`, `DOCKER_GUIDE.md`, `KUBERNETES_GUIDE.md` |
| 25 | Known limitations and future improvements | `README.md` section "Known limitations and future improvements" |

## 3. Quality evidence

| Check | Result |
| --- | --- |
| Automated tests | About 660 (unit, security, API, integration, contract, dashboard), green on every merge |
| Code quality | `ruff check` and `ruff format --check` clean on every merge |
| API contract | `docs/api_contract.json`: request/response shapes can't change by accident |
| Smoke tests | Live API (guest) 13 passed / 0 failed; Kubernetes 13 passed (admin upload pending a local Secret mismatch); Jenkins development deployment 17/17 |
| Security scan | Snyk: dependencies clean; container 7 findings → 2 after the Debian 13 base image; those 2 (no Debian fix yet) accepted until 2027-02-09 with the reason in `.snyk` |
| Kubernetes | 2 API replicas + dashboard Running 1/1 on Minikube; probes, limits, HPA, PV/PVC |
| Jenkins | 11 stages run end to end; last build UNSTABLE only because of the two base-image findings, accepted afterwards |
