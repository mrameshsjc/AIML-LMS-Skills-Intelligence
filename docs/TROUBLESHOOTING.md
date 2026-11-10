# Troubleshooting

Problems met while building and running the engine, with the fix. Commands are for **PowerShell** on Windows 11, run from the project folder. Each guide has its own detailed table; this page collects the common ones.

## 1. Python environment and settings

| Symptom | Fix |
| --- | --- |
| `..\.venv\Scripts\Activate.ps1 is not recognized` | The venv is two folders up: `D:\PythonProject\aiml_004\.venv\Scripts\Activate.ps1`. If the prompt already shows `(.venv)`, it is active |
| `running scripts is disabled on this system` | Once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `ModuleNotFoundError` | `pip install -r requirements-dev.txt` in the active venv |
| No `.env` file | Create it from the template: `Copy-Item .env.example .env`. It is git-ignored on purpose |
| `rag_min_score … unable to parse string as a number` (or another setting) | An old `.env` line like `KEY=   # comment` turns the comment into the value. Leave nothing after `=` for empty settings. Current versions ignore such values |
| Settings changed but no effect | Restart `uvicorn` / `streamlit`: settings are read at start |
| `Unsafe security settings: AUTH_SECRET_KEY must have at least 32 characters` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`, put it in `.env` |
| Tests behave differently with your `.env` | They shouldn't: `tests/conftest.py` sets safe defaults. If one fails only on your PC, send the `FAILED` lines |

## 2. Running locally

| Symptom | Fix |
| --- | --- |
| Port 8000 "already in use" | Another `uvicorn` or Docker Compose runs: stop it, or `uvicorn app.main:app --port 8001` |
| Port "forbidden by its access permissions" (often 8080) | Windows reserves port ranges for WSL2/Hyper-V; use another port (e.g. 18000). List: `netsh interface ipv4 show excludedportrange protocol=tcp` |
| Assistant says "fallback (no LLM)" | Ollama isn't running or the model isn't installed: start the Ollama app, `ollama pull llama3.2:3b`, check `python scripts/check_llm.py` |
| Ollama stores models on C: although `OLLAMA_MODELS` points to D: | Newer Ollama apps use their own setting: *Ollama app → Settings → Model location*. Or move the folder and create a junction (`LLM_RAG_GUIDE.md`) |
| "No document index yet" | `python scripts/build_index.py` (Docker, Kubernetes and the public demo build it automatically) |
| Login on, Swagger returns 401 | Click **Authorize** and log in (accounts: `python scripts/create_demo_users.py`), or set `GUEST_ACCESS=true` |
| A smoke-test command fails with `The '<' operator is reserved` | `<…>` in the guides is a placeholder: replace it with the real value, without the brackets |

## 3. Git and GitHub

| Symptom | Fix |
| --- | --- |
| Pull request shows conflicts after branching from an old `development` | Always `git checkout development; git pull` **before** `git checkout -b phase-…`. To resolve: merge `development` into your branch and keep the correct side of each conflict |
| Merge committed with `<<<<<<< HEAD` markers (pip/pytest fail on them) | Restore the clean files from the right commit (`git checkout <commit> -- .`), check with `Select-String -Pattern "<<<<<<<"`, commit |
| "There isn't anything to compare" (`main` ← `development`) | Either `main` doesn't exist (create it from `development`) or both point to the same commit (nothing to merge: correct) |
| Pushed to a branch whose pull request was already merged; no new pull request | Open one by hand: base `development` ← compare your branch |
| Compare page looks empty | Base and compare are swapped: **base** is where changes go, **compare** where they come from |

## 4. Docker

| Symptom | Fix |
| --- | --- |
| `failed to connect to the docker API … dockerDesktopLinuxEngine` | Start Docker Desktop and wait for "Engine running"; check with `docker version` (Client **and** Server) |
| `Read-only file system` in container logs | Something writes outside the volumes: tell us the path. For a quick test, remove `read_only: true` for that service in `compose.yaml` |
| `dashboard` never starts | It waits for a healthy `api`: `docker compose logs api` |
| Two compose files warning | `docker-compose.yml` was replaced by `compose.yaml` in Phase 18: `git rm docker-compose.yml` |
| Disk filling up | `docker system df`, then `docker image prune` and `docker builder prune` |

## 5. Kubernetes (Minikube)

| Symptom | Fix |
| --- | --- |
| `minikube start` fails with a Docker API error | Docker Desktop isn't running (section 4) |
| `minikube image build`: "open Dockerfile: no such file" | Old `.dockerignore` excluded the Dockerfile; use the current version, or `docker build` + `minikube image load` |
| `ImagePullBackOff` / `ErrImageNeverPull` | The image isn't inside Minikube: `minikube image build -t aiml-lms-skills-intelligence:dev .` |
| `CreateContainerConfigError` | The Secret `lms-secrets` is missing: create it from `secret.env` |
| `port-forward`: "Only one usage of each socket address" / "forbidden" | Port in use or reserved by Windows: use `18000:80` |
| Smoke test "not answering" | The port-forward must keep running in its own window; it also stops when pods are replaced |
| API 7 upload 401 with `--admin-key` | The cluster's Secret differs from `secret.env`: compare with `kubectl -n lms-skills exec deployment/lms-api -- printenv ADMIN_API_KEY`, recreate the Secret, `rollout restart` |
| "Cannot reach Ollama at http://host.minikube.internal" | That name doesn't resolve on some setups; optional: try `host.docker.internal` in the ConfigMap. Otherwise the labelled fallback answers |

## 6. Jenkins and Snyk

| Symptom | Fix |
| --- | --- |
| Jenkins image build fails with exit code 127 | A tool is missing; the current image downloads Docker's official CLI. Rebuild with the latest `deployment/jenkins/Dockerfile` |
| `No such container: lms-jenkins` | The image build failed, so the container was never created: fix the build first |
| Only "Build with Parameters", no "Build Now" | Normal after the first run: same button, keep the defaults, **Build** |
| `permission denied … docker.sock` | Set `DOCKER_GID` (`JENKINS_CICD_GUIDE.md` section 7) |
| Build UNSTABLE (yellow) | Snyk found vulnerabilities, or the `snyk-token` credential is missing: read the warnings at the end of the log |
| Snyk container findings in Debian packages | Newer base image + `apt-get upgrade`; unfixed ones are accepted in `.snyk` with a reason and an expiry |

## 7. Public demo

| Symptom | Fix |
| --- | --- |
| Hugging Face asks for PRO for Docker Spaces | Docker Spaces aren't free since 2026: the demo runs on Streamlit Community Cloud + Render |
| Streamlit sidebar says "Login is off" | Paste the **whole** secrets block (`deployment/cloud/streamlit/secrets.toml.example`), not only the two secrets |
| GitHub authorize button disabled | Wait a few seconds with the page focused, scroll to the button, or try another browser |
| API takes about a minute to answer | Render's free service woke up after 15 minutes without traffic |
| Someone changed the demo data | Admin login → Model management → **Reset the demo** |

## Still stuck?

Collect: the exact command, the **first** error lines (not only the last), and where it happened (local, Docker, Kubernetes, Jenkins, public). Most problems come down to a missing setting, a busy port, or a service that isn't running.
