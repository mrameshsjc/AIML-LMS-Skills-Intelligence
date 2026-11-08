# syntax=docker/dockerfile:1
# Dockerfile: the recipe for the container image (Phase 1, hardened in Phase 18).
# One image runs every service: the API (default), the dashboard and the MLflow UI.
#
#   PS> docker build -t aiml-lms-skills-intelligence:dev .
#   PS> docker run --rm -p 127.0.0.1:8000:8000 aiml-lms-skills-intelligence:dev
#   Everyday use is Docker Compose (compose.yaml) - see docs/DOCKER_GUIDE.md.
#
# HARDENING (Phase 18)
#   - Two stages: libraries are installed in a "builder" stage; the final image
#     gets only the finished virtual environment (no pip caches, no build files).
#   - Runs as a normal user with a fixed ID (10001), never as root. Kubernetes
#     (Phase 20) can then verify "runAsNonRoot".
#   - The code and the sample data belong to root and are READ-ONLY for the app:
#     even a compromised app cannot change its own code. Only the folders that
#     are mounted as volumes are writable.
#   - No secrets in the image: .env, accounts and keys are excluded by
#     .dockerignore and arrive as environment variables at run time.
#   - Works with a read-only root filesystem (compose.yaml: read_only: true).
#
# WHY python:3.11-slim-bookworm
#   The same Python version as CI; "slim" is a small Debian image that works
#   with ML wheels (numpy, faiss, scikit-learn), unlike Alpine. The tag is
#   fixed to a Debian release (bookworm) so a rebuild does not silently switch
#   operating system. For fully repeatable builds pin the digest as well:
#   docker build --build-arg PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:<digest> .

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

# ---------- Stage 1: install the Python libraries --------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# A virtual environment in /opt/venv is easy to copy into the final stage as one folder.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Requirements first, in their own layer: Docker reuses this layer (no reinstall)
# as long as requirements.txt does not change, even when the code changes.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# ---------- Stage 2: the image that runs -----------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ARG APP_VERSION=dev
# The user ID the app runs as. 10001 by default; Hugging Face Spaces always run containers as
# user 1000, so the Space build uses APP_UID=1000 (scripts/prepare_hf_space.py, Phase 19).
ARG APP_UID=10001
LABEL org.opencontainers.image.title="LMS Skills Intelligence Engine" \
      org.opencontainers.image.description="Skills gaps, role matching, training recommendations, learning paths, LLM + RAG assistant (synthetic data)" \
      org.opencontainers.image.source="https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence" \
      org.opencontainers.image.version="${APP_VERSION}"

# PYTHONDONTWRITEBYTECODE: no .pyc files (the code folder is read-only anyway).
# PYTHONUNBUFFERED: logs appear immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/home/appuser

# The user the app runs as: fixed IDs, no login shell.
RUN groupadd --gid ${APP_UID} appuser \
    && useradd --uid ${APP_UID} --gid ${APP_UID} --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

# Application code and read-only content (owned by root: the app can read, not change, them).
COPY app ./app
COPY data/sample ./data/sample
COPY documents ./documents
COPY scripts ./scripts
COPY dashboard ./dashboard
COPY .streamlit ./.streamlit

# The ONLY writable places - each is a volume in compose.yaml. Creating them here,
# owned by appuser, means a new named volume starts with the right owner.
RUN mkdir -p data/uploads/documents data/accounts data/db vector_store models logs mlruns \
    && chown -R ${APP_UID}:${APP_UID} data/uploads data/accounts data/db vector_store models logs mlruns

USER ${APP_UID}:${APP_UID}

EXPOSE 8000 8501 5000

# Docker checks the API every 30 s ("healthy" / "unhealthy"). The first start may build
# the document index, hence the longer start period. Python's urllib: no curl in slim images.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# Start step (app/core/prepare.py): folders, database and document index on first start,
# then it becomes the command below. 0.0.0.0 = accept connections from outside the container.
ENTRYPOINT ["python", "-m", "app.core.prepare"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
