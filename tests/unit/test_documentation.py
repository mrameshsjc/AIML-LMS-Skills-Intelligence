"""Phase 22: the final documentation exists, is linked, and is complete."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

REQUIRED_DOCS = [
    "PROJECT_OVERVIEW.md",
    "ARCHITECTURE.md",
    "API_DOCUMENTATION.md",
    "DATA_DICTIONARY.md",
    "DATA_PIPELINE_GUIDE.md",
    "DATABASE_GUIDE.md",
    "MYSQL_CONFIGURATION_GUIDE.md",
    "ML_MODEL_GUIDE.md",
    "LLM_RAG_GUIDE.md",
    "DASHBOARD_GUIDE.md",
    "SECURITY_GUIDE.md",
    "SNYK_SECURITY_GUIDE.md",
    "DOCKER_GUIDE.md",
    "KUBERNETES_GUIDE.md",
    "JENKINS_CICD_GUIDE.md",
    "PUBLIC_DEPLOYMENT_GUIDE.md",
    "TESTING_GUIDE.md",
    "TROUBLESHOOTING.md",
    "DEMO_WALKTHROUGH.md",
    "ACCEPTANCE_CHECKLIST.md",
]


@pytest.mark.parametrize("name", REQUIRED_DOCS)
def test_required_doc_exists_and_is_listed_in_the_index(name):
    assert (DOCS / name).is_file(), name
    assert f"({name})" in (DOCS / "README.md").read_text(encoding="utf-8")


def test_readme_covers_the_whole_project():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for section in (
        "## What it does",
        "## How it is built",
        "## Quick start",
        "## Documentation",
        "## Known limitations and future improvements",
    ):
        assert section in text, section
    assert "https://lms-skills-intelligence.streamlit.app" in text
    assert "https://lms-skills-api.onrender.com/docs" in text


def test_relative_links_in_docs_point_to_existing_files():
    broken = []
    for md in [ROOT / "README.md", *DOCS.glob("*.md"), DOCS / "screenshots" / "README.md"]:
        for target in re.findall(r"\]\(([^)#\s]+)\)", md.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if target.endswith(".png"):
                continue  # screenshots are added by hand
            if not (md.parent / target).exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not broken, broken


def test_screenshot_list_matches_the_walkthrough():
    text = (DOCS / "screenshots" / "README.md").read_text(encoding="utf-8")
    names = re.findall(r"`(\d{2}-[a-z0-9-]+\.png)`", text)
    assert len(set(names)) >= 14
