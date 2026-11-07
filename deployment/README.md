# deployment – environment-specific deployment files

| Folder | Holds | Phase |
| --- | --- | --- |
| `docker/` | Production Compose override and Docker notes | 18 |
| `kubernetes/` | Minikube manifests (Deployment, Service, ConfigMap, Secret, PVC) | 20 |
| `cloud/` | Public demo deployment configuration | 19 |

The main `Dockerfile` and `docker-compose.yml` stay in the project root so `docker compose up` works from there.
