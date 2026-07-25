# DevOps Chatbot v2.0

Kubernetes-native troubleshooting assistant with real-time health signals (K8sGPT), **FAISS RAG** over a shared knowledge base, and an agentic chat backend. Auth uses short-lived **Kion AWS** credentials (and/or kubeconfig). Delivery is **Argo CD + Helm** (Flux is retired).

**Release pin:** git tag `faiss-202607` · **Repo:** https://github.com/pandew-home/bookish-octo-robot

## Features

- **Short-lived auth** — Kion STS credentials and/or kubeconfig; HttpOnly session cookie (+ `X-Session-Id`)
- **Health weather widget** — Driven by K8sGPT Result CRDs
- **Agentic chat** — Live Kubernetes API tools, skills, KB retrieval; mutations require explicit approval
- **FAISS knowledge base** — Shared PVC-backed index for team solutions
- **Single- or multi-cluster** — Optional pin via `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`
- **GitOps** — Argo CD app-of-apps + Helm charts; images from GHCR by git SHA

## Quick start

### Local development

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e ../libs/devops-k8s -e ../libs/devops-kb -e ../libs/devops-rag
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
User → React UI → FastAPI (agent tools + RAG)
                     ├── Session cookie / X-Session-Id
                     ├── Kion/STS → EKS API (or kubeconfig)
                     ├── K8sGPT Result CRDs
                     └── FAISS KB on PVC

Argo CD → helm/devops-chatbot (+ operator, alloy, grafana charts)
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
| [docs/README.md](docs/README.md) | Full index |

## Endpoints (typical)

| Mode | URL |
|------|-----|
| Local UI | http://localhost:3000 |
| Local API | http://localhost:8000/docs |
| Cluster | Host/path from `helm/devops-chatbot/values.yaml` (e.g. `/chatbot` + `/api`) |

Do not hardcode lab hostnames from older docs; values change per environment.

## Testing

```bash
cd backend && pytest
cd frontend && npm test -- --no-watch
# Optional: cd frontend && npx playwright test
```

## License

See [LICENSE](LICENSE).
