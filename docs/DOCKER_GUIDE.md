# Docker Guide (Phase 18)

How to build, run, stop, inspect and debug the LMS Skills Intelligence Engine in containers on Windows 11 with Docker Desktop. Every command is for **PowerShell**, run from the project folder.

| File | What it is |
| --- | --- |
| `Dockerfile` | The image recipe: two stages, non-root user 10001, start step, health check |
| `compose.yaml` | Runs the services together, with volumes, health checks and hardening |
| `.dockerignore` | What never goes into the image (secrets, Git, tests, generated data) |
| `deployment/docker/compose.prod.yaml` | Override for shared servers: login on, secret required |
| `app/core/prepare.py` | The start step: folders, database and document index on first start |

---

## 1. Docker in five words each

| Term | Meaning here |
| --- | --- |
| **Image** | The packaged app: Python 3.11, libraries, code, sample data. Built once, read-only |
| **Container** | A running copy of the image. Throw-away: delete it and start a new one any time |
| **Volume** | A folder Docker keeps **outside** the container: your database, index, uploads, models |
| **Compose** | Starts several containers, their network and volumes with one command |
| **Health check** | A small command Docker runs every 30 s; the container shows `healthy` or `unhealthy` |

Kubernetes (Phase 20) runs the same image on a cluster: it restarts, scales and spreads containers over machines. Docker Compose is for one computer.

## 2. Services

| Service | Port (this PC only) | Starts with | What |
| --- | --- | --- | --- |
| `api` | http://127.0.0.1:8000/docs | `docker compose up` | FastAPI, all seven APIs, Swagger UI |
| `dashboard` | http://127.0.0.1:8501 | `docker compose up` | Streamlit dashboard |
| `mlflow` | http://127.0.0.1:5000 | `--profile mlflow` | MLflow UI: retraining runs, registered models |
| `ollama` | http://127.0.0.1:11434 | `--profile llm` | Local LLM in a container (only where suitable, section 7) |

All of our services use **one image** (`aiml-lms-skills-intelligence:dev`): the same code everywhere; only the command differs.

**No MySQL container:** the project uses SQLite (Phase 9), a single file on the `lms_db` volume. MySQL arrives with the LMS integration project; it would be one more service here.

## 3. Volumes: where your data lives

| Volume | Path in the container | Holds |
| --- | --- | --- |
| `lms_db` | `/app/data/db` | SQLite database (Compose uses `DATA_SOURCE=database`) |
| `lms_index` | `/app/vector_store` | Document index (FAISS or NumPy) and its manifest |
| `lms_uploads` | `/app/data/uploads` | Uploaded documents (API 7) and checked CSV files |
| `lms_models` | `/app/models` | Model versions and the retraining history (API 6) |
| `lms_mlruns` | `/app/mlruns` | MLflow runs and registered models |
| `lms_accounts` | `/app/data/accounts` | Login accounts (Phase 17) |
| `lms_logs` | `/app/logs` | Audit log (Phase 17) |
| `ollama_models` | `/root/.ollama` | Downloaded LLMs (profile `llm`) |

`docker compose down` keeps the volumes; `docker compose down -v` **deletes them** (fresh start: the start step rebuilds the database and index).

## 4. First start

Docker Desktop must be running (whale icon in the taskbar).

```powershell
Copy-Item .env.example .env          # once; edit .env for your settings (never commit it)
docker compose up --build -d         # build the image and start api + dashboard in the background
docker compose ps                    # wait until both show "(healthy)" - about a minute the first time
```

What happens on the first start:

1. The `api` container runs the **start step** (`app/core/prepare.py`): it creates the folders, the SQLite database with the synthetic data (2,014 rows in 11 tables) and the document index (Ollama embeddings if Ollama is running on your PC, otherwise TF-IDF).
2. Uvicorn starts; the health check turns `healthy`.
3. Only then does the `dashboard` start (`depends_on: service_healthy`), so it never sees half-prepared volumes.

```powershell
docker compose logs api | Select-String prepare   # what the start step did
```

```
prepare | Folders: ready
prepare | Database: created and loaded from data/sample: 2014 rows in 11 tables
prepare | Document index: built: 8 documents, 132 chunks (tfidf/numpy). ...
```

On later starts, each step says `ready` and does nothing.

Then open http://127.0.0.1:8000/docs and http://127.0.0.1:8501, or run the smoke test from your venv:

```powershell
python scripts/api_smoke_test.py --admin-key <ADMIN_API_KEY from .env>
```

## 5. Everyday commands

| Task | Command |
| --- | --- |
| Start (after code changes: rebuild) | `docker compose up --build -d` |
| Start without rebuilding | `docker compose up -d` |
| Status and health | `docker compose ps` |
| Follow logs (Ctrl+C stops following) | `docker compose logs -f api` · `docker compose logs -f dashboard` |
| Last 100 lines | `docker compose logs --tail 100 api` |
| Restart one service | `docker compose restart api` |
| Stop, keep containers | `docker compose stop` |
| Stop and remove containers (data kept) | `docker compose down` |
| Fresh start: **delete all data volumes** | `docker compose down -v` |
| With MLflow UI | `docker compose --profile mlflow up -d` |
| CPU and memory use | `docker stats` |

Inside a running container:

```powershell
docker compose exec api python scripts/build_index.py              # rebuild the index (e.g. after ollama pull)
docker compose exec api python scripts/retrain.py --reason "test"  # retraining (or API 6 / dashboard)
docker compose exec api python scripts/create_user.py admin --role admin   # login accounts (Phase 17)
docker compose exec api python scripts/create_user.py --list
docker compose exec api python -m app.core.prepare                 # run the start step again
```

## 6. Inspecting and debugging

| Question | Command |
| --- | --- |
| Why is it `unhealthy`? | `docker inspect --format "{{json .State.Health}}" aiml-lms-skills-api` (last checks and their output) |
| Why did it stop? | `docker compose ps -a` then `docker compose logs api` |
| What settings does it really have? | `docker compose config` (the merged compose file with `.env` values) |
| Look around inside | `docker compose exec api bash` (`exit` to leave) |
| Which files are in the image? | `docker run --rm --entrypoint ls aiml-lms-skills-intelligence:dev -la /app` |
| Who does it run as? | `docker compose exec api id` → `uid=10001(appuser)` |
| Which volumes exist? | `docker volume ls` · `docker volume inspect aiml-lms-skills-intelligence_lms_db` |
| Image size and layers | `docker image ls aiml-lms-skills-intelligence` · `docker history aiml-lms-skills-intelligence:dev` |
| Run one command in a new container | `docker compose run --rm api python -c "import app; print('ok')"` |

Common problems:

| Symptom | Cause and fix |
| --- | --- |
| `port is already allocated` | A local `uvicorn`/`streamlit` already uses 8000/8501: stop it, or change the left number in `ports` |
| `Read-only file system` in the logs | Something writes outside the volumes. For a quick test, comment out `read_only: true` for that service, and tell us which path it needs |
| `dashboard` never starts | It waits for a healthy `api`: check `docker compose logs api` first |
| Assistant says "fallback (no LLM)" | Ollama is not reachable from the container. Is the Ollama app running on Windows? `docker compose exec api python scripts/check_llm.py` |
| Index built with TF-IDF although Ollama runs | Ollama was not running at the first start: `docker compose exec api python scripts/build_index.py` |
| Changes in code not visible | Rebuild: `docker compose up --build -d` |
| Disk filling up | `docker system df`, then `docker image prune` (old images) and `docker builder prune` (build cache) |

## 7. Ollama: on Windows or in a container?

| | Ollama app on Windows (default) | `--profile llm` (container) |
| --- | --- | --- |
| Setup | Already done in Phase 11 | Nothing to install on Windows |
| Speed | Can use your GPU | CPU only by default; slow on most laptops |
| Memory | Separate from Docker | Needs 4–8 GB inside Docker Desktop's limit |
| Reached from containers as | `http://host.docker.internal:11434` (set in compose.yaml) | `http://ollama:11434` |

To use the container: add `OLLAMA_BASE_URL=http://ollama:11434` to `.env`, then

```powershell
docker compose --profile llm up -d
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec api python scripts/build_index.py     # rebuild the index with Ollama embeddings
```

## 8. Hardening: what protects the containers

| Measure | Where | Why |
| --- | --- | --- |
| Two-stage build | `Dockerfile` | The final image has the finished libraries only, no build leftovers |
| Non-root user 10001 (build arg `APP_UID`; 1000 on Hugging Face), no login shell | `Dockerfile` | A break-in gets an ordinary user, not root |
| Code owned by root, read-only for the app | `Dockerfile` | The app cannot be made to change its own code |
| Read-only root filesystem | `compose.yaml` `read_only: true` | Only the volumes and `/tmp` are writable |
| All Linux capabilities dropped, `no-new-privileges` | `compose.yaml` | No raw network access, no `setuid` tricks |
| Ports on `127.0.0.1` only | `compose.yaml` | Other computers on your network cannot reach the services |
| Memory/CPU limits | `compose.yaml` `deploy.resources` | One runaway service cannot freeze your PC |
| Rotated logs (3 × 10 MB) | `compose.yaml` `logging` | Container logs cannot fill the disk |
| `init: true` | `compose.yaml` | Stop signals reach the app; no zombie processes |
| No secrets in the image | `.dockerignore`, `.env` at run time | Images get shared and pushed; secrets must not travel with them |
| Fixed base and Ollama versions | `Dockerfile`, `compose.yaml` | A rebuild does not silently change the system |
| Login required in production | `deployment/docker/compose.prod.yaml` + Phase 17 checks | A shared server never runs open |

CI checks all of this: it validates both Compose files, builds the image, checks it runs as user 10001, starts it **read-only with no capabilities on empty volumes**, checks that the start step built the index, and runs the smoke test (`.github/workflows/ci.yml`, job "Build Docker image").

## 9. A shared server: production override

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"   # put into .env as AUTH_SECRET_KEY=...
docker compose -f compose.yaml -f deployment/docker/compose.prod.yaml up -d
docker compose exec api python scripts/create_user.py admin --role admin
```

The override sets `APP_ENV=production` and `AUTH_ENABLED=true`. Compose refuses to start without `AUTH_SECRET_KEY`, and the app refuses to start in production without login. Put HTTPS in front (Phase 19). Keep the ports on `127.0.0.1` and let the HTTPS proxy reach them.

## 10. Limits of this setup

- One API process (one Uvicorn worker): the rate limiter counts per process (Phase 17). Kubernetes (Phase 20) scales with several pods plus a shared store.
- SQLite suits one machine; several API replicas need MySQL (the integration project).
- The image is large (expect well over 1 GB) because of scikit-learn, FAISS, Streamlit and MLflow. A slimmer API-only image without Streamlit and MLflow is possible later.
- Docker Desktop's default memory limit may be too small for `--profile llm`: *Settings → Resources → Memory*.

## 11. Public demo image (Phase 19)

The same Dockerfile builds Hugging Face Space images (a PRO plan is needed for Docker Spaces since 2026; the free demo uses Streamlit Community Cloud + Render, which install from the slim requirement files instead). `scripts/prepare_hf_space.py` copies it with `ARG APP_UID=1000` (Hugging Face runs every container as user 1000), the service's command on port 7860, and public-demo defaults. See [`PUBLIC_DEPLOYMENT_GUIDE.md`](PUBLIC_DEPLOYMENT_GUIDE.md). To try the demo settings locally:

```powershell
docker build --build-arg APP_UID=1000 -t lms-demo .
docker run --rm -p 127.0.0.1:8000:8000 -e APP_PROFILE=public-demo -e AUTH_ENABLED=true -e GUEST_ACCESS=true `
  -e AUTH_SECRET_KEY=<48-char secret> -e BOOTSTRAP_ADMIN_PASSWORD=<12+ chars> -e PREPARE_TRAIN_MODEL=true lms-demo
```
