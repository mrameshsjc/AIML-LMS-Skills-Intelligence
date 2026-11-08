# Kubernetes Guide (Phase 20)

How to run the LMS Skills Intelligence Engine on **Kubernetes**, locally with **Minikube** on Windows 11. Every command is for **PowerShell**, run from the project folder.

| File (`deployment/kubernetes/`) | Kubernetes object | What it does |
| --- | --- | --- |
| `namespace.yaml` | Namespace `lms-skills` | Keeps all objects of the engine together |
| `configmap.yaml` | ConfigMap `lms-config` | Non-secret settings, as environment variables |
| *(you create it)* | Secret `lms-secrets` | `AUTH_SECRET_KEY`, admin password, admin key; from `secret.env`, never in Git |
| `persistent-volume.yaml` | PersistentVolume + PersistentVolumeClaim | Storage that survives restarts: database, index, uploads, models, MLflow, accounts, audit log |
| `api-deployment.yaml` | Deployment `lms-api` | FastAPI, 2 replicas, rolling updates, probes, limits |
| `api-service.yaml` | Service `lms-api` | One address for all API pods (NodePort 30800) |
| `api-hpa.yaml` | HorizontalPodAutoscaler | 2–4 API pods, by CPU use |
| `api-pdb.yaml` | PodDisruptionBudget | At least one API pod during maintenance |
| `dashboard-deployment.yaml`, `dashboard-service.yaml` | Deployment + Service `lms-dashboard` | Streamlit, 1 replica (NodePort 30501) |
| `kustomization.yaml` | – | Applies all of the above in one command; sets the image tag |

---

## 1. Docker vs Kubernetes

| | Docker / Docker Compose (Phase 18) | Kubernetes (this phase) |
| --- | --- | --- |
| What it is | Builds images and runs containers on **one** machine | Runs containers on a **cluster** of machines and keeps them in the state you describe |
| You say | "Start these containers" (`docker compose up`) | "There should be 2 healthy API pods, 1 dashboard, this storage" (`kubectl apply`) |
| A container crashes | `restart: unless-stopped` restarts it on that machine | A controller notices and replaces the pod, on any healthy node |
| Busy? | You change the number by hand | The **HorizontalPodAutoscaler** adds pods when CPU is high and removes them later |
| New version | Stop, rebuild, start (short outage) | **Rolling update**: new pods start and must pass the readiness probe before old ones stop; `rollout undo` goes back |
| Traffic | Fixed ports per container | A **Service** spreads traffic over all *ready* pods |
| Settings and secrets | `.env`, `environment:` | **ConfigMap** and **Secret** objects |
| Storage | Named volumes | **PersistentVolume** (the storage) + **PersistentVolumeClaim** (the request) |
| Health | One `healthcheck` | **Readiness** (may it get traffic?) and **liveness** (is it alive, or restart it?) probes |
| Good for | Development, a single server | Several servers, high availability, scaling, managed cloud (EKS, AKS, GKE) |

**The same image runs in both.** Kubernetes doesn't replace Docker images; it decides where and how many containers run, and keeps them that way. **Minikube** is a one-node Kubernetes inside Docker Desktop, for learning and testing on your PC.

## 2. Install (once)

Docker Desktop must be installed and running. Give it at least **4 CPUs and 6 GB of memory**: *Docker Desktop → Settings → Resources*.

```powershell
winget install Kubernetes.minikube
winget install Kubernetes.kubectl
# close and reopen PowerShell, then:
minikube version
kubectl version --client
```

## 3. Start Minikube

```powershell
minikube start --driver=docker --cpus=4 --memory=6144
minikube addons enable metrics-server     # CPU/memory figures for the autoscaler and `kubectl top`
kubectl get nodes                          # one node "minikube", STATUS Ready
```

## 4. Build the image inside Minikube

Minikube has its own image store. Build the image **into** it, so the pods find it without a registry:

```powershell
minikube image build -t aiml-lms-skills-intelligence:dev .
minikube image ls | Select-String aiml-lms-skills    # shows docker.io/library/aiml-lms-skills-intelligence:dev
```

The first build takes a few minutes; later builds reuse cached layers.

**Alternatives** (useful if `minikube image build` misbehaves):

```powershell
# build with Docker Desktop, then copy the image into Minikube
docker build -t aiml-lms-skills-intelligence:dev .
minikube image load aiml-lms-skills-intelligence:dev

# or: point this PowerShell window's docker command at Minikube's Docker, and build straight into it
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
docker build -t aiml-lms-skills-intelligence:dev .
```

## 5. Create the namespace and the Secret

```powershell
kubectl apply -f deployment/kubernetes/namespace.yaml
Copy-Item deployment/kubernetes/secret.example.env deployment/kubernetes/secret.env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as AUTH_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(16))"   # paste as BOOTSTRAP_ADMIN_PASSWORD (your admin password)
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste as ADMIN_API_KEY
notepad deployment/kubernetes/secret.env                        # replace the three placeholders, save
kubectl -n lms-skills create secret generic lms-secrets --from-env-file=deployment/kubernetes/secret.env
```

`secret.env` is git-ignored. Kubernetes stores the Secret separately from the manifests, and `kubectl describe secret` shows sizes, not values.

## 6. Deploy

```powershell
kubectl apply -k deployment/kubernetes
kubectl -n lms-skills get pods -w          # Ctrl+C when every pod is Running and READY 1/1
```

What you'll see (about 1–2 minutes the first time):

```
NAME                             READY   STATUS     RESTARTS
lms-api-7d9c8f6b5-abcde          0/1     Init:1/2   0      ← preparing the volume (database, index, model)
lms-api-7d9c8f6b5-fghij          0/1     Init:1/2   0      ← waits for the lock, then finds everything ready
lms-dashboard-5b8d7c9f4-klmno    0/1     Init:1/2   0
lms-api-7d9c8f6b5-abcde          1/1     Running    0      ← readiness probe passed: receives traffic
```

The start step's log:

```powershell
kubectl -n lms-skills logs deployment/lms-api -c prepare
```

## 7. Open it

Simplest, works with every Minikube driver. Keep each window open; ports 18000/18501 avoid ports that Windows often reserves or that local servers use:

```powershell
kubectl -n lms-skills port-forward service/lms-api 18000:80         # window 1 → http://127.0.0.1:18000/docs
kubectl -n lms-skills port-forward service/lms-dashboard 18501:80   # window 2 → http://127.0.0.1:18501
```

Or let Minikube open them through the NodePorts (on Windows with the Docker driver, keep the window open):

```powershell
minikube service lms-dashboard -n lms-skills
minikube service lms-api -n lms-skills --url
```

Check it:

```powershell
$adminKey = (Select-String -Path deployment\kubernetes\secret.env -Pattern '^ADMIN_API_KEY=').Line.Split('=',2)[1]
python scripts/api_smoke_test.py --base-url http://127.0.0.1:18000 --admin-key $adminKey
```

Visitors browse as guests; the admin logs in as `admin` with `BOOTSTRAP_ADMIN_PASSWORD`. The assistant uses Ollama on your PC (`host.minikube.internal`) when it is running, otherwise the labelled fallback.

## 8. Everyday operations

| Task | Command |
| --- | --- |
| Everything at a glance | `kubectl -n lms-skills get all,pvc,hpa` |
| Pod details and recent events (first stop when something is wrong) | `kubectl -n lms-skills describe pod <pod-name>` |
| Recent events in the namespace | `kubectl -n lms-skills get events --sort-by=.lastTimestamp` |
| Logs (all API pods / one pod / follow) | `kubectl -n lms-skills logs -l app.kubernetes.io/component=api --tail 50` · `kubectl -n lms-skills logs <pod> -f` |
| Logs of an init container | `kubectl -n lms-skills logs <pod> -c prepare` |
| A shell inside a pod | `kubectl -n lms-skills exec -it deployment/lms-api -- bash` |
| CPU and memory per pod | `kubectl -n lms-skills top pods` |
| Change settings | edit `configmap.yaml` → `kubectl apply -k deployment/kubernetes` → `kubectl -n lms-skills rollout restart deployment` |
| Restart pods (e.g. after a Secret change) | `kubectl -n lms-skills rollout restart deployment/lms-api` |
| Kubernetes dashboard (web UI) | `minikube dashboard` |

## 9. Scaling

**By hand:**

```powershell
kubectl -n lms-skills scale deployment/lms-api --replicas=3
kubectl -n lms-skills get pods -l app.kubernetes.io/component=api
```

The autoscaler then brings it back between 2 and 4 by CPU load. **Automatically (HPA):**

```powershell
kubectl -n lms-skills get hpa lms-api          # TARGETS: e.g. cpu: 3%/70%, REPLICAS: 2
# create load in a second window for a minute or two:
kubectl -n lms-skills run load --rm -it --image=busybox:1.36 --restart=Never -- `
  sh -c "while true; do wget -q -O- http://lms-api/api/v1/learning-path/E1001 >/dev/null; done"
kubectl -n lms-skills get hpa lms-api -w       # watch REPLICAS go up; after the load stops, back to 2
```

The load pod gets 429 answers once the per-pod rate limit (120/minute) is reached; that's still enough CPU load to show scaling. To see more, raise `RATE_LIMIT_PER_MINUTE` in the ConfigMap for the test.

**Why several API pods work:** all pods share the volume. The index and the current model are reloaded automatically when another pod changes them: each request checks the index's manifest and the current model version. The start step uses a lock, so only one pod builds.

## 10. Updating and rolling back

```powershell
minikube image build -t aiml-lms-skills-intelligence:v2 .
# in deployment/kubernetes/kustomization.yaml set: newTag: v2
kubectl apply -k deployment/kubernetes
kubectl -n lms-skills rollout status deployment/lms-api       # one new pod at a time, each must be ready
kubectl -n lms-skills rollout history deployment/lms-api
kubectl -n lms-skills rollout undo deployment/lms-api         # back to the previous version
```

With `maxUnavailable: 0` the API keeps serving during the update. A new version that never becomes ready (fails its readiness probe) stops the rollout, and the old pods keep running.

## 11. Stopping and cleaning up

```powershell
kubectl delete namespace lms-skills      # everything of the engine (pods, services, claim, secret)
kubectl delete pv lms-data-pv            # the volume object (Retain policy: removed only explicitly)
minikube ssh -- sudo rm -rf /data/lms-skills   # the stored data itself (database, index, models, ...)
minikube stop                            # pause the cluster (keeps everything for next time)
minikube delete                          # remove the cluster completely
```

## 12. Troubleshooting

| STATUS / symptom | Meaning and fix |
| --- | --- |
| `minikube image build`: "open Dockerfile: no such file or directory" | An older `.dockerignore` excluded the Dockerfile; use the Phase 20 version, or one of the alternatives in section 4 |
| `ErrImageNeverPull` / `ImagePullBackOff` | The image isn't inside Minikube: section 4 (`minikube image build ...`), and check the tag in `kustomization.yaml` |
| `CreateContainerConfigError` | The Secret `lms-secrets` is missing: section 5 |
| `Init:Error` / `Init:CrashLoopBackOff` | The start step failed: `kubectl -n lms-skills logs <pod> -c prepare` (or `-c volume-permissions`) |
| `Pending`, event "unbound PersistentVolumeClaim" | `kubectl get pv,pvc -n lms-skills`; the PV must be `Bound`. After deleting the namespace, delete and re-apply the PV (section 11) |
| `CrashLoopBackOff`, log "Unsafe security settings" | `AUTH_SECRET_KEY` shorter than 32 characters or the admin password shorter than 12: recreate the Secret (`kubectl -n lms-skills delete secret lms-secrets`, then section 5), `rollout restart` |
| `OOMKilled` | Over the memory limit: raise `limits.memory` in the deployment, or give Minikube more memory |
| Running but `READY 0/1` | The readiness probe fails: `kubectl -n lms-skills describe pod <pod>` (events) and the logs |
| HPA shows `<unknown>/70%` | `minikube addons enable metrics-server`, wait a minute |
| `port-forward` stops | It ends when its pod is replaced (e.g. after `rollout restart`); run it again |
| `port-forward`: "Only one usage of each socket address" | The port is in use (an old port-forward, a local uvicorn, or Docker Compose): stop it, or use another port |
| `port-forward`: "forbidden by its access permissions" | Windows reserves port ranges for WSL2/Hyper-V (often including 8080): use e.g. `18000:80`; `netsh interface ipv4 show excludedportrange protocol=tcp` lists them |
| Smoke test API 7 upload: 401 `ADMIN_AUTH_REQUIRED` with `--admin-key` | The Secret in the cluster has another key than your `secret.env` (often: created before the file was edited). Compare: `kubectl -n lms-skills exec deployment/lms-api -- printenv ADMIN_API_KEY`; recreate the Secret, then `rollout restart` |
| LLM WARN "Cannot reach Ollama at http://host.minikube.internal:11434 (Name or service not known)" | Some Minikube/Docker Desktop setups don't resolve that name inside pods. Optional: test `host.docker.internal` (`kubectl -n lms-skills exec deployment/lms-api -- python -c "import socket; print(socket.gethostbyname('host.docker.internal'))"`) and set it as `OLLAMA_BASE_URL` in the ConfigMap; otherwise the labelled fallback answers |

## 13. Limits of this setup

- **One node:** the volume is `ReadWriteOnce` (one node). A multi-node cluster needs `ReadWriteMany` storage (NFS, Azure Files, EFS) or a database server (MySQL, from the LMS integration project) instead of SQLite and files.
- **Rate limits per pod:** each replica counts its own requests; a shared store (Redis) would make them cluster-wide.
- **Dashboard has one replica:** Streamlit keeps sessions in memory; scaling it needs sticky sessions (an Ingress with session affinity).
- **No TLS/Ingress here:** port-forward and NodePorts are for local use. A cloud cluster would add an Ingress controller with HTTPS certificates.
- **Images are built into Minikube:** a real cluster pulls from a registry (GitHub Container Registry, Docker Hub); Phase 21 can publish the image from CI.
