# Architecture

How the LMS Skills Intelligence Engine is built and deployed. GitHub renders the diagrams below (Mermaid).

---

## 1. System context

```mermaid
flowchart LR
    subgraph Users
        V[Visitor / employee / manager]
        A[Administrator]
        L[Enterprise LMS<br/>PHP/F3/Vue, future]
    end
    subgraph Engine["LMS Skills Intelligence Engine"]
        D[Streamlit dashboard]
        API[FastAPI service<br/>7 APIs + Swagger]
    end
    subgraph AI["Language model (optional)"]
        O[Ollama, local]
        H[Hosted OpenAI-compatible service]
    end
    V -->|browser| D
    V -->|REST / Swagger| API
    A -->|admin login or X-Admin-Key| D & API
    L -.->|REST + token| API
    D & API -->|prompts with redacted facts| O & H
```

The dashboard and the API use the **same services** in the same code base, so they always show the same numbers. The language model is optional: without one, a clearly labelled fallback answers.

## 2. Layers inside the code

```mermaid
flowchart TB
    subgraph Presentation
        R["app/api/v1/*<br/>routers: skills, roles, trainings, learning_path,<br/>ai_chat, ml_training, rag, auth, admin, health"]
        UI["dashboard/<br/>Home + 8 pages"]
    end
    subgraph Cross["Cross-cutting"]
        SEC["app/security/<br/>login, roles, rate limits, audit, injection, uploads"]
        CFG["app/core/<br/>settings, errors, logging, start step"]
    end
    subgraph Services["app/services/"]
        S1[SkillAnalysis] --- S2[RoleMatching] --- S3[TrainingRecommendation] --- S4[LearningPath]
        S5[Chat] --- S6[Ingestion] --- S7[Explanation]
    end
    subgraph Engines
        ML["app/ml/<br/>features, train, evaluate,<br/>registry, retraining, MLflow"]
        RAG["app/rag/<br/>loader, chunking, embeddings,<br/>vector store, index"]
        LLM["app/llm/<br/>Ollama · hosted · fallback,<br/>prompts, guardrails"]
    end
    subgraph Data
        REPO["app/repositories/<br/>CSV or SQLite (same interface)"]
        DOM["app/domain/models.py"]
    end
    R & UI --> SEC --> Services
    Services --> ML & RAG & LLM
    Services --> REPO --> DOM
    CFG -.-> R & UI & Services
```

| Layer | Rule |
| --- | --- |
| Routers / pages | Validate input (Pydantic), check access, call one service, shape the response. No business logic |
| Services | All business logic; testable without HTTP |
| Repositories | The only code that knows where data lives: CSV files or SQLite, chosen by `DATA_SOURCE`. MySQL would be one more repository |
| Engines | ML, RAG and LLM behind small interfaces, so each can be replaced (e.g. another LLM provider) |

## 3. The seven APIs and what they use

| # | Endpoint | Service | Uses |
| --- | --- | --- | --- |
| 1 | `POST /api/v1/skills/analyze` | SkillAnalysis | employee skills, role requirements |
| 2 | `POST /api/v1/roles/match` | RoleMatching | TF-IDF role profiles + API 1 logic |
| 3 | `POST /api/v1/trainings/recommend` | TrainingRecommendation | API 1 gaps, course skills, prerequisites, completion model |
| 4 | `GET /api/v1/learning-path/{id}` | LearningPath | API 3 scores, prerequisite order; optional LLM explanation |
| 5 | `POST /api/v1/ai/chat` | Chat | APIs 1–4 facts, RAG index, LLM |
| 6 | `POST /api/v1/ml/retrain` | RetrainingService | data validation, training, quality gate, registry, MLflow |
| 7 | `POST /api/v1/rag/ingest` | Ingestion | loader, chunking, embeddings, vector store |

Supporting endpoints: health (`/health`, `/health/llm`, `/health/rag`), login (`/auth/token`, `/auth/me`), model status (`/ml/status`), documents (`GET/DELETE /rag/documents`), demo reset (`/admin/reset-demo`).

## 4. Request flow: a recommendation (API 3)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant M as Middleware
    participant R as Router
    participant S as Security
    participant T as TrainingRecommendation
    participant K as SkillAnalysis
    participant P as Completion model
    C->>M: POST /api/v1/trainings/recommend {"employee_id": "E1001"}
    M->>M: request ID, rate limit, timing
    M->>R: forward
    R->>S: who is calling? may they see E1001?
    S-->>R: allowed (own data / team / admin / guest)
    R->>T: recommend(E1001)
    T->>K: gaps toward the career goal
    K-->>T: SQL 2→4, Python 2→4, AWS 0→4 ...
    T->>P: probability of completing each candidate course
    P-->>T: C-SQL-201 0.59, C-AWS-101 0.80 ...
    T-->>R: ranked courses with score parts and reasons
    R-->>M: JSON (Pydantic schema)
    M-->>C: 200 + X-Request-ID + security headers, audit log line
```

## 5. AI assistant: RAG and guardrails (API 5)

```mermaid
flowchart LR
    Q[Question] --> INJ{Prompt-injection<br/>pattern?}
    INJ -->|yes| REF[Fixed refusal<br/>no model call]
    INJ -->|no| INT[Intent detection]
    INT --> FACTS[LMS facts:<br/>gaps, path, roles, courses]
    INT --> SEARCH[Search the index<br/>min score + relative cut-off]
    SEARCH --> CLEAN[Remove instruction-like<br/>sentences from passages]
    FACTS & CLEAN --> PROMPT[System rules + redacted facts<br/>+ cited passages S1..Sn]
    PROMPT --> LLM{LLM available?}
    LLM -->|yes| ANS[Answer with citations]
    LLM -->|no| FB[Labelled fallback:<br/>facts + passages]
    ANS --> CHECK[Grounding check<br/>+ system-prompt leak check]
    CHECK & FB --> OUT[Answer, sources, facts,<br/>warnings, provider]
```

**Indexing (API 7 / start step):** documents (`.md .txt .pdf .docx .csv`) → text extraction → about 800-character chunks with 120 overlap and section paths → embeddings (Ollama `nomic-embed-text`, or TF-IDF) → FAISS (or NumPy) → swapped into place atomically, with `manifest.json`. Base documents are read-only; uploads are checked (type, size, content matches extension, no hidden instructions).

## 6. Machine learning lifecycle (API 6)

```mermaid
flowchart LR
    DATA[Training history] --> VAL[Validate data]
    VAL -->|errors| STOP1[Rejected: invalid data]
    VAL --> FEAT[11 leakage-free features]
    FEAT --> CV[Compare models<br/>5-fold CV]
    CV --> FIT[Fit the best]
    FIT --> EVAL[Evaluate on unseen rows]
    EVAL --> CMP[Compare with the current model<br/>on the SAME rows]
    CMP --> GATE{Quality gate:<br/>ROC AUC ≥ 0.60,<br/>> chance, no regression}
    GATE -->|fail| REG1[Register as rejected<br/>current model stays]
    GATE -->|pass| REG2[Register + promote]
    REG1 & REG2 --> TRACK[MLflow run, model card,<br/>retraining history]
```

The current model version is read per request, so a promotion or rollback (dashboard or API) is used at once, even by other replicas on Kubernetes.

## 7. Data model

```mermaid
erDiagram
    EMPLOYEES ||--o{ EMPLOYEE_SKILLS : has
    EMPLOYEES ||--o| CAREER_GOALS : targets
    EMPLOYEES ||--o{ TRAINING_HISTORY : enrols
    EMPLOYEES }o--|| JOB_ROLES : "current role"
    EMPLOYEES }o--o| EMPLOYEES : "manager_id"
    JOB_ROLES ||--o{ ROLE_REQUIRED_SKILLS : requires
    SKILLS ||--o{ EMPLOYEE_SKILLS : ""
    SKILLS ||--o{ ROLE_REQUIRED_SKILLS : ""
    SKILLS ||--o{ COURSE_SKILLS : ""
    COURSES ||--o{ COURSE_SKILLS : teaches
    COURSES ||--o{ COURSE_PREREQUISITES : needs
    COURSES ||--o{ TRAINING_HISTORY : ""
    CAREER_GOALS }o--|| JOB_ROLES : ""
```

Eleven datasets, synthetic: 100 employees, 42 skills, 13 job roles, 80 courses, 925 employee skills, 554 training records. Columns and rules: `DATA_DICTIONARY.md`.

## 8. Security layers

```mermaid
flowchart LR
    REQ[Request] --> H[Security headers,<br/>CORS, request ID]
    H --> RL[Rate limits<br/>API · chat · admin · login]
    RL --> AUTH[Login: JWT HS256<br/>or guest / admin key]
    AUTH --> ACC[Access rules:<br/>self · team · everyone]
    ACC --> VALID[Input validation<br/>Pydantic, upload checks]
    VALID --> SVC[Service]
    SVC --> AUD[Audit log<br/>no bodies, no secrets]
```

Plus: PBKDF2 password hashes, tenant check, prompt-injection protection, start-up refusal of unsafe settings, non-root read-only containers, Snyk scans. Details: `SECURITY_GUIDE.md`.

## 9. Deployment views

```mermaid
flowchart TB
    subgraph Local["Your PC"]
        PY[uvicorn + streamlit<br/>from the venv]
        OL[(Ollama)]
        subgraph Compose["Docker Compose"]
            CA[api] --- CD[dashboard]
            CM[mlflow, optional] --- CO[ollama, optional]
            VOL[(7 named volumes)]
        end
        subgraph K8s["Minikube"]
            PA[lms-api × 2–4<br/>HPA] --- PD[lms-dashboard]
            PV[(PV + PVC)]
        end
        subgraph CI["Jenkins container"]
            J[11-stage pipeline] --> DEV[lms-dev-api<br/>:18001]
        end
    end
    subgraph Cloud["Public, free tiers"]
        SC[Streamlit Community Cloud<br/>dashboard]
        RD[Render<br/>API + Swagger]
    end
    GH[GitHub repository<br/>Actions: lint · tests · Docker · Snyk] -->|push to main| SC & RD
```

| Environment | How it runs | Data | Guide |
| --- | --- | --- | --- |
| Local | `uvicorn app.main:app` + `streamlit run dashboard/Home.py` | CSV files, local index and models | `README.md` |
| Docker Compose | Hardened image, start step, 7 volumes | SQLite + index + models on volumes | `DOCKER_GUIDE.md` |
| Kubernetes | 2–4 API replicas, dashboard, PV/PVC, probes, limits | shared persistent volume | `KUBERNETES_GUIDE.md` |
| Jenkins | Build, test, scan, deploy `lms-dev-api`, smoke test | dev volumes | `JENKINS_CICD_GUIDE.md` |
| Public | Streamlit Community Cloud + Render, guest access | rebuilt from the repository at each start | `PUBLIC_DEPLOYMENT_GUIDE.md` |

## 10. Key design decisions

| Decision | Reason |
| --- | --- |
| Rules + ML hybrid for recommendations | Every score part is explainable; ML adds only what must be learned (completion) |
| One code base for API and dashboard | Same numbers everywhere; less code |
| Repository interface (CSV / SQLite) | The data source changes without touching services; ready for the LMS database |
| LLM behind a provider interface with a fallback | Works without a GPU; never pretends a fallback is AI |
| Start step (`app/core/prepare.py`) | Empty volumes or fresh hosts become a working system automatically; locked for multiple pods |
| Quality gate before promotion | A worse model can never silently replace a better one |
| Synthetic data only | Safe public demo; no personal data |
