# Dockerfile: recipe for building the API container image.
#
# Build:  docker build -t aiml-lms-skills-intelligence:dev .
# Run:    docker run --rm -p 8000:8000 aiml-lms-skills-intelligence:dev
#
# WHY python:3.11-slim
#   Same Python version as local development (avoids "works on my machine").
#   "slim" is a small Debian image: much smaller than the full image and more
#   compatible with ML libraries (numpy, faiss) than the even smaller Alpine.

FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: do not write .pyc files inside the container.
# PYTHONUNBUFFERED: print logs immediately so `docker logs` shows them live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy requirements FIRST and install them in their own layer. Docker caches
# this layer, so changing your code does not reinstall every library.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Now copy the application code and the synthetic sample data the API serves.
COPY app ./app
COPY data/sample ./data/sample
# Phase 12: knowledge documents and the scripts that index them
# (inside the container: python scripts/build_index.py)
COPY documents ./documents
COPY scripts ./scripts

# Run as a normal user, not root: if the app were ever compromised, the
# attacker would have far fewer permissions inside the container.
RUN useradd --create-home appuser \
    && mkdir -p /app/data /app/vector_store \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Docker checks this every 30 s and marks the container healthy/unhealthy.
# Python's urllib is used because curl is not installed in the slim image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# 0.0.0.0 = accept connections from outside the container (needed for -p 8000:8000).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
