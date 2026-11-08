# Snyk Security Guide (Phase 21)

**Snyk** finds known vulnerabilities (published CVEs) in what the project depends on, so they are noticed and fixed before an attacker uses them. It complements the application security of Phase 17 (login, roles, rate limits): that protects *our* code paths, while Snyk watches the *libraries and system packages* we ship.

| Scan | Command | What it checks | Where it runs |
| --- | --- | --- | --- |
| Dependencies (open source) | `snyk test --file=requirements.txt` | Python packages, including transitive ones (e.g. what MLflow pulls in) | Jenkins stage 7, GitHub job "Snyk security scan" |
| Container | `snyk container test <image> --file=Dockerfile` | Debian packages of the base image, Python packages inside the image, and a better base image to switch to | Jenkins stage 8, GitHub job |
| Monitoring | `snyk monitor` | Saves a snapshot to snyk.io; you get alerts when a new vulnerability affects it later | Jenkins with `SNYK_MONITOR` |

---

## 1. How findings are handled here

- **Severity threshold `high`:** only *high* and *critical* findings count by default. Lower ones are listed in the full report but don't change the build result.
- **Reported, not blocking (default):** a vulnerability published today must not stop unrelated work. In Jenkins, findings turn the build **UNSTABLE** (yellow); in GitHub the step is marked as failed-but-continued, and the results appear under **Security → Code scanning**.
- **Blocking when you want it:** Jenkins parameter `SNYK_FAIL_BUILD` (e.g. for release builds into `main`).
- **Fix, then re-scan:** most fixes are a version bump in `requirements.txt` (Snyk names the fixed version) or a newer base image in the `Dockerfile`. Commit on a branch; the pipeline proves the fix.
- **Accept only with a reason and an expiry:** if there is no fix yet, or the vulnerable code is not reachable here, record it in `.snyk` (section 5).

## 2. Create a Snyk account (free)

1. Go to **https://snyk.io** → **Sign up** → **GitHub** (the free plan has a monthly test limit; plenty for this project).
2. Snyk may offer to import repositories from GitHub. That's optional; the scans here run from the CLI in Jenkins and GitHub Actions.

## 3. Get the API token

On snyk.io: your name (bottom left) → **Account settings** → **Auth Token** (or *General → Auth Token*) → **click to show** → copy.

The token is a password: never put it in a file in the repository, a screenshot or a chat.

## 4. Give the token to the pipelines

**GitHub Actions:** repository **Settings → Secrets and variables → Actions → New repository secret**: name `SNYK_TOKEN`, value = the token. The next push runs the Snyk job. Without the secret, the job shows a notice "Snyk scan skipped" and passes.

**Jenkins:** *Manage Jenkins → Credentials → System → Global → Add Credentials*: kind **Secret text**, ID **`snyk-token`**, secret = the token (`JENKINS_CICD_GUIDE.md` section 4).

**Your PC (optional):**

```powershell
npm install --global snyk        # needs Node.js; or download snyk-win.exe from https://github.com/snyk/cli/releases
snyk auth                        # opens the browser to log in; stores the token in your user profile
snyk test --file=requirements.txt --package-manager=pip --command=python --severity-threshold=high
docker compose build api
snyk container test aiml-lms-skills-intelligence:dev --file=Dockerfile --severity-threshold=high
```

Run the dependency scan with the project's virtual environment active, so Snyk sees the installed versions.

## 5. Reading a finding and what to do

```
✗ High severity vulnerability found in example-package
  Description: Remote Code Execution
  Info: https://security.snyk.io/vuln/SNYK-PYTHON-EXAMPLEPACKAGE-1234567
  Introduced through: mlflow@3.x > example-package@1.2.0
  Fixed in: 1.2.4
```

| Situation | Action |
| --- | --- |
| Direct dependency (in `requirements.txt`), fix exists | Raise the lower bound, e.g. `pypdf>=6.1,<7.0`; test; commit |
| Transitive dependency ("introduced through mlflow > …"), fix exists | Upgrade the parent (mlflow), or add the fixed package as an explicit minimum in `requirements.txt` |
| Container: Debian package | Rebuild (newer base image patches); if Snyk suggests a newer base image tag, update `ARG PYTHON_IMAGE` in the `Dockerfile` |
| No fix yet, or not reachable in this app | Accept temporarily with a reason and an expiry: `snyk ignore --id=SNYK-... --expiry=2027-03-31 --reason="..."` (updates `.snyk`); review at the next phase |

**What "reachable" means here:** optional packages (MLflow, FAISS) are used only by admin-only retraining or are switched off in the public demo. That lowers the risk; it doesn't remove it. Prefer fixing.

## 5b. First scan of this project (November 2026)

The first Jenkins build ran all 11 stages; the smoke test passed 16/16, and the build was **UNSTABLE** because of the container scan:

| Finding | Where | Action taken |
| --- | --- | --- |
| 1 critical (`zlib`), several high (`sqlite3`, …) | System packages of the base image `python:3.11-slim-bookworm` (Debian 12) | Base image changed to `python:3.11-slim-trixie` (Debian 13, Snyk's recommendation) and `apt-get upgrade` added to the image build |
| None | Python packages inside the image | – |

Re-run the pipeline after such a change. Findings that remain and have **no fix in Debian yet** are accepted in `.snyk` with a reason and an expiry (section 5), and reviewed at the next phase.

## 6. Dependabot: updates before they become findings

`.github/dependabot.yml` makes GitHub open pull requests into `development` every week: one grouped pull request for minor and patch updates of Python packages, and separate ones for the Docker base image and GitHub Actions. Each runs the full CI; merge it when green. GitHub's own **Dependabot alerts** (repository *Settings → Code security*) can be switched on too. They're free and work with Snyk.

## 7. What Snyk does not cover

- **Our own code's logic:** covered by tests, Phase 17 controls, and code review. *Snyk Code* (static analysis, `snyk code test`) can be enabled in the Snyk organisation settings for extra checks.
- **Secrets accidentally committed:** GitHub *secret scanning* (Settings → Code security) catches those; `.gitignore` and the tests in Phases 17–21 prevent them.
- **The synthetic data:** there is no real personal data in the project to leak.
