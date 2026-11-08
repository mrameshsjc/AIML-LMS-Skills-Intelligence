# Public Deployment Guide (Phase 19)

How to put the LMS Skills Intelligence Engine on the internet as a **free public demo** that anyone can use in a browser. Visitors install nothing: no Python, no Docker, no Ollama. All data is **synthetic**.

> **Status:** this guide and the code are ready. The public URLs exist only after you complete section 4. Until the demo has been deployed **and** checked with section 6, do not list it as deployed.

---

## 1. The recommendation

**Dashboard on Streamlit Community Cloud + API on a Render free web service. Both are free and both deploy straight from the GitHub repository:**

```
 Visitor's browser
   │
   ├── https://<app-name>.streamlit.app               Streamlit dashboard   ← PUBLIC DASHBOARD URL
   │        Streamlit Community Cloud, from GitHub (branch main), dashboard/Home.py
   │        guest access, admin login, its own copy of the data, index and model
   │
   └── https://lms-skills-api.onrender.com            FastAPI               ← API BASE URL (/api/v1)
            /docs  Swagger UI                                               ← SWAGGER URL
            Render free web service, from GitHub (render.yaml), API-only install

 Optional, outside both: an OpenAI-compatible hosted LLM (LLM_PROVIDER=hosted).
 Without it, the assistant answers in a clearly labelled fallback mode.
```

**Why two hosts:** the requirements say "Do not assume one hosting provider can run every service". Streamlit Community Cloud runs only Streamlit apps, so it can't run FastAPI. Render runs FastAPI, but its free tier is too small for the dashboard as well. The dashboard calls the engine's services directly, so it doesn't depend on the API being awake.

**Why no LLM on either host:** free tiers have no GPU, and Ollama with a useful model doesn't fit in their memory. As the requirements say, the LLM is separated from the application. It is reached through the configurable provider interface and is optional (section 7).

**Bonus:** both hosts **redeploy automatically** when you push to `main`, so the demo always shows the latest merged code.

## 2. Hosting options evaluated

Facts checked in November 2026; free tiers change often, so check them again before relying on them.

| Criterion | Streamlit Community Cloud | Render | Hugging Face Spaces | Railway |
| --- | --- | --- | --- | --- |
| Python | ✅ | ✅ | ✅ | ✅ |
| FastAPI | ❌ Streamlit apps only | ✅ | ✅ (Docker Space) | ✅ |
| Streamlit | ✅ (its purpose) | ✅ | ✅ | ✅ |
| Free for our case | ✅ | ✅ (web service) | ❌ **Docker and Gradio Spaces now need PRO**; only static pages are free | ⚠️ $1/month credit |
| CPU / RAM (free) | about 0.08–2 cores / 0.7–2.7 GB | 0.1 CPU / 512 MB | – (paid) | 1 vCPU / 0.5 GB |
| Persistent storage (free) | ❌ | ❌ | – | volumes, inside the small credit |
| GPU | ❌ | ❌ | paid | ❌ |
| Sleep when idle | after 12 h without traffic | after 15 min; about 1 min to wake | – | while credit lasts |
| LLM hosting on free tier | ❌ | ❌ | ❌ | ❌ |
| Deploys from GitHub | ✅ auto on push | ✅ auto on push (`render.yaml`) | upload or Git push | ✅ |
| Public URL | `https://<app>.streamlit.app` | `https://<name>.onrender.com` | `https://<user>-<space>.hf.space` | `https://<name>.up.railway.app` |
| Role here | **Dashboard** | **API + Swagger** | Only with a PRO plan (`scripts/prepare_hf_space.py` is kept for that case) | Not used: credit too small |

**Other options considered:**
- **Oracle Cloud Always Free VM** (2 Arm CPUs / 12 GB since June 2026): always on and could run everything with Docker Compose. But it needs a credit card, idle VMs can be reclaimed, and you run the server yourself.
- **Cloudflare Tunnel from your PC**: a temporary link for a live presentation, only while your PC runs.

## 3. What the public demo runs

| Setting | Value | Why |
| --- | --- | --- |
| `APP_PROFILE` | `public-demo` | The engine refuses to start without login and a strong secret |
| `AUTH_ENABLED` + `GUEST_ACCESS` | `true` + `true` | Visitors browse the synthetic data read-only without an account; admin actions need an admin login |
| `PREPARE_TRAIN_MODEL` | `true` | A first model is trained at start, so model metrics are visible |
| `PREPARE_IN_DASHBOARD` | `true` (dashboard only) | Streamlit Cloud has no start command: the dashboard runs the start step once itself |
| `EMBEDDING_PROVIDER` / `VECTOR_BACKEND` | `tfidf` / `numpy` | No Ollama and no FAISS on the free hosts; search still works |
| `LLM_PROVIDER` | `fallback` | Labelled fallback answers; switch to `hosted` in section 7 |
| Rate limits | API 60/min, assistant 10/min, admin 10/hour | Stricter limits for the public |
| `RAG_MAX_UPLOAD_MB` | 2 | Small uploads only (admins) |
| Install | `dashboard/requirements.txt` / `requirements-api.txt` | Slim lists without MLflow, FAISS and the other side's server, to fit the free memory |

**Secrets** (never in Git; entered in each host's settings):

| Secret | What |
| --- | --- |
| `AUTH_SECRET_KEY` | Signs login tokens. Streamlit: you generate it. Render: generated for you |
| `BOOTSTRAP_ADMIN_PASSWORD` | The private password of the `admin` account, recreated at every start (12+ characters) |
| `HOSTED_LLM_API_KEY` | Only for section 7 |

Generate values on your PC:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"   # AUTH_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(16))"   # BOOTSTRAP_ADMIN_PASSWORD (keep it private)
```

## 4. Deploy, step by step

**First:** merge Phase 19 into `development`, then `development` into **`main`** (pull request on GitHub, green CI). Both hosts deploy from `main`.

### 4A. Dashboard on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and click **Continue with GitHub**. Allow Streamlit to see your repositories.
2. Click **Create app** → **Deploy a public app from GitHub** (or "Yup, I have an app").
3. Fill in:
   - **Repository:** `mrameshsjc/AIML-LMS-Skills-Intelligence`
   - **Branch:** `main`
   - **Main file path:** `dashboard/Home.py`
   - **App URL:** choose a name, e.g. `lms-skills-intelligence` → `https://lms-skills-intelligence.streamlit.app`
4. Open **Advanced settings**:
   - **Python version:** `3.11` (the version CI tests with)
   - **Secrets:** paste the contents of `deployment/cloud/streamlit/secrets.toml.example` and replace the two placeholder values with your generated secrets.
5. Click **Deploy**. The first start installs the libraries (several minutes), then shows "First start: building the database, the document index and a first model …" for about half a minute. After that the dashboard appears.

Later changes: *your app → ⋮ → Settings → Secrets* (the app restarts by itself). *Reboot app* also gives a fresh start.

### 4B. API + Swagger on Render

1. Go to **https://render.com** and sign up with **GitHub**.
2. Click **New +** → **Blueprint** → connect the repository `mrameshsjc/AIML-LMS-Skills-Intelligence`.
3. Render reads `render.yaml` and shows the service **`lms-skills-api`** (free plan). It asks for **`BOOTSTRAP_ADMIN_PASSWORD`**: paste your admin password. `AUTH_SECRET_KEY` is generated automatically.
4. Click **Apply** (or **Deploy Blueprint**). Watch the service's **Logs**: first `pip install -r requirements-api.txt`, then the start step:
   ```
   prepare | Document index: built: 8 documents, 132 chunks (tfidf/numpy). ...
   prepare | Admin account: created admin (password from BOOTSTRAP_ADMIN_PASSWORD)
   prepare | Model: promoted: version 1, test ROC AUC 0.693
   ```
   then `Uvicorn running`. The status turns **Live**.
5. Your API is at `https://lms-skills-api.onrender.com` (Render shows the exact address at the top; a suffix is added if the name is taken). Swagger UI is at `/docs`.

If the name `lms-skills-api` is taken, Render adds a suffix to the address; use the address it shows.

### 4C. If something does not start

| Where | Message | Fix |
| --- | --- | --- |
| Streamlit | "Unsafe settings - the dashboard will not run: AUTH_SECRET_KEY …" | Secrets missing or too short: *Settings → Secrets*, then *Reboot app* |
| Streamlit | `ModuleNotFoundError` | The app must use `dashboard/requirements.txt`; check the main file path is `dashboard/Home.py`, then *Reboot app* |
| Streamlit | "Error installing requirements" | Choose Python 3.11 (*Settings*, or delete and redeploy the app with Advanced settings) |
| Render | `RuntimeError: Unsafe security settings: BOOTSTRAP_ADMIN_PASSWORD must have at least 12 characters` | *Environment* tab → fix the value → *Manual Deploy* |
| Render | `Ran out of memory (used over 512MB)` | Settings → *Environment*: set `PREPARE_TRAIN_MODEL=false` (no first model), redeploy |
| Render | First request takes about a minute | The free service was asleep after 15 minutes without traffic; normal |

## 5. Data on free hosts: reset on restart (by design)

Neither free host keeps files after a restart or redeploy. The start step (`app/core/prepare.py`) rebuilds what the demo needs: the document index, the admin account and a first model. It runs in well under a minute.

| What happens to | On restart | Kept? |
| --- | --- | --- |
| Synthetic data, documents, first model | rebuilt from the repository | ✅ always present |
| Uploaded documents, retrained models | gone | ❌ |
| Admin account | recreated from the secret | ✅ |
| Audit log | gone | ❌ (an external log service would keep it) |

**Reset mechanism** (requirement "Provide a reset mechanism for demo data"):
- **Dashboard:** log in as admin (sidebar) → *Model management* → *Reset the demo*.
- **API:** `POST /api/v1/admin/reset-demo` as admin (Swagger: *8. Demo administration*).
- **Hosts:** Streamlit *Reboot app*; Render *Manual Deploy → Restart service*.
- **Locally / Docker:** `python -m app.core.prepare --reset`.

## 6. Verify the deployment (before you call it deployed)

```powershell
# API: every endpoint over real HTTP, as a guest (no account). --wait covers Render waking up.
python scripts/api_smoke_test.py --base-url https://lms-skills-api.onrender.com --wait 120 --skip-upload
# and as the administrator (includes the API 7 upload check)
python scripts/api_smoke_test.py --base-url https://lms-skills-api.onrender.com --username admin --password <BOOTSTRAP_ADMIN_PASSWORD>
```

Then in a **private browser window** (no cookies, like a real visitor):

- [ ] Dashboard opens without login; the sidebar says "Guest: read-only demo"
- [ ] E1001 → Skills analysis shows gap score 37.5 for Data Engineer
- [ ] Role matching, Recommendations (C-SQL-201 first) and Learning path work
- [ ] AI assistant answers "How many learning hours do I have per year?" with sources and the **Fallback mode** note
- [ ] Documents page lists 8 documents; the upload area says "Administrators only"
- [ ] Model management shows the metrics; retraining and reset say "Administrators only"
- [ ] `https://lms-skills-api.onrender.com/docs` opens Swagger UI; `POST /api/v1/skills/analyze` with `{"employee_id": "E1001", "target_role_id": "R004"}` returns 200
- [ ] `POST /api/v1/ml/retrain` without login returns **401**
- [ ] Admin login in the dashboard sidebar works; the reset works

Take the **screenshots** for the submission during this check: dashboard home, skills analysis, learning path, assistant with sources, model metrics, Swagger UI.

## 7. Optional: a hosted LLM instead of the fallback

The engine talks to any service with an **OpenAI-compatible** `/chat/completions` endpoint (`app/llm/hosted_provider.py`). It must be configured explicitly, and prompts then leave the host. That's acceptable here only because the demo data is synthetic.

Add to the Streamlit secrets and/or the Render environment:

| Name | Value |
| --- | --- |
| `LLM_PROVIDER` | `hosted` |
| `LLM_ALLOW_REMOTE` | `true` (required approval; the engine refuses `hosted` without it) |
| `HOSTED_LLM_BASE_URL` | the service's OpenAI-compatible URL, e.g. `https://router.huggingface.co/v1` |
| `HOSTED_LLM_MODEL` | a chat model the service offers |
| `HOSTED_LLM_API_KEY` | the service's token (a **secret**) |

**Cost:** Hugging Face Inference Providers currently include monthly credits only for PRO accounts ($2/month). Some other providers have free tiers with daily limits; check their terms. When the quota runs out or the service fails, answers switch to the labelled fallback automatically, with the reason in the answer's notes. Locally, keep using Ollama (`LLM_PROVIDER=auto`).

## 8. Security of the public demo

| Requirement | How it is met |
| --- | --- |
| Never expose database credentials / API tokens; never commit `.env` | SQLite/CSV have no credentials; tokens and passwords are host **secrets**; `.env` and `.streamlit/secrets.toml` are git-ignored; settings are `SecretStr` |
| Protect admin operations | Upload, delete, retrain, rollback and reset need an admin login (or `X-Admin-Key`); guests get 401 or "Administrators only" |
| Prevent public users from triggering expensive retraining | Retraining is admin-only and limited to 10 admin actions per hour per IP |
| Restrict document uploads; file size limits; no executables | Admin-only, 2 MB in the demo, extension allow-list, content must match the extension, prompt-injection check |
| Rate limiting | API 60/min, assistant 10/min per visitor (per browser session in the dashboard), admin 10/hour, login 10/min |
| Avoid storing sensitive user information | Guests are not identified; the audit log keeps request metadata only and is wiped on restart |
| Only synthetic demo data | The repository contains only `data/sample` and the sample documents |
| Clear message when AI inference is unavailable; never pretend a fallback came from an LLM | The assistant shows "Fallback mode - no language model…"; API answers carry `provider: "fallback"` and `is_fallback: true` |
| Demo credentials without exposing admin credentials | Visitors need **no** credentials (guest access); the admin password exists only as a host secret: never publish it |

## 9. Updating the demo

Merge into `main`: both hosts redeploy automatically. To restart without a code change: Streamlit *Reboot app*; Render *Manual Deploy*.

## 10. Final public deliverables

Fill this table in **after** section 6 passes:

| Deliverable | Value |
| --- | --- |
| GitHub repository | https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence |
| Public dashboard URL | `https://<app-name>.streamlit.app` *(after deployment)* |
| API base URL | `https://lms-skills-api.onrender.com/api/v1` *(after deployment)* |
| Swagger URL | `https://lms-skills-api.onrender.com/docs` *(after deployment)* |
| Demo credentials | None needed: guest access. The admin login is private |
| Deployment documentation | this guide, `docs/DOCKER_GUIDE.md`, `docs/SECURITY_GUIDE.md` |
| Screenshots | taken during section 6 (Phase 22 adds them to the README) |

## 11. Demo walkthrough (for visitors, about 5 minutes)

1. **Open the dashboard.** The home page shows the totals: 100 employees, 13 roles, the completion rate, the most common skill gaps.
2. **Skills analysis:** keep **E1001** (Arjun, Software Developer) and the target **Data Engineer**: gap score 37.5, match 62.5 %, missing and below-level skills.
3. **Role matching:** which roles E1001 is closest to, and what is missing for each.
4. **Recommendations:** courses ranked by an explainable score. Each course has a reason, prerequisites, and the predicted chance of completion from the ML model.
5. **Learning path:** C-SQL-201 first; the projected match rises to 100 %.
6. **AI assistant:** ask "What are my current skill gaps?" (answers from E1001's data) and "How many learning hours do I have per year?" (answers from the learning policy, with the source passage shown).
7. **Documents:** the 8 indexed documents the assistant can cite.
8. **Model management:** the completion model's test ROC AUC and accuracy against a baseline, the algorithm comparison and feature importance. The data is synthetic, so the metrics show the method, not real-world accuracy.
9. **Swagger** (`/docs` on the API): try the same analysis as JSON.

## 12. Known limitations

- **Free hosting:** the API sleeps after 15 minutes (first request about a minute); the dashboard sleeps after 12 hours. Both forget uploads and retrained models on restart.
- **No LLM by default:** the public assistant uses the labelled fallback unless a hosted LLM is configured (section 7). Ollama runs only locally or in Docker Compose.
- **TF-IDF search** in the demo matches words, not meaning (no embedding model on the free hosts).
- **Rate limits are approximate:** behind the hosts' proxies the visitor's address comes from a forwarded header that a determined user can change, and the limits are in memory, per process.
- **Two separate copies:** the dashboard and the API have their own data; an upload in one does not appear in the other.
- **Synthetic data only:** the metrics demonstrate the method, not real-world accuracy.
- **Hugging Face Spaces:** prepared (`scripts/prepare_hf_space.py`), but Docker Spaces need a PRO plan since 2026.
