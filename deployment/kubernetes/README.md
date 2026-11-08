# deployment/kubernetes (Phase 20)

Kubernetes manifests for Minikube. Apply them all with `kubectl apply -k deployment/kubernetes`.

| File | Object |
| --- | --- |
| `kustomization.yaml` | The list of manifests and the image tag |
| `namespace.yaml` | Namespace `lms-skills` |
| `configmap.yaml` | Non-secret settings |
| `secret.example.env` | Template for the Secret: copy to `secret.env` (git-ignored), then `kubectl create secret generic lms-secrets --from-env-file=...` |
| `persistent-volume.yaml` | PersistentVolume + PersistentVolumeClaim |
| `api-deployment.yaml`, `api-service.yaml`, `api-hpa.yaml`, `api-pdb.yaml` | FastAPI: 2–4 replicas, Service, autoscaler, disruption budget |
| `dashboard-deployment.yaml`, `dashboard-service.yaml` | Streamlit dashboard |

Step by step: `docs/KUBERNETES_GUIDE.md`.
