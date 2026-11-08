"""
Checks of the container setup (Phase 18) that run without Docker: the
Dockerfile, compose.yaml and .dockerignore keep their security and volume
promises. (CI also builds the image and runs it hardened.)

HOW TO RUN
    PS> pytest tests/unit/test_docker_config.py -v
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
PROD = yaml.safe_load((ROOT / "deployment/docker/compose.prod.yaml").read_text(encoding="utf-8"))
IGNORE = [
    line.strip()
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
OUR_SERVICES = ["api", "dashboard", "mlflow"]  # built from our image (ollama is a third-party image)


# --- Dockerfile ------------------------------------------------------------------------------------
def test_image_runs_as_a_fixed_non_root_user():
    users = re.findall(r"^USER\s+(\S+)", DOCKERFILE, re.MULTILINE)
    assert users and users[-1] == "${APP_UID}:${APP_UID}"
    assert re.search(r"^ARG APP_UID=10001$", DOCKERFILE, re.MULTILINE)  # not root (0) by default


def test_two_stages_and_a_fixed_base_image():
    assert len(re.findall(r"^FROM\s", DOCKERFILE, re.MULTILINE)) == 2
    base = re.search(r"^ARG PYTHON_IMAGE=(\S+)", DOCKERFILE, re.MULTILINE).group(1)
    assert base.startswith("python:3.11-slim-") and base != "python:3.11-slim"  # pinned to a Debian release


def test_no_secret_is_baked_into_the_image():
    for line in DOCKERFILE.splitlines():
        if re.match(r"^\s*(ENV|ARG)\b", line):
            assert not re.search(r"(KEY|SECRET|PASSWORD|TOKEN)\s*=", line, re.IGNORECASE), line
    assert "COPY . " not in DOCKERFILE  # copy named folders only, never "everything"


def test_healthcheck_and_start_step():
    assert "HEALTHCHECK" in DOCKERFILE and "/api/v1/health" in DOCKERFILE
    assert 'ENTRYPOINT ["python", "-m", "app.core.prepare"]' in DOCKERFILE


def test_only_volume_folders_are_writable():
    chown = re.search(r"chown -R \$\{APP_UID\}:\$\{APP_UID\} ([^\n]+)", DOCKERFILE).group(1).split()
    assert set(chown) == {
        "data/uploads",
        "data/accounts",
        "data/db",
        "vector_store",
        "models",
        "logs",
        "mlruns",
    }


# --- compose.yaml ----------------------------------------------------------------------------------
def test_services_and_optional_profiles():
    services = COMPOSE["services"]
    assert {"api", "dashboard", "mlflow", "ollama"} <= set(services)
    assert "profiles" not in services["api"] and "profiles" not in services["dashboard"]
    assert services["mlflow"]["profiles"] == ["mlflow"] and services["ollama"]["profiles"] == ["llm"]


@pytest.mark.parametrize("service", OUR_SERVICES)
def test_every_service_is_hardened(service):
    s = COMPOSE["services"][service]
    assert s["read_only"] is True and "/tmp" in s["tmpfs"]
    assert s["cap_drop"] == ["ALL"] and "no-new-privileges:true" in s["security_opt"]
    assert s["init"] is True and s["deploy"]["resources"]["limits"]["memory"]
    assert "healthcheck" in s  # each overrides the image's API health check with its own


@pytest.mark.parametrize("service", list(COMPOSE["services"]))
def test_ports_are_only_open_on_this_pc(service):
    for port in COMPOSE["services"][service].get("ports", []):
        assert port.startswith("127.0.0.1:"), port


def test_persistent_volumes_for_database_index_uploads_models():
    mounts = dict(v.split(":", 1)[::-1] for v in COMPOSE["services"]["api"]["volumes"])
    for path in ("/app/data/db", "/app/vector_store", "/app/data/uploads", "/app/models", "/app/mlruns"):
        assert path in mounts and mounts[path] in COMPOSE["volumes"]
    assert COMPOSE["services"]["dashboard"]["volumes"] == COMPOSE["services"]["api"]["volumes"]


def test_only_the_api_prepares_the_shared_volumes():
    env = {name: COMPOSE["services"][name]["environment"].get("PREPARE_ON_START") for name in OUR_SERVICES}
    assert env == {"api": "true", "dashboard": "false", "mlflow": "false"}
    assert COMPOSE["services"]["dashboard"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_third_party_image_is_pinned():
    image = COMPOSE["services"]["ollama"]["image"]
    assert ":" in image and not image.endswith(":latest")


def test_production_override_requires_login_and_a_secret():
    env = PROD["services"]["api"]["environment"]
    assert env["AUTH_ENABLED"] == "true" and env["APP_ENV"] == "production"
    assert env["AUTH_SECRET_KEY"].startswith("${AUTH_SECRET_KEY:?")  # Compose stops if it is missing


# --- .dockerignore ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "pattern", [".env", ".env.*", ".git", "data/users.json", "data/accounts", "tests", "models", "**/*.db"]
)
def test_secrets_and_generated_files_stay_out_of_the_image(pattern):
    assert pattern in IGNORE


def test_sample_data_and_documents_stay_in():
    assert "!data/sample" in IGNORE and "!documents/*.md" in IGNORE
