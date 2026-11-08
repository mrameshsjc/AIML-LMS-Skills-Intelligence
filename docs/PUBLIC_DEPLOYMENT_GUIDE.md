# Public Deployment Guide (Phase 19)

How to put the LMS Skills Intelligence Engine on the internet as a **free public demo** that anyone can use in a browser. Visitors install nothing: no Python, no Docker, no Ollama. All data is **synthetic**.

> **Status:** this guide and the code are ready. The public URLs exist only after you complete section 4. Until the demo has been deployed **and** checked with section 6, do not list it as deployed.

---

## 1. The recommendation

**Two Hugging Face Spaces (free "CPU basic"), built from this repository's Dockerfile, plus an optional hosted LLM:**

```
 Visitor's browser
   │
   ├── https://<user>-lms-skills-dashboard.hf.space   Streamlit dashboard  ← PUBLIC DASHBOARD URL
   │        (Space 1: own copy of the engine, guest access, admin login)
   │
   └── https://<user>-lms-skills-api.hf.space         FastAPI             ← API BASE URL
            /docs  Swagger UI                                             ← SWAGGER URL
            (Space 2: own copy of the engine, guest access, admin login)

 Optional, outside both Spaces: an OpenAI-compatible hosted LLM (LLM_PROVIDER=hosted).
 Without it, the assistant answers in a clearly labelled fallback mode.
```

Why two Spaces: a Space exposes **one** port, and the requirements say "Do not assume one hosting provider can run every service". Each Space runs the same image with a different command. The dashboard calls the engine's services directly, so it does not need the API Space to be awake.

Why no LLM inside a Space: a free Space has no GPU, and Ollama with a useful model on 2 CPUs would answer in tens of seconds or run out of memory. As the requirements say, the LLM is separated from the application. It is reached through the configurable provider interface and is optional.

## 2. Hosting options evaluated

Facts checked in November 2026; free tiers change, so check them again before relying on them.

| Criterion | Hugging Face Spaces | Streamlit Community Cloud | Render | Railway |
| --- | --- | --- | --- | --- |
| Python | ✅ | ✅ | ✅ | ✅ |
| FastAPI | ✅ (Docker Space) | ❌ Streamlit apps only | ✅ | ✅ |
| Streamlit | ✅ | ✅ (its purpose) | ✅ | ✅ |
| Runs our Dockerfile | ✅ | ❌ | ✅ | ✅ |
| CPU / RAM (free) | **2 vCPU / 16 GB** | about 0.08–2 cores / 0.7–2.7 GB | 0.1 CPU / 512 MB | Free plan: 1 vCPU / 0.5 GB |
| Persistent storage (free) | ❌ resets on restart (paid buckets) | ❌ | ❌ | volumes, inside the small credit |
| GPU | paid hardware only | ❌ | ❌ | ❌ |
| Sleep when idle | yes, wakes on visit | after 12 h without traffic | after 15 min; about 1 min to wake | runs while credit lasts |
| LLM hosting on free tier | ❌ (no GPU); hosted inference separately | ❌ | ❌ | ❌ |
| Cost | free (CPU basic), no card | free | free tier; paid bandwidth reduced Aug 2026 | $1/month free credit, $5 trial; Hobby $5/month |
| Public URL | `https://<user>-<space>.hf.space`, instant | `https://<app>.streamlit.app` | `https://<name>.onrender.com` | `https://<name>.up.railway.app` |
| Fits this project? | **Yes**: memory for pandas, scikit-learn, FAISS, the index and the model | Dashboard only; too little memory is likely | 512 MB is too small | 0.5 GB is too small on the free plan |

**Other options considered:**
- **Oracle Cloud Always Free VM** (2 Arm CPUs / 12 GB since June 2026): always on and runs Docker Compose with everything, even a small Ollama model. But it needs a credit card, idle VMs can be reclaimed, and you run the server yourself.
- **Cloudflare Tunnel from your PC**: a quick temporary link for a live presentation, only while your PC runs.

**Decision:** Hugging Face Spaces has the most memory on a free tier, runs our existing Dockerfile unchanged except for the user ID, and gives a shareable URL at once. Its weak point, a disk that resets on restart, is handled by the start step (section 5).

## 3. What the public demo runs

`scripts/prepare_hf_space.py` builds a Space folder with these defaults (`DEMO_ENV` in the script). Space **Variables** can override any of them:

| Setting | Demo value | Why |
| --- | --- | --- |
| `APP_PROFILE` | `public-demo` | The server refuses to start without login and a strong secret |
| `AUTH_ENABLED` | `true` | Admin actions need an admin login |
| `GUEST_ACCESS` | `true` | Visitors browse the synthetic data without an account (read-only) |
| `DATA_SOURCE` | `database` | The SQLite database is built from the sample on every start |
| `PREPARE_TRAIN_MODEL` | `true` | A first model is trained at start, so model metrics are visible |
| `EMBEDDING_PROVIDER` | `tfidf` | No Ollama on the Space; TF-IDF search needs no model |
| `LLM_PROVIDER` | `fallback` | Labelled fallback answers; switch to `hosted` in section 7 |
| `RATE_LIMIT_PER_MINUTE` / `_CHAT_` / `_ADMIN_PER_HOUR` | 60 / 10 / 10 | Stricter limits for the public |
| `RAG_MAX_UPLOAD_MB` | 2 | Small uploads only (admins) |
| `FRAME_ANCESTORS` | `https://huggingface.co` | Lets the Space page show Swagger UI in its frame |
| user ID | 1000 | Hugging Face runs every container as user 1000 |

**Secrets** (never in Git, never in the image; set in the Space settings):

| Secret | Required | What |
| --- | --- | --- |
| `AUTH_SECRET_KEY` | yes | Signs login tokens; `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `BOOTSTRAP_ADMIN_PASSWORD` | yes (to administer) | The `admin` account is created from it at every start (12+ characters) |
| `HOSTED_LLM_API_KEY` | only for section 7 | Token of the hosted LLM service |
| `ADMIN_API_KEY` | optional | Lets scripts call admin endpoints with `X-Admin-Key` |

## 4. Deploy, step by step (PowerShell)

### 4.1 One-time setup

1. Create a free account at https://huggingface.co (username below: `<user>`).
2. Create an access token with **write** permission: *Settings → Access Tokens → Create new token → Write*. Keep it private.
3. Create **two Spaces**: *New → Space*.
   - Name `lms-skills-dashboard`, SDK **Docker**, template **Blank**, hardware **CPU basic (free)**, visibility **Public**.
   - Name `lms-skills-api`, the same choices.
4. In **each** Space: *Settings → Variables and secrets → New secret*. Add `AUTH_SECRET_KEY` (a different value per Space is fine) and `BOOTSTRAP_ADMIN_PASSWORD`.
5. Install the Hugging Face command-line tool in your venv and log in:

```powershell
pip install huggingface_hub          # deployment tool only - not part of requirements.txt
hf auth login                         # paste the write token (older versions: huggingface-cli login)
```

### 4.2 Build and upload the two Spaces

From the project folder, on an up-to-date `development` or `main` branch:

```powershell
python scripts/prepare_hf_space.py dashboard --out ..\hf-lms-dashboard
python scripts/prepare_hf_space.py api --out ..\hf-lms-api

hf upload <user>/lms-skills-dashboard ..\hf-lms-dashboard . --repo-type space --commit-message "Deploy dashboard"
hf upload <user>/lms-skills-api ..\hf-lms-api . --repo-type space --commit-message "Deploy API"
```

`hf upload` sends the PDF and Word sample documents correctly; a plain `git push` would need Git LFS for them. Hugging Face then **builds the image**, which takes about 5–10 minutes the first time. Follow it on the Space page (*Logs → Build*, then *Container*).

The container log shows the start step:

```
prepare | Database: created and loaded from data/sample: 2014 rows in 11 tables
prepare | Document index: built: 8 documents, 132 chunks (tfidf/numpy). ...
prepare | Admin account: created admin (password from BOOTSTRAP_ADMIN_PASSWORD)
prepare | Model: promoted: version 1, test ROC AUC 0.693
```

### 4.3 If the Space does not start

| Log message | Fix |
| --- | --- |
| `Unsafe security settings: AUTH_SECRET_KEY must have at least 32 characters` | Add the `AUTH_SECRET_KEY` secret, then *Settings → Restart Space* |
| `BOOTSTRAP_ADMIN_PASSWORD must have at least 12 characters` | Use a longer password |
| `Permission denied` on `/app/...` | The Space Dockerfile must have `ARG APP_UID=1000`: regenerate it with the script |
| Build fails while installing requirements | Read the build log; usually a temporary download problem: *Factory rebuild* |
| Dashboard upload gives 403 inside the Space page | Open the direct `https://<user>-lms-skills-dashboard.hf.space` address (browser cookie rules in frames) |

## 5. Data on a free Space: reset on restart (by design)

A free Space's disk is **not persistent**: every restart, rebuild or wake-up starts from a clean disk. The start step (`app/core/prepare.py`) rebuilds what the demo needs: the database, the index, the admin account and a first model. That takes well under a minute.

| What happens to | On restart | Kept? |
| --- | --- | --- |
| Synthetic data, documents, first model | rebuilt from the image | ✅ always present |
| Uploaded documents, retrained models | gone | ❌ |
| Admin account | recreated from the secret | ✅ |
| Audit log | gone | ❌ (use a paid storage bucket or an external log service to keep it) |

**Reset mechanism** (requirement "Provide a reset mechanism for demo data"):
- **Dashboard:** log in as admin → *Model management* → *Reset the demo* (tick the box, click the button).
- **API:** `POST /api/v1/admin/reset-demo` as admin (Swagger: *8. Demo administration*).
- **Space:** *Settings → Restart Space*.
- **Locally / Docker:** `python -m app.core.prepare --reset`.

## 6. Verify the deployment (before you call it deployed)

```powershell
# API Space: every API over real HTTP, as a guest (no account)
python scripts/api_smoke_test.py --base-url https://<user>-lms-skills-api.hf.space --wait 120 --skip-upload
# and as the administrator (includes the API 7 upload check)
python scripts/api_smoke_test.py --base-url https://<user>-lms-skills-api.hf.space --username admin --password <BOOTSTRAP_ADMIN_PASSWORD>
```

Then in a **private browser window** (no cookies, like a real visitor):

- [ ] Dashboard opens without login; the sidebar says "Guest: read-only demo"
- [ ] E1001 → Skills analysis shows gap score 37.5 for Data Engineer
- [ ] Role matching, Recommendations (C-SQL-201 first) and Learning path work
- [ ] AI assistant answers "How many learning hours do I have per year?" with sources, and shows the **Fallback mode** note (or a hosted model's name)
- [ ] Documents page lists 8 documents; the upload area says "Administrators only"
- [ ] Model management shows the metrics; retraining and reset say "Administrators only"
- [ ] `https://<user>-lms-skills-api.hf.space/docs` opens Swagger UI; `POST /api/v1/skills/analyze` with `{"employee_id": "E1001", "target_role_id": "R004"}` returns 200
- [ ] `POST /api/v1/ml/retrain` without login returns **401**
- [ ] Admin login in the dashboard sidebar works; the reset works

Take the **screenshots** for the submission during this check: dashboard home, skills analysis, learning path, assistant with sources, model metrics, Swagger UI.

## 7. Optional: a hosted LLM instead of the fallback

The engine talks to any service with an **OpenAI-compatible** `/chat/completions` endpoint (`app/llm/hosted_provider.py`). It must be configured explicitly, and prompts then leave the Space. That's acceptable here only because the demo data is synthetic.

In the Space *Settings → Variables and secrets*:

| Name | Kind | Example |
| --- | --- | --- |
| `LLM_PROVIDER` | variable | `hosted` |
| `LLM_ALLOW_REMOTE` | variable | `true` (required approval; the server refuses `hosted` without it) |
| `HOSTED_LLM_BASE_URL` | variable | `https://router.huggingface.co/v1` (Hugging Face) or another provider's OpenAI-compatible URL |
| `HOSTED_LLM_MODEL` | variable | a chat model the service offers, e.g. `meta-llama/Llama-3.1-8B-Instruct` |
| `HOSTED_LLM_API_KEY` | **secret** | the service's token |

Then restart the Space. **Cost:** Hugging Face Inference Providers currently include monthly credits only for PRO accounts ($2/month); free accounts must buy credits. Some other providers have free tiers with daily limits; check their terms. When the quota runs out or the service fails, answers switch to the labelled fallback automatically, and the reason is in the answer's notes. Locally, keep using Ollama (`LLM_PROVIDER=auto`).

## 8. Security of the public demo

| Requirement | How it is met |
| --- | --- |
| Never expose database credentials / API tokens; never commit `.env` | SQLite has no credentials; tokens and passwords are Space **secrets**; `.env` is git-ignored and docker-ignored; settings are `SecretStr` |
| Protect admin operations | Upload, delete, retrain, rollback and reset need an admin login (or `X-Admin-Key`); guests get 401 or "Administrators only" |
| Prevent public users from triggering expensive retraining | Retraining is admin-only and limited to 10 admin actions per hour per IP |
| Restrict document uploads; file size limits; no executables | Admin-only, 2 MB in the demo, extension allow-list, content must match the extension, prompt-injection check |
| Rate limiting | API 60/min, assistant 10/min per visitor (per browser session in the dashboard), admin 10/hour, login 10/min |
| Avoid storing sensitive user information | Guests are not identified; the audit log keeps request metadata only and is wiped on restart |
| Only synthetic demo data | The image contains only `data/sample` and the sample documents |
| Clear message when AI inference is unavailable; never pretend a fallback came from an LLM | The assistant shows "Fallback mode - no language model…"; API answers carry `provider: "fallback"` and `is_fallback: true` |
| Demo credentials without exposing admin credentials | Visitors need **no** credentials (guest access). The admin password exists only as a Space secret: never publish it |

## 9. Updating the demo

After merging new work:

```powershell
git checkout main; git pull
python scripts/prepare_hf_space.py dashboard --out ..\hf-lms-dashboard
python scripts/prepare_hf_space.py api --out ..\hf-lms-api
hf upload <user>/lms-skills-dashboard ..\hf-lms-dashboard . --repo-type space --commit-message "Update"
hf upload <user>/lms-skills-api ..\hf-lms-api . --repo-type space --commit-message "Update"
```

Phase 21 (CI/CD) can run these steps automatically from GitHub Actions with the token stored as a GitHub secret.

## 10. Final public deliverables

Fill this table in **after** section 6 passes:

| Deliverable | Value |
| --- | --- |
| GitHub repository | https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence |
| Public dashboard URL | `https://<user>-lms-skills-dashboard.hf.space` *(after deployment)* |
| API base URL | `https://<user>-lms-skills-api.hf.space/api/v1` *(after deployment)* |
| Swagger URL | `https://<user>-lms-skills-api.hf.space/docs` *(after deployment)* |
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
9. **Swagger** (API Space `/docs`): try the same analysis as JSON.

## 12. Known limitations

- **Free hosting:** the Space sleeps when idle (the first visit waits for it to start) and forgets uploads and retrained models on restart.
- **No LLM by default:** the public assistant uses the labelled fallback unless a hosted LLM is configured (section 7). Ollama runs only locally or in Docker Compose.
- **TF-IDF search** in the demo matches words, not meaning (no embedding model on the Space).
- **Rate limits are approximate:** behind the Hugging Face proxy the visitor's address comes from the forwarded header, which a determined user can change. The limits are in memory, per Space.
- **Two separate copies:** the dashboard and API Spaces have their own data; an upload in one does not appear in the other.
- **Synthetic data only:** the metrics demonstrate the method, not real-world accuracy.
- **Dashboard uploads inside the huggingface.co page** may be blocked by browser cookie rules; use the direct `.hf.space` address.
