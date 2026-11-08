"""
The Kubernetes manifests (Phase 20), checked without a cluster: every required
object exists, the pieces fit together (labels, names, mounts, settings) and every
container is hardened, probed and limited. CI also renders them with `kubectl kustomize`.
"""

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

FOLDER = Path(__file__).resolve().parents[2] / "deployment" / "kubernetes"
KUSTOMIZATION = yaml.safe_load((FOLDER / "kustomization.yaml").read_text(encoding="utf-8"))
OBJECTS = [
    doc
    for name in KUSTOMIZATION["resources"]
    for doc in yaml.safe_load_all((FOLDER / name).read_text(encoding="utf-8"))
    if doc
]
BY_KIND: dict[str, list[dict]] = {}
for obj in OBJECTS:
    BY_KIND.setdefault(obj["kind"], []).append(obj)
DEPLOYMENTS = {d["metadata"]["name"]: d for d in BY_KIND["Deployment"]}
CONFIG = BY_KIND["ConfigMap"][0]["data"]
FIELDS = {name.upper() for name in Settings.model_fields}


def pod(name: str) -> dict:
    return DEPLOYMENTS[name]["spec"]["template"]["spec"]


def test_every_required_object_is_there():
    # Requirements: Deployment, Service, ConfigMap, Secret, PV, PVC, probes, limits, scaling
    for kind in (
        "Namespace",
        "ConfigMap",
        "PersistentVolume",
        "PersistentVolumeClaim",
        "Deployment",
        "Service",
    ):
        assert kind in BY_KIND, kind
    assert {"HorizontalPodAutoscaler", "PodDisruptionBudget"} <= set(BY_KIND)
    assert set(DEPLOYMENTS) == {"lms-api", "lms-dashboard"}


def test_kustomization_lists_every_manifest_and_no_secret():
    on_disk = {p.name for p in FOLDER.glob("*.yaml")} - {"kustomization.yaml"}
    assert on_disk == set(KUSTOMIZATION["resources"])
    assert "Secret" not in BY_KIND  # real secrets never go into Git (kubectl create secret ...)


@pytest.mark.parametrize("name", ["lms-api", "lms-dashboard"])
def test_containers_are_probed_limited_and_hardened(name):
    spec = pod(name)
    assert spec["securityContext"]["runAsNonRoot"] is True and spec["securityContext"]["runAsUser"] == 10001
    for c in spec["containers"]:
        assert c["readinessProbe"] and c["livenessProbe"]
        assert c["resources"]["requests"]["cpu"] and c["resources"]["limits"]["memory"]
        sc = c["securityContext"]
        assert (
            sc["readOnlyRootFilesystem"]
            and not sc["allowPrivilegeEscalation"]
            and sc["capabilities"]["drop"] == ["ALL"]
        )
    for c in spec["initContainers"]:
        assert c["resources"]["limits"]["memory"] and c["securityContext"]["capabilities"]["drop"] == ["ALL"]


@pytest.mark.parametrize("name", ["lms-api", "lms-dashboard"])
def test_settings_and_secrets_come_from_the_configmap_and_secret(name):
    for c in pod(name)["initContainers"][1:] + pod(name)["containers"]:
        sources = {next(iter(s.values()))["name"] for s in c["envFrom"]}
        assert sources == {"lms-config", "lms-secrets"}
    prepare = {e["name"]: e["value"] for e in pod(name)["initContainers"][1]["env"]}
    main = {e["name"]: e["value"] for e in pod(name)["containers"][0]["env"]}
    assert prepare["PREPARE_ON_START"] == "true" and main["PREPARE_ON_START"] == "false"


@pytest.mark.parametrize("name", ["lms-api", "lms-dashboard"])
def test_volume_sub_folders_exist_and_match_the_settings(name):
    spec = pod(name)
    created = set(re.findall(r"/volume/(\w+)", spec["initContainers"][0]["args"][0]))
    mounts = {m["mountPath"]: m.get("subPath") for m in spec["containers"][0]["volumeMounts"]}
    assert {s for s in mounts.values() if s} <= created
    assert mounts["/app/data/db"] == "db" and CONFIG["DATABASE_URL"] == "sqlite:///./data/db/lms_ai.db"
    assert CONFIG["USERS_FILE"].startswith("data/accounts/") and CONFIG["AUDIT_LOG_FILE"].startswith("logs/")
    assert {"/app/vector_store", "/app/models", "/app/data/uploads", "/app/mlruns"} <= set(mounts)
    assert spec["volumes"][0]["persistentVolumeClaim"]["claimName"] == "lms-data"


def test_claim_binds_to_the_volume():
    pv, pvc = BY_KIND["PersistentVolume"][0], BY_KIND["PersistentVolumeClaim"][0]
    assert pvc["spec"]["volumeName"] == pv["metadata"]["name"]
    assert pvc["spec"]["storageClassName"] == pv["spec"]["storageClassName"]
    assert pvc["spec"]["resources"]["requests"]["storage"] == pv["spec"]["capacity"]["storage"]


@pytest.mark.parametrize("service", ["lms-api", "lms-dashboard"])
def test_services_select_their_pods(service):
    svc = next(s for s in BY_KIND["Service"] if s["metadata"]["name"] == service)
    labels = DEPLOYMENTS[service]["spec"]["template"]["metadata"]["labels"]
    assert svc["spec"]["selector"].items() <= labels.items()
    port_names = {p["name"] for p in pod(service)["containers"][0]["ports"]}
    assert svc["spec"]["ports"][0]["targetPort"] in port_names


def test_api_scales_and_stays_available():
    hpa = BY_KIND["HorizontalPodAutoscaler"][0]["spec"]
    assert hpa["scaleTargetRef"]["name"] == "lms-api" and 2 <= hpa["minReplicas"] < hpa["maxReplicas"]
    strategy = DEPLOYMENTS["lms-api"]["spec"]["strategy"]["rollingUpdate"]
    assert strategy["maxUnavailable"] == 0
    pdb = BY_KIND["PodDisruptionBudget"][0]["spec"]
    assert (
        pdb["selector"]["matchLabels"].items()
        <= DEPLOYMENTS["lms-api"]["spec"]["selector"]["matchLabels"].items()
    )


def test_configmap_holds_valid_non_secret_settings():
    assert set(CONFIG) <= FIELDS, set(CONFIG) - FIELDS
    assert not {"AUTH_SECRET_KEY", "BOOTSTRAP_ADMIN_PASSWORD", "ADMIN_API_KEY"} & set(CONFIG)
    settings = Settings(**{k.lower(): v for k, v in CONFIG.items()}, auth_secret_key="s" * 48)
    assert settings.app_profile == "kubernetes" and settings.check_security() == []


def test_secret_template_has_placeholders_only():
    lines = [
        ln for ln in (FOLDER / "secret.example.env").read_text().splitlines() if ln and not ln.startswith("#")
    ]
    values = dict(line.split("=", 1) for line in lines)
    assert set(values) <= FIELDS and all(v.startswith("replace-with") for v in values.values())
