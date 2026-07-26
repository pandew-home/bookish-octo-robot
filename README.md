# DevOps Chatbot v2.0

Kubernetes-native troubleshooting assistant with real-time health signals (K8sGPT), **Vestige institutional memory**, and an agentic chat backend. Auth uses short-lived **Kion AWS** credentials (and/or kubeconfig). Delivery is **Argo CD + Helm** (Flux is retired).

**Repo:** https://github.com/pandew-home/bookish-octo-robot

## Features

- **Short-lived auth** — Kion STS credentials and/or kubeconfig; HttpOnly session cookie (+ `X-Session-Id`)
- **Health weather widget** — Driven by K8sGPT Result CRDs
- **Agentic chat** — Live Kubernetes API tools + skills; mutations gated by `kubeApi` policy + user RBAC
- **Vestige memory** — Colocated MCP in the chatbot image; data on the app PVC; automatic recall/ingest
- **Free recommendations** — Remediation advice always allowed; execution is policy-gated
- **Single- or multi-cluster** — Optional pin via `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`
- **GitOps** — Argo CD app-of-apps + Helm charts; images from GHCR by git SHA

## Quick start

### Local development

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e ../libs/devops-k8s -e ../libs/devops-rag
uvicorn app:app --reload --port 8000

# Frontend
cd frontend
npm install && npm start
```

Set `LLM_API_KEY` and `DEFAULT_REGION` (see [docs/development.md](docs/development.md)).

### Cluster (GitOps)

```bash
# Once: Argo CD project + root app
kubectl apply -n argocd -f argocd/projects/bookish-octo-robot.yaml
kubectl apply -n argocd -f argocd/bootstrap/root-app.yaml

# Secrets (not committed)
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot
```

Details: [docs/argocd-gitops.md](docs/argocd-gitops.md), [docs/deployment.md](docs/deployment.md).

### K8sGPT

Prefer Argo CD apps `00-k8sgpt-operator` / `10-k8sgpt-instance` and chart `helm/k8sgpt-instance`.  
See [docs/k8sgpt-setup.md](docs/k8sgpt-setup.md).

## Architecture (short)

```text
User → React UI → FastAPI (agent tools + MemoryPort)
                     ├── Session cookie / X-Session-Id
                     ├── Kion/STS → EKS API (or kubeconfig)
                     ├── K8sGPT Result CRDs
                     └── Vestige MCP (same image, loopback :3928, PVC /data/vestige)

Argo CD → helm/devops-chatbot (+ operator, alloy, grafana)
GHCR    → ghcr.io/pandew-home/bookish-octo-robot:<git-sha>
```

## Documentation

| Doc | Topic |
|-----|--------|
| [AGENTS.md](AGENTS.md) | Rules for AI coding agents |
| [docs/architecture.md](docs/architecture.md) | Design & data flows |
| [docs/development.md](docs/development.md) | Local dev & tests |
| [docs/deployment.md](docs/deployment.md) | Deploy, env, troubleshooting |
| [docs/argocd-gitops.md](docs/argocd-gitops.md) | App-of-apps GitOps |
| [docs/k8sgpt-setup.md](docs/k8sgpt-setup.md) | K8sGPT |
| [docs/security.md](docs/security.md) | Security |
| [docs/usage.md](docs/usage.md) | End-user usage |
