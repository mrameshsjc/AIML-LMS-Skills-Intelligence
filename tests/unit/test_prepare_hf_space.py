"""scripts/prepare_hf_space.py (Phase 19): the generated Hugging Face Space folders."""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prepare_hf_space", ROOT / "scripts" / "prepare_hf_space.py")
hf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hf)


@pytest.mark.parametrize("service, starts", [("dashboard", "streamlit"), ("api", "uvicorn")])
def test_space_dockerfile(service, starts):
    text = hf.space_dockerfile(service)
    assert text.startswith("# syntax=docker/dockerfile:1\n")  # the directive must stay first
    assert re.search(r"^ARG APP_UID=1000$", text, re.MULTILINE)  # Hugging Face runs as user 1000
    assert "HEALTHCHECK" not in text and "EXPOSE 7860" in text
    cmd = re.search(r"^CMD (\[.*\])$", text, re.MULTILINE).group(1)
    assert cmd.startswith(f'["{starts}"') and "7860" in cmd
    assert 'GUEST_ACCESS="true"' in text and 'APP_PROFILE="public-demo"' in text
    assert not re.search(r"(SECRET_KEY|PASSWORD|API_KEY)=", text)  # secrets come from the Space settings


@pytest.mark.parametrize("service", ["dashboard", "api"])
def test_space_readme_header(service):
    text = hf.space_readme(service)
    header = yaml.safe_load(text.split("---")[1])
    assert header["sdk"] == "docker" and header["app_port"] == 7860
    assert len(header["short_description"]) <= 60
    assert "synthetic" in text.lower()


def test_build_copies_the_app_but_no_secrets(tmp_path):
    out = tmp_path / "space"
    files = hf.build("api", out)
    assert {"Dockerfile", "README.md", "app", "documents", "data/sample"} <= set(files)
    assert (out / "app" / "main.py").exists() and (out / "data" / "sample" / "employees.csv").exists()
    copied = {p.name for p in out.rglob("*")}
    assert not ({".env", "users.json", "audit.jsonl"} & copied) and "__pycache__" not in copied


def test_out_folder_must_be_outside_the_project():
    with pytest.raises(ValueError):
        hf.build("api", ROOT / "space")
