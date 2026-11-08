# CI/CD Guide: Jenkins and GitHub Actions (Phase 21)

**CI** (continuous integration) checks every change automatically: lint, tests, security scan, image build. **CD** (continuous delivery/deployment) takes a checked change further: publish the image, deploy it to an environment, check that it works there.

This project has two pipelines:

| | GitHub Actions (`.github/workflows/ci.yml`) | Jenkins (`Jenkinsfile`) |
| --- | --- | --- |
| Runs | On GitHub's servers, on every push and pull request | On your Jenkins (here: a container on your PC) |
| Jobs / stages | Lint + tests → Docker build + hardened run + smoke test; Snyk scan | The 11 stages in section 2 |
| Secrets | Repository secrets (`SNYK_TOKEN`) | Jenkins credentials (`snyk-token`, `registry-credentials`) |
| Deployment | Streamlit Community Cloud and Render deploy themselves from `main` (Phase 19) | Stage 10: a development container on your PC |
| Good for | Gatekeeping pull requests, free for public repositories | Companies running their own CI servers, private networks, custom deployment steps |

Both use the same commands (ruff, pytest, docker, Snyk, the smoke test), so a green Jenkins build and a green GitHub check mean the same thing.

---

## 1. Files

| File | What |
| --- | --- |
| `Jenkinsfile` | The pipeline (declarative syntax), in the repository root, where Jenkins looks for it |
| `deployment/jenkins/Dockerfile` | Jenkins LTS + Python 3, Docker CLI, kubectl, Snyk CLI, the needed plugins |
| `deployment/jenkins/compose.yaml` | Starts that Jenkins on your PC: http://127.0.0.1:18080 |
| `.github/workflows/ci.yml` | GitHub Actions, including the Snyk job (Phase 21) |
| `.github/dependabot.yml`, `.snyk` | Dependency update pull requests; accepted Snyk findings (see `SNYK_SECURITY_GUIDE.md`) |

## 2. The pipeline stages

| # | Stage | What happens | Fails the build when |
| --- | --- | --- | --- |
| 1 | Checkout | Gets the code of the configured branch | Repository not reachable |
| 2 | Python environment | Creates a fresh virtual environment `.venv` in the workspace | Python 3 missing |
| 3 | Dependencies | `pip install -r requirements-dev.txt` | A package cannot be installed |
| 4 | Code quality | `ruff check`, `ruff format --check`, `kubectl kustomize` of the Kubernetes manifests | Lint or formatting errors, broken manifests |
| 5 | Unit tests | `pytest tests/unit tests/security` → JUnit report | Any test fails |
| 6 | API tests | `pytest tests/api tests/integration tests/dashboard` with coverage → JUnit + coverage reports | Any test fails |
| 7 | Snyk dependency scan | `snyk test` on `requirements.txt` (with the installed packages) | Only with `SNYK_FAIL_BUILD`; otherwise findings make the build **UNSTABLE** (yellow) |
| 8 | Docker build | Builds the image, checks it runs as user 10001, then `snyk container test` | Build error, root user (Snyk as in stage 7) |
| 9 | Publish image | Pushes to a registry, **only if** `PUBLISH_IMAGE` is ticked and `REGISTRY_IMAGE` set | Login or push fails |
| 10 | Development deployment | Replaces the container `lms-dev-api` with this build's image, hardened like Compose, with a fresh admin key | The container cannot start |
| 11 | Smoke test | `scripts/api_smoke_test.py` against the development container, including the admin upload | Any check fails |

After every build: test results (**Test Result** page), and `reports/` (coverage, Snyk JSON) under **Build Artifacts**.

**Parameters** (*Build with Parameters*):

| Parameter | Default | Meaning |
| --- | --- | --- |
| `SNYK_SEVERITY` | `high` | Lowest severity that counts (`low`, `medium`, `high`, `critical`) |
| `SNYK_FAIL_BUILD` | off | Fail instead of UNSTABLE on findings |
| `SNYK_MONITOR` | off | Send a snapshot to the Snyk dashboard (alerts on new vulnerabilities later) |
| `PUBLISH_IMAGE` / `REGISTRY_IMAGE` | off / empty | Publish, e.g. `ghcr.io/<user>/aiml-lms-skills-intelligence` |
| `DEPLOY_DEV` | on | Stages 10–11 |

## 3. Start Jenkins on your PC (once)

Docker Desktop must be running.

```powershell
cd D:\PythonProject\aiml_004\AIML_Project\AIML-LMS-Skills-Intelligence
docker compose -f deployment/jenkins/compose.yaml up -d --build      # first time: several minutes
docker exec lms-jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

1. Open **http://127.0.0.1:18080**, paste the password printed above → **Continue**.
2. **Install suggested plugins** (a few minutes).
3. Create your admin user → **Save and Continue** → keep the URL `http://127.0.0.1:18080/` → **Start using Jenkins**.

Check that Jenkins can use Docker:

```powershell
docker exec lms-jenkins docker version --format "{{.Server.Version}}"   # prints a version, no "permission denied"
```

## 4. Credentials (secrets): never in the Jenkinsfile

*Manage Jenkins → Credentials → System → Global credentials (unrestricted) → Add Credentials*:

| Kind | ID (exactly) | Value | Needed for |
| --- | --- | --- | --- |
| Secret text | `snyk-token` | your Snyk API token (`SNYK_SECURITY_GUIDE.md` section 3) | Stages 7–8; without it they are skipped and the build turns UNSTABLE |
| Username with password | `registry-credentials` | registry user + access token (e.g. GitHub user + a token with `write:packages`) | Stage 9, only when publishing |

Jenkins stores credentials encrypted, injects them only inside `withCredentials { }`, and masks them as `****` in logs.

## 5. Create the pipeline job

1. **New Item** → name `lms-skills-intelligence` → **Pipeline** → **OK**.
2. Section **Pipeline**:
   - **Definition:** *Pipeline script from SCM*
   - **SCM:** *Git*, **Repository URL:** `https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence.git` (public: no credentials needed)
   - **Branch Specifier:** `*/development` (or `*/main`)
   - **Script Path:** `Jenkinsfile`
3. **Save** → **Build Now**.

The first build reads the Jenkinsfile and registers the parameters; afterwards use **Build with Parameters**. Follow it under the build → **Console Output**, or the stage table on the job page. A first run takes about 10–15 minutes (installing packages, building the image); later runs reuse caches.

When it's green, the development API runs at **http://127.0.0.1:18001/docs**.

**Automatic builds:** Jenkins on your PC cannot receive GitHub webhooks. Under *Configure → Build Triggers* tick **Poll SCM** with `H/15 * * * *` (checks for new commits every 15 minutes), or build manually.

## 6. Build results

| Colour | Meaning |
| --- | --- |
| Green (SUCCESS) | Every stage passed |
| Yellow (UNSTABLE) | Everything ran, but Snyk found vulnerabilities, or the Snyk token or CLI is missing: read the messages at the end of the log |
| Red (FAILURE) | A stage failed: the console shows which, and the development container's last log lines are printed |
| Grey (ABORTED) | Stopped by hand or by the 60-minute timeout |

## 7. Troubleshooting

| Message | Fix |
| --- | --- |
| `permission denied while trying to connect to the Docker daemon socket` | The jenkins user lacks the socket's group: find it with `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock alpine stat -c %g /var/run/docker.sock`, put `DOCKER_GID=<number>` in front of the `docker compose ... up -d` command (or in a `.env` next to the compose file), recreate the container |
| Port 18080 or 18001 "already in use" / "forbidden" | Another program or a Windows-reserved range: change the left port in `deployment/jenkins/compose.yaml` (Jenkins) or `DEV_PORT` in the Jenkinsfile |
| `No such DSL method 'timestamps'` | Install the *Timestamper* plugin (Manage Jenkins → Plugins), or rebuild the Jenkins image |
| Stage 11: "server ... is not answering" | Stage 10's container did not start: the post-failure log lines show why; `docker logs lms-dev-api` |
| Stage 3 very slow | First run downloads everything; later runs use pip's cache in the Jenkins home volume |
| `network lms-jenkins not found` | Start Jenkins with the compose file in `deployment/jenkins/` (it creates the network) |
| Disk filling up | `docker image prune -f` (old build images), *Discard old builds* keeps 20 builds |

Check a changed Jenkinsfile before committing: open a build → **Replay**, edit, **Run**. Or use *Pipeline Syntax* (link on the job page) to generate steps.

## 8. Stop and start

```powershell
docker compose -f deployment/jenkins/compose.yaml stop     # stop (jobs and settings are kept)
docker compose -f deployment/jenkins/compose.yaml start
docker rm -f lms-dev-api                                     # remove the development API
docker compose -f deployment/jenkins/compose.yaml down -v   # remove Jenkins and ALL its data
```

## 9. Security notes

- **No secrets in Git:** the Jenkinsfile uses only credential IDs; the development admin key is generated per build and deleted from the workspace afterwards; registry passwords go through `--password-stdin`.
- **The Docker socket is powerful:** whoever controls Jenkins controls Docker Desktop. That is why this Jenkins listens on `127.0.0.1` only and is meant for your PC. A company Jenkins would build with separate agents (or Kaniko/BuildKit) instead of the host socket.
- **Least privilege:** Jenkins runs as the `jenkins` user; the deployed container is hardened (read-only, no capabilities, non-root), as in Compose and Kubernetes.
- **Supply chain:** Snyk checks the dependencies and the image on every build; Dependabot proposes updates weekly (`SNYK_SECURITY_GUIDE.md`).
