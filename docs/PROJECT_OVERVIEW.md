# Project Overview: LMS Skills Intelligence Engine

| | |
| --- | --- |
| Author | Ramesh M |
| Repository | https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence |
| Live demo | Dashboard https://lms-skills-intelligence.streamlit.app · API https://lms-skills-api.onrender.com/docs |
| What it is | A standalone AI/ML service with seven REST APIs, a dashboard and an AI assistant, ready for an enterprise LMS to call |
| Data | **Synthetic only**: no real employee information |
| Status | Live, built in 22 phases (November 2026) |

---

## 1. Summary

Companies spend heavily on training, but most learning management systems (LMS) only *store* courses and completions. They don't answer the questions employees and managers actually ask: *Which skills am I missing for the role I want? Which course should I take next, and why? How far am I from being ready?*

The **LMS Skills Intelligence Engine** answers those questions with seven REST APIs, a web dashboard and an AI learning assistant:

- It compares each employee's skills with the requirements of their target job role (**skills-gap analysis**).
- It finds the roles an employee is closest to (**role matching**).
- It ranks courses with an **explainable hybrid score**, including a machine-learning prediction of whether the employee will finish the course.
- It orders those courses into a **personalised learning path** that respects prerequisites.
- It answers natural-language questions with an **LLM + RAG assistant** that cites company documents and never invents facts.

The engine runs as a standalone service with its own data, models and deployment, live on the internet, and an existing LMS (PHP/F3/Vue in our case) can call its APIs without changes to the engine.

## 2. The problem it solves

| Who | Today | Pain |
| --- | --- | --- |
| Employee | Browses a long course catalogue | Doesn't know which course matters for their goal, or in which order |
| Manager | Sees completion reports | Can't see team skill gaps toward roles, or plan development |
| L&D team | Buys and assigns courses | No evidence which courses close real gaps; low completion rates |
| HR / talent | Plans internal mobility | No quick view of who is close to a role |

## 3. What it does

1. Measures skill gaps against job-role requirements with a transparent, weighted formula.
2. Matches employees to roles, including roles they did not list as a goal.
3. Recommends training with a score every user can understand, not a black box.
4. Predicts course completion with a validated ML model and tracks model versions.
5. Builds an ordered, prerequisite-aware learning path with a clear next action.
6. Answers questions with an AI assistant grounded in LMS data and approved documents, with a clearly labelled fallback when no language model is available.
7. Runs like a production service: tests, security, containers, Kubernetes, CI/CD, vulnerability scanning, public demo.

## 4. What is included

**Included:** synthetic LMS data (100 employees, 13 roles, 42 skills, 80 courses, 554 training records); seven APIs; Streamlit dashboard; completion model with controlled retraining and MLflow; RAG over 8 company documents (Markdown, PDF, Word, CSV); login and roles; Docker, Kubernetes (Minikube), Jenkins, Snyk, GitHub Actions; public demo.

**Not included (future work):** integration code inside the existing LMS, real employee data, MySQL as the production database, single sign-on with the company identity provider.

## 5. How it works

```
LMS data (CSV / SQLite)  ──►  Services: skills · roles · recommendations · learning path
                                         │                 ▲
                                         ▼                 │ completion probability
Company documents ──► RAG index ──► AI assistant ◄── LLM (Ollama / hosted / fallback)
                                         │
                       FastAPI (7 APIs, Swagger)  ·  Streamlit dashboard
```

| # | API | Answers |
| --- | --- | --- |
| 1 | `POST /api/v1/skills/analyze` | Gap score, match %, missing and below-level skills for a target role |
| 2 | `POST /api/v1/roles/match` | Best-matching roles and what is missing for each |
| 3 | `POST /api/v1/trainings/recommend` | Ranked courses with reason, score parts, prerequisites, completion probability |
| 4 | `GET /api/v1/learning-path/{employee_id}` | Ordered steps, hours, projected readiness, next action |
| 5 | `POST /api/v1/ai/chat` | Grounded answers with document citations |
| 6 | `POST /api/v1/ml/retrain` | Controlled retraining with a quality gate (admins) |
| 7 | `POST /api/v1/rag/ingest` | Add company documents to the assistant's knowledge (admins) |

Worked example (E1001, Software Developer → Data Engineer): gap score **37.5**, match **62.5 %**, first course **C-SQL-201**, and the learning path reaches **100 %** in 5 steps (90 hours).

## 6. Methods

| Area | Method | Why |
| --- | --- | --- |
| Skills gap | Weighted formula: `gap_score = 100 × Σ w·gap / Σ w·required` | Exact, explainable, no training data needed |
| Role matching | TF-IDF + cosine similarity over role skill profiles, plus the employee's match | Finds related roles beyond the stated goal |
| Recommendations | Hybrid score: gap coverage 0.50, level fit 0.20, prerequisites ready 0.15, completion probability 0.15 | Each part is a question a user can check |
| Completion model | Logistic Regression vs Random Forest (5-fold CV); Logistic Regression won (CV ROC AUC 0.637); 11 leakage-free features | Simple, stable, explainable with few rows |
| Retraining | Validate → train → evaluate → compare with the current model on the same rows → quality gate → register → promote only if approved; MLflow | A worse model can never silently replace a better one |
| RAG | Chunking (≈800 characters), embeddings (Ollama `nomic-embed-text` or TF-IDF), FAISS/NumPy vector store, citations | Answers grounded in approved documents |
| LLM | Provider interface: local Ollama, hosted OpenAI-compatible service, or labelled fallback | Works on every machine; never pretends a fallback is AI |

## 7. Technology stack

| Need | Used | Alternatives considered |
| --- | --- | --- |
| Language | Python 3.11 | – (the AI/ML ecosystem) |
| API | FastAPI + Pydantic | Flask (no validation/docs built in), Django (too heavy) |
| Data | pandas; SQLite (stdlib) | MySQL planned for LMS integration (`MYSQL_CONFIGURATION_GUIDE.md`) |
| ML | scikit-learn, joblib, MLflow | XGBoost (overfits 354 training rows) |
| Vector search | FAISS (NumPy fallback) | Chroma, pgvector (extra services) |
| LLM | Ollama (local), OpenAI-compatible adapter | Cloud-only APIs (data would leave the machine) |
| Dashboard | Streamlit | React (more code for the same result) |
| Containers | Docker, Docker Compose | – |
| Orchestration | Kubernetes (Minikube) | Docker Swarm (less common) |
| CI/CD | GitHub Actions + Jenkins | GitLab CI |
| Security scanning | Snyk + Dependabot | Trivy |
| Public hosting | Streamlit Community Cloud + Render (free) | Hugging Face Spaces (Docker Spaces need PRO since 2026), Railway (credit too small) |

## 8. Security and privacy

Synthetic data only. Login with roles (employee: self; manager: their team; admin: everyone), JWT tokens, PBKDF2 password hashes, admin-only retraining and uploads, rate limiting, audit log, prompt-injection protection, upload content checks, security headers, and secrets kept only in environment variables and secret stores. Containers run non-root with a read-only filesystem and no Linux capabilities. Snyk scans dependencies and images on every pipeline run. Details: `SECURITY_GUIDE.md`, `SNYK_SECURITY_GUIDE.md`.

## 9. How it was built (22 phases)

| Phases | Delivered |
| --- | --- |
| 1–4 | Project skeleton, synthetic data, validation, cleaning and EDA |
| 5–7 | APIs 1–3: skills gap, role matching, recommendations |
| 8–10 | Completion model, SQLite database, API 4 learning path |
| 11–13 | Ollama LLM, document search (RAG), API 5 assistant and API 7 ingestion |
| 14–16 | Integration/contract tests, Streamlit dashboard, API 6 retraining with MLflow |
| 17–18 | Security; hardened Docker and Docker Compose |
| 19 | Public demo (Streamlit Community Cloud + Render) |
| 20–21 | Kubernetes (Minikube); Jenkins CI/CD and Snyk |
| 22 | Final documentation and live demo walkthrough |

## 10. Quality and acceptance

The 23 public-demo acceptance criteria, each with its evidence: [`ACCEPTANCE_CHECKLIST.md`](ACCEPTANCE_CHECKLIST.md). Quality evidence includes about 660 automated tests, the API contract snapshot, the smoke test against every deployment, and green CI on every merge.

## 11. Risks and how they are handled

| Risk | Mitigation |
| --- | --- |
| Small synthetic dataset makes ML metrics unrealistic | Metrics are presented as a demonstration of the method; the quality gate and baseline comparison are the real value |
| LLM unavailable or slow | Provider interface with a clearly labelled fallback; the API never depends on the LLM |
| LLM inventing facts | Answers built from LMS facts and cited passages; grounding warnings; refusal when nothing relevant is found |
| Free hosting limits | Slim installs; start step rebuilds data on restart; documented sleep behaviour |
| Vulnerable dependencies | Snyk in Jenkins and GitHub, Dependabot, documented acceptances with expiry |

## 12. Future work

- Integration with the existing PHP/F3/Vue LMS: the LMS calls the seven APIs with its own login token.
- MySQL for multi-instance production; Redis for cluster-wide rate limits.
- Real data, with privacy review, a larger training set, and model monitoring for drift.
- Multi-tenant deployment (one index and dataset per customer: the design already separates tenants).
- Better embeddings and a hosted LLM agreed with the data-protection officer.
