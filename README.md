# DevOps Chatbot v2.0

A Kubernetes-native troubleshooting assistant with real-time cluster health monitoring, RAG-powered chat, and a shared team knowledge base. Uses Kion AWS credentials for authentication and K8sGPT Operator for automated cluster diagnostics.

## Features

- **Simplified Authentication** — Kion temporary credentials for both K8s and AWS APIs
- **Real-Time Health Monitoring** — Weather widget driven by K8sGPT diagnostics
- **RAG-Powered Chat** — Semantic search over team knowledge base
- **Multi-Cluster Support** — One deployment, multiple EKS clusters
- **Scaling Detection** — HPA and Node analyzer integration via K8sGPT

## Quick Start

### Local Development

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ../libs/devops-k8s -e ../libs/devops-kb -e ../libs/devops-prompts -e ../libs/devops-rag
uvicorn app:app --reload --port 8000

# Frontend
cd frontend
npm install && npm start
```

Copy `.env.example` to `.env` and set `LLM_API_KEY` and `DEFAULT_REGION`.

### Kubernetes Deployment

```bash
kubectl create namespace devops-chatbot
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openai \
  --from-literal=llm-model=gpt-4o-mini \
  -n devops-chatbot
kubectl apply -f k8s/
```

### K8sGPT Operator

```bash
# Create API key secret
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system

# Deploy operator via ArgoCD
kubectl apply -f k8sgpt/Alloy/argocd-application.yaml

# Deploy K8sGPT instance + supporting resources
kubectl apply -f k8sgpt/namespace.yaml
kubectl apply -f k8sgpt/rbac.yaml
kubectl apply -f k8sgpt/k8sgpt-openrouter-cr.yaml

# Setup Alloy + Grafana integration (AUTOMATED VIA GITHUB ACTIONS)
# For manual setup, see k8sgpt/Alloy/ALLOY_INTEGRATION.md
# Recommendation: Use GitHub Actions workflows instead (deploy-k8sgpt.yml)
# which handle: Helm chart installation, datasource registration, dashboard import
```

See [K8sGPT + Alloy Integration](k8sgpt/Alloy/ALLOY_INTEGRATION.md) for full setup details.

## Architecture

```text
User → Frontend (React) → Backend (FastAPI)
                               ├── Kion/STS → EKS bearer token
                               ├── K8sGPT Result CRDs
                               ├── RAG engine (FAISS + LLM)
                               └── Knowledge base (PVC)

K8sGPT Operator (per cluster)
    └── Analyzes: Pod, Deployment, Node, HPA, PVC, Service, Ingress
    └── Interval: 2 minutes, noCache: true

Grafana Alloy → Loki → Grafana dashboard at http://cluster-host/grafana (Traefik subpath)
CronJob → deletes Results older than 24h
```

## Documentation

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)
- [Flux GitOps Setup](docs/flux-gitops.md)
- [K8sGPT Setup](docs/k8sgpt-setup.md)
- [K8sGPT + Alloy Integration](k8sgpt/Alloy/ALLOY_INTEGRATION.md)
- [Security](docs/security.md)
- [Usage](docs/usage.md)

## Endpoints

### Ingresses by Cluster

#### Civo Staging (2nd Stage Testing)
- **DevOps Chatbot:** `http://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com` (Traefik)
  - Backend: `devops-chatbot:80` → Pods: `10.0.1.18:8080`, `10.0.0.169:8080`
- **Grafana:** `http://grafana.k8s.civo.com` (Traefik)
  - Credentials: see Vault / k8s secret
- **Prometheus:** ClusterIP only (port-forward to access)

### Local Development
- **Frontend:** `http://localhost:3000`
- **Backend API:** `http://localhost:8000`
- **API Docs:** `http://localhost:8000/docs`
- **DevOps Chatbot (Port-Forward):** `kubectl port-forward svc/devops-chatbot 8080:80 -n devops-chatbot`
- **Grafana (Port-Forward):** `kubectl port-forward svc/prometheus-grafana 30300:80 -n monitoring`

## Testing

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test -- --no-watch

# K8sGPT integration (apply test Result CRD)
kubectl apply -f k8sgpt/test-hpa-result-cr.yaml
kubectl get results.core.k8sgpt.ai --all-namespaces
```
