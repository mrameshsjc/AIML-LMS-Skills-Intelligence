"""
The free public-demo hosting files (Phase 19): render.yaml (API on Render) and the
Streamlit Community Cloud secrets template (dashboard). Checked without the hosts.
"""

import tomllib
from pathlib import Path

import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
RENDER = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"][0]
ENV = {item["key"]: item for item in RENDER["envVars"]}
SECRETS = tomllib.loads(
    (ROOT / "deployment/cloud/streamlit/secrets.toml.example").read_text(encoding="utf-8")
)
FIELDS = {name.upper() for name in Settings.model_fields}


def test_render_runs_the_api_with_the_slim_install_and_the_start_step():
    assert RENDER["type"] == "web" and RENDER["plan"] == "free" and RENDER["runtime"] == "python"
    assert RENDER["buildCommand"] == "pip install -r requirements-api.txt"
    start = RENDER["startCommand"]
    assert start.startswith("python -m app.core.prepare uvicorn app.main:app") and "--port $PORT" in start
    assert RENDER["healthCheckPath"] == "/api/v1/health"


def test_render_public_demo_settings_and_secrets():
    assert ENV["APP_PROFILE"]["value"] == "public-demo"
    assert ENV["AUTH_ENABLED"]["value"] == "true" and ENV["GUEST_ACCESS"]["value"] == "true"
    assert ENV["AUTH_SECRET_KEY"] == {"key": "AUTH_SECRET_KEY", "generateValue": True}
    assert ENV["BOOTSTRAP_ADMIN_PASSWORD"] == {
        "key": "BOOTSTRAP_ADMIN_PASSWORD",
        "sync": False,
    }  # asked, not stored
    unknown = set(ENV) - FIELDS - {"PYTHON_VERSION"}
    assert unknown == set(), f"render.yaml sets settings the engine does not have: {unknown}"


def test_streamlit_secrets_template():
    assert set(SECRETS) <= FIELDS, set(SECRETS) - FIELDS
    assert SECRETS["PREPARE_IN_DASHBOARD"] == "true" and SECRETS["GUEST_ACCESS"] == "true"
    assert SECRETS["AUTH_SECRET_KEY"].startswith("paste-")  # a placeholder, never a real secret
    assert SECRETS["BOOTSTRAP_ADMIN_PASSWORD"].startswith("paste-")


def test_the_template_values_load_as_settings():
    values = {k.lower(): v for k, v in SECRETS.items()}
    values.update(auth_secret_key="s" * 48, bootstrap_admin_password="long-enough-pass-1")
    settings = Settings(**values)
    assert settings.guest_access and settings.prepare_in_dashboard and settings.check_security() == []
