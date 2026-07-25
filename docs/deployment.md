# Deployment Guide

Deploy DevOps Chatbot v2.0 with **Docker → GHCR → Argo CD/Helm**. Prefer GitOps over imperative `kubectl apply` for ongoing delivery.

**Baseline tag:** `faiss-202607`.

## Recommended path (GitOps)

1. Build/push image (CI on `main` or local build).  
2. Ensure cluster secrets exist.  
3. Bootstrap Argo CD apps (once).  
4. Let Argo CD reconcile `helm/devops-chatbot` and sibling charts.

Full bootstrap and Image Updater notes: **[argocd-gitops.md](argocd-gitops.md)**.

### One-time Argo CD

```bash
kubectl apply -n argocd -f argocd/projects/bookish-octo-robot.yaml
kubectl apply -n argocd -f argocd/bootstrap/root-app.yaml
```

### Runtime secrets

```bash
kubectl create namespace devops-chatbot --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot

kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<user> \
  --docker-password=<token> \
  -n devops-chatbot
```

## Docker image

```bash
DOCKER_BUILDKIT=1 docker build -t ghcr.io/pandew-home/bookish-octo-robot:local .
```

Production tags are **git SHAs** (`ghcr.io/pandew-home/bookish-octo-robot:<40-char-sha>`). Avoid pinning production to `latest`.

## Helm (without Argo CD)

Useful for smoke tests:

```bash
helm upgrade --install devops-chatbot ./helm/devops-chatbot \
  -n devops-chatbot --create-namespace \
  --set image.tag=<git-sha> \
  --set llm.createSecret=false \
  --set llm.existingSecret=devops-chatbot-secrets
```

Source values: `helm/devops-chatbot/values.yaml` (ingress host/path, resources, PVC, CORS, LLM secret ref).

### Ingress alignment

Keep these consistent when changing host or path:

| Setting | Purpose |
|---------|---------|
| `ingress.host` / `ingress.path` | External URL (chart default path `/chatbot`) |
| `ingress.extraPaths` | `/api`, `/static`, favicon, manifest |
| `app.apiBaseUrl` | Usually `/api` for root-built image |
| `app.publicUrl` | Usually `/` unless frontend rebuilt for subpath assets |
| `app.allowedOrigins` | CORS; include scheme+host (+ path origin if needed) |

`k8s/ingress.yaml` may lag the chart — treat **Helm values + Argo Application** as authoritative.

## Legacy raw manifests

```bash
kubectl apply -f k8s/
```

Still present for reference/emergency. Prefer `helm/` + Argo CD. Port-forward example:

```bash
kubectl port-forward -n devops-chatbot svc/devops-chatbot 8080:80
# http://localhost:8080
```

## GitHub Actions

Workflow: `.github/workflows/deploy.yml`

| Job area | Behavior |
|----------|----------|
| detect / build / test | CI; push image to GHCR |
| deploy / smoke | Optional; `direct_deploy` is emergency-oriented |
| k8sgpt workflows | Separate deploy helpers under `.github/workflows/` |

Do not assume Actions is the only deployer — **Argo CD is steady state**.

## Environment variables

### Required (runtime)

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` (or secret key in `devops-chatbot-secrets`) | LLM provider key |
| `DEFAULT_REGION` | Default AWS region for STS/EKS |

### Common optional

| Variable | Description | Notes |
|----------|-------------|--------|
| `LLM_PROVIDER` | `openai`, `openrouter`, `anthropic`, … | Chart/secret |
| `LLM_MODEL` | Model id | Chart/secret |
| `KB_SEEDING_ENABLED` | Seed KB on startup | default often true |
| `KB_FORCE_RESEED` | Force reseed | |
| `DATA_ROOT` / FAISS paths | Index and KB locations on PVC | |
| `IN_CLUSTER_EKS_CLUSTER_NAME` | Target cluster name | Single-cluster mode |
| `EKS_CLUSTER_NAME` | Fallback target name | Same |
| `ALLOWED_ORIGINS` / chart `app.allowedOrigins` | CORS | Must match browser origin |
| `REACT_APP_API_URL` / `app.apiBaseUrl` | API base for UI | |
| `DEBUG` / `LOG_LEVEL` | Logging | |

### Auth session behavior

- Credential APIs set HttpOnly cookie `session_id` (1h).  
- APIs also accept legacy `X-Session-Id` header.  
- Logout/delete clears cookie when credentials are removed.

## Pre-deploy checklist

- [ ] Secrets created (LLM, GHCR pull, K8sGPT AI)  
- [ ] Argo CD project + root app healthy  
- [ ] Ingress host/path/CORS match the real URL  
- [ ] Image tag is a real SHA present in GHCR  
- [ ] Security checklist: [security.md](security.md)  
- [ ] K8sGPT Results visible: `kubectl get results.core.k8sgpt.ai -A`

## Troubleshooting

### Invalid credentials

- Refresh Kion temporary keys; confirm region; STS must succeed.

### No clusters / 403 on target cluster

- Check `eks:ListClusters` and describe/auth for the target.  
- If single-cluster env is set, credentials must reach that cluster’s API.

### Weather empty

- K8sGPT operator/instance running; Results exist; RBAC allows read of Result CRDs.

### KB / FAISS empty

- PVC mounted; seeding logs; `KB_SEEDING_ENABLED=true`; index path writable.

### UI calls wrong host / CORS errors

- Realign `ingress.*`, `app.apiBaseUrl`, `app.publicUrl`, `allowedOrigins` and redeploy.

### Image change not visible

- Confirm SHA tag pulled (Image Updater / Helm values); avoid sticky old pods with failed pulls; check `imagePullSecrets`.

## Related

- [Argo CD GitOps](argocd-gitops.md) · [K8sGPT setup](k8sgpt-setup.md) · [Architecture](architecture.md)
