# Deployment

Docker → GHCR → **Argo CD + Helm**. Prefer GitOps over imperative `kubectl apply`.

## GitOps layout

```
argocd/
  projects/bookish-octo-robot.yaml   # AppProject
  bootstrap/root-app.yaml            # App-of-apps root
  apps/
    00-k8sgpt-operator.yaml
    10-k8sgpt-instance.yaml
    20-kube-prometheus-stack.yaml
    30-alloy.yaml
    35-alloy-extras.yaml
    40-grafana-dashboards.yaml
    50-devops-chatbot.yaml           # Chatbot + Image Updater annotations
helm/
  devops-chatbot/
  k8sgpt-instance/
  alloy-extras/
  grafana-dashboards/
```

Root app watches `argocd/apps` on `main` with prune/selfHeal. **Flux is retired** — do not reintroduce a `flux/` tree.

## Bootstrap (once)

Prerequisites: Argo CD installed; repo readable by Argo CD; `kubectl` context set.

```bash
kubectl apply -n argocd -f argocd/projects/bookish-octo-robot.yaml
kubectl apply -n argocd -f argocd/bootstrap/root-app.yaml

kubectl create namespace devops-chatbot --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=<api-key> \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<ghcr-read-token> \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -
```

K8sGPT AI secret (before instance is healthy) — see [k8sgpt-setup.md](k8sgpt-setup.md).

```bash
kubectl get applications -n argocd
kubectl get pods -n devops-chatbot
```

## Image updates

- Image: `ghcr.io/pandew-home/bookish-octo-robot`
- Prefer **40-char git SHA** tags (not `latest`)
- Image Updater writes SHA into `argocd/apps/50-devops-chatbot.yaml` (needs updater + git write creds + GHCR pull)

```bash
DOCKER_BUILDKIT=1 docker build -t ghcr.io/pandew-home/bookish-octo-robot:local .
```

| Path | Role |
|------|------|
| `.github/workflows/deploy.yml` | CI: build/test/push GHCR |
| Argo CD + Image Updater | Steady-state CD |
| `workflow_dispatch` `direct_deploy=true` | Emergency only |

## Helm (smoke test without Argo)

```bash
helm upgrade --install devops-chatbot ./helm/devops-chatbot \
  -n devops-chatbot --create-namespace \
  --set image.tag=<git-sha> \
  --set llm.createSecret=false \
  --set llm.existingSecret=devops-chatbot-secrets
```

### Ingress alignment

Keep these consistent when changing host/path:

| Setting | Purpose |
|---------|---------|
| `ingress.host` / `ingress.path` | External URL (default path `/chatbot`) |
| `ingress.extraPaths` | `/api`, `/static`, favicon, manifest |
| `app.apiBaseUrl` | Usually `/api` |
| `app.publicUrl` | Usually `/` unless SPA rebuilt for subpath |
| `app.allowedOrigins` | CORS; scheme+host of the real UI |

`k8s/` raw manifests are **legacy/reference** — Helm + Argo are authoritative.

```bash
kubectl port-forward -n devops-chatbot svc/devops-chatbot 8080:80
# http://localhost:8080
```

## Config changes

1. Edit `helm/<chart>/values.yaml` or Application CR values.
2. Keep ingress, `apiBaseUrl`/`publicUrl`, and `allowedOrigins` aligned.
3. PR → `main`; Argo self-heals.

## Environment variables

### Required

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` (or secret key) | LLM provider key |
| `DEFAULT_REGION` | Default AWS region for STS/EKS |

### Common optional

| Variable | Description | Notes |
|----------|-------------|--------|
| `LLM_PROVIDER` / `LLM_MODEL` | Provider and model id | Chart/secret |
| `MEMORY_BACKEND` | `noop` \| `vestige` | Chart default `vestige`; unset → code `noop` |
| `VESTIGE_HTTP_URL` | Local Vestige MCP | Default `http://127.0.0.1:3928` |
| `VESTIGE_DATA_DIR` | SQLite on PVC | Default `/data/vestige` |
| `FASTEMBED_CACHE_PATH` | Embedding cache | Default `/data/vestige/model-cache` |
| `DATA_ROOT` | Chatbot data root | Conversations + Vestige under `/data` |
| `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME` | Single-cluster pin | |
| `ALLOWED_ORIGINS` / `app.allowedOrigins` | CORS | Must match browser origin |
| `REACT_APP_API_URL` / `app.apiBaseUrl` | UI API base | |
| `DEBUG` / `LOG_LEVEL` | Logging | |

Session: credential APIs set HttpOnly cookie `session_id` (1h); also accept `X-Session-Id`; logout clears cookie.

## Vestige (colocated)

Runs in the chatbot container (supervisord) on `127.0.0.1:3928`; data on PVC `/data/vestige`. Prefer `replicaCount: 1` (SQLite single-writer).

```bash
# Health
kubectl exec -n devops-chatbot deploy/devops-chatbot -- curl -s http://127.0.0.1:3928/health

# Backup
kubectl exec -n devops-chatbot deploy/devops-chatbot -- \
  tar czf - -C /data/vestige . > vestige-backup.tar.gz

# Wipe
kubectl exec -n devops-chatbot deploy/devops-chatbot -- rm -rf /data/vestige/*
kubectl rollout restart deployment/devops-chatbot -n devops-chatbot
```

`memory.backend=noop` skips MemoryPort→Vestige (process may still run).

## Pre-deploy checklist

- [ ] Secrets out of band (LLM, GHCR pull, K8sGPT AI)
- [ ] Argo project + root app healthy
- [ ] Ingress host/path/CORS match real URL
- [ ] Image tag is a real SHA in GHCR
- [ ] [Security checklist](security.md)
- [ ] K8sGPT Results: `kubectl get results.core.k8sgpt.ai -A`

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Invalid credentials | Refresh Kion keys; region; STS |
| No clusters / 403 | EKS list/describe/auth; single-cluster env pin |
| Weather empty | Operator/instance; Results exist; Result CRD RBAC |
| Memory degraded | Vestige logs in chatbot pod; PVC writable (fsGroup 1000); `memory_degraded` in chat metadata |
| CORS / wrong host | Realign `ingress.*`, `apiBaseUrl`, `publicUrl`, `allowedOrigins` |
| Image not updating | SHA in values; pull secret; Image Updater |

## Related

- [Architecture](architecture.md) · [K8sGPT setup](k8sgpt-setup.md) · [Security](security.md) · [Development](development.md)
