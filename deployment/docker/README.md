# deployment/docker (Phase 18)

| File | Use |
| --- | --- |
| `compose.prod.yaml` | Override for servers other people reach: login on, `APP_ENV=production`, `AUTH_SECRET_KEY` required |

```powershell
docker compose -f compose.yaml -f deployment/docker/compose.prod.yaml config   # see the merged result
docker compose -f compose.yaml -f deployment/docker/compose.prod.yaml up -d
```

The main `Dockerfile` and `compose.yaml` are in the project root. Full guide: `docs/DOCKER_GUIDE.md`.
