# deployment – environment-specific deployment files

| Folder | Holds | Phase |
| --- | --- | --- |
| `docker/` | Production Compose override and Docker notes | 18 |
| `kubernetes/` | Minikube manifests: Deployments, Services, ConfigMap, Secret template, PV + PVC, HPA, PDB (**done**) | 20 |
| `cloud/` | Public demo deployment configuration | 19 |

The main `Dockerfile` and `compose.yaml` stay in the project root so `docker compose up` works from there.
