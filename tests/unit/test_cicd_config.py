"""
CI/CD configuration (Phase 21), checked without Jenkins or GitHub: the Jenkinsfile has the
11 required stages in order and no secrets; the Jenkins image has its tools; the GitHub
Snyk job only runs with a token; Dependabot watches every kind of dependency.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
JENKINSFILE = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
JENKINS_IMAGE = (ROOT / "deployment/jenkins/Dockerfile").read_text(encoding="utf-8")
JENKINS_COMPOSE = yaml.safe_load((ROOT / "deployment/jenkins/compose.yaml").read_text(encoding="utf-8"))
CI = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
DEPENDABOT = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))

REQUIRED_STAGES = [
    "Checkout",
    "Python environment",
    "Dependencies",
    "Code quality",
    "Unit tests",
    "API tests",
    "Snyk dependency scan",
    "Docker build",
    "Publish image",
    "Development deployment",
    "Smoke test",
]


def stages() -> list[str]:
    return re.findall(r"stage\('(\d+)\. ([^']+)'\)", JENKINSFILE)


def test_jenkinsfile_has_the_eleven_stages_in_order():
    found = stages()
    assert [int(n) for n, _ in found] == list(range(1, 12))
    assert [name for _, name in found] == REQUIRED_STAGES


@pytest.mark.parametrize(
    "snippet",
    [
        "checkout scm",
        "pytest tests/unit tests/security",
        "pytest tests/api tests/integration tests/dashboard",
        "snyk test --file=requirements.txt",
        "snyk container test",
        "docker build",
        "scripts/api_smoke_test.py",
        "junit ",
    ],
)
def test_jenkinsfile_does_the_work(snippet):
    assert snippet in JENKINSFILE


def test_jenkinsfile_takes_secrets_only_from_credentials():
    assert "credentialsId: 'snyk-token'" in JENKINSFILE
    assert "credentialsId: 'registry-credentials'" in JENKINSFILE
    assert "--password-stdin" in JENKINSFILE  # never a password on the command line
    # no literal tokens/passwords: long random-looking strings or KEY=value assignments
    assert not re.search(r"(?i)(token|password|secret|api_key)\s*=\s*['\"][^'\"$]{8,}", JENKINSFILE)
    assert not re.search(r"\b[A-Za-z0-9_\-]{40,}\b", JENKINSFILE)


def test_publishing_happens_only_when_configured():
    publish = JENKINSFILE.split("stage('9. Publish image')")[1].split("stage('10.")[0]
    assert "when { expression { params.PUBLISH_IMAGE && params.REGISTRY_IMAGE?.trim() } }" in publish


def test_jenkinsfile_braces_balance():
    code = re.sub(r"//[^\n]*", "", JENKINSFILE)  # comments may contain anything
    code = re.sub(r"'''.*?'''|\"\"\".*?\"\"\"", "", code, flags=re.DOTALL)
    code = re.sub(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"", "", code)
    assert code.count("{") == code.count("}") and code.count("(") == code.count(")")


def test_jenkins_image_has_the_pipeline_tools():
    for tool in ("python3-venv", "docker.io", "kubectl", "snyk"):
        assert tool in JENKINS_IMAGE
    assert JENKINS_IMAGE.rstrip().splitlines()[-1].startswith("RUN jenkins-plugin-cli")
    assert re.search(r"^USER jenkins$", JENKINS_IMAGE, re.MULTILINE)  # not left as root


def test_jenkins_stays_on_this_pc_and_shares_the_dev_network():
    service = JENKINS_COMPOSE["services"]["jenkins"]
    assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    network = JENKINS_COMPOSE["networks"]["lms-jenkins"]["name"]
    assert f"DEV_NETWORK = '{network}'" in JENKINSFILE


def test_github_snyk_job_runs_only_with_a_token():
    job = CI["jobs"]["security"]
    assert job["env"]["SNYK_TOKEN"] == "${{ secrets.SNYK_TOKEN }}"
    assert job["permissions"]["security-events"] == "write"
    first, *rest = job["steps"]
    assert first["if"] == "env.SNYK_TOKEN == ''"
    assert all("env.SNYK_TOKEN != ''" in step["if"] for step in rest)
    commands = " ".join(step.get("run", "") for step in rest)
    assert "snyk test" in commands and "snyk container test" in commands


def test_dependabot_watches_python_docker_and_actions():
    ecosystems = {u["package-ecosystem"] for u in DEPENDABOT["updates"]}
    assert ecosystems == {"pip", "docker", "github-actions"}
    assert all(u["target-branch"] == "development" for u in DEPENDABOT["updates"])
