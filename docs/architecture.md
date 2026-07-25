# Architecture

DevOps Chatbot v2.0 separates **continuous cluster diagnostics** (K8sGPT) from the **user-facing assistant** (React + FastAPI + FAISS RAG), delivered via **Argo CD + Helm**.

**Baseline:** tag `faiss-202607` on `main`.

## System overview

```
┌────────────────────────────────────────────────────────────┐
│  Target cluster(s) — e.g. Civo / EKS                        │
│                                                            │
│  K8sGPT Operator + Instance  →  Result CRDs (periodic)     │
│  Grafana Alloy → Loki → Grafana (observability path)       │
│  Argo CD (in-cluster) reconciles apps from this git repo   │
│                                                            │
│  ┌─ devops-chatbot (Helm) ──────────────────────────────┐  │
│  │  nginx + static React UI                             │  │
│  │  FastAPI backend (agentic tools + RAG)               │  │
│  │  PVC: knowledge base + FAISS index                   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────┬───────────────────────────────┘
                             │ LLM provider (OpenRouter / OpenAI / …)
                             ▼
                    External model API
```

Users authenticate with **Kion temporary AWS credentials** (and/or kubeconfig). The backend stores credentials **in memory** with TTL, associates them with a **session id** (HttpOnly cookie and/or `X-Session-Id` header), and uses STS + EKS token flows (or local kubeconfig) to talk to the Kubernetes API.

### Single-cluster vs multi-cluster

- **Default multi-cluster:** discover EKS clusters the credentials can list; user picks a target.
- **Single-cluster / in-cluster mode:** set `IN_CLUSTER_EKS_CLUSTER_NAME` or `EKS_CLUSTER_NAME`. Credential submit verifies API access to that cluster; listing is filtered or defaulted to one cluster.

## Key components

### Frontend (`frontend/`)

- React 18 + TypeScript SPA
- Auth forms (AWS / kubeconfig), weather widget, chat UI, solution save
- Hooks for credentials, cluster, chat, weather
- Playwright specs under `frontend/e2e/`

### Backend (`backend/`)

| Area | Role |
|------|------|
| `api/credentials.py` | Validate/store creds; session cookie + header |
| `api/clusters.py` | Discover/switch clusters; single-cluster filter |
| `api/chat.py` | Chat entry; agent run; mutation approval detection |
| `api/weather.py` | Health summary from K8sGPT Results |
| `api/solutions.py` | Knowledge base write path |
| `agentic_engine.py` / `agent_tools.py` | Tool-using agent; approval for mutations |
| `skills/` + `skills.py` | Skill packs (k8s-check, triage skills, …) |
| `prompts/system.md` | System prompt template (versioned in git) |
| `rag_integration.py` | KB/FAISS + LLM orchestration |
| `k8sgpt_reader.py` | Result CRD parsing |
| `weather_calculator.py` | Map findings → weather status |
| `conversation_history.py` | Per-session/cluster history |

### Shared libraries (`libs/`)

- **devops-k8s** — cluster/client helpers  
- **devops-kb** — knowledge base storage  
- **devops-rag** — embeddings / FAISS / LLM client pieces  

Local dev installs these editable from `backend/`. Production image installs or vendors as defined by the root `Dockerfile`.

### GitOps (`argocd/` + `helm/`)

- App-of-apps root → numbered Applications (operator → instance → monitoring → alloy → chatbot).
- Chatbot chart: deployment, service, ingress, PVC, PDB, resource quota, optional secret template (disabled by default).
- Image Updater can rewrite chatbot image SHA in the Application values.

Raw manifests under `k8s/` are **legacy/reference**; prefer Helm + Argo CD for new changes.

### K8sGPT + observability

- Operator + instance analyze resources on an interval and emit Result CRDs.
- Alloy extras include cleanup CronJob (`ttlSecondsAfterFinished` on jobs) and scraping helpers.
- Grafana dashboards chart packages K8sGPT-oriented dashboards.

## Data flows

### Authentication

1. User submits Kion AWS fields or kubeconfig content/context.  
2. Backend validates (STS or kubeconfig parse/auth).  
3. Optional target-cluster access check when single-cluster env is set.  
4. Session UUID stored; response includes `session_id` JSON **and** HttpOnly cookie.  
5. Later requests use cookie and/or `X-Session-Id`.

### Cluster selection

1. List clusters (filtered in single-cluster mode).  
2. On select, generate EKS bearer token (or use kubeconfig context) and cache clients.  
3. Conversation context switches with the selected cluster.

### Health (weather)

1. Frontend polls weather API.  
2. Backend reads K8sGPT Result CRDs for the active cluster.  
3. Weather calculator aggregates severity → UI icon/status.

### Chat (agentic)

1. User query → `AgentEngine` with K8s tools, skills, K8sGPT summary, KB hits.  
2. Default: observe/diagnose; mutating API calls require human approval phrases/path.  
3. Response structured per `prompts/system.md` (assessment, hypothesis, remediation).  
4. History updated for the session/cluster.

### Knowledge base

1. Solutions saved via API → PVC-backed store.  
2. FAISS index updated for semantic retrieval on later chats.

## Security architecture (summary)

- Temporary credentials only; TTL store; no long-lived AWS keys in the app.  
- Session cookie HttpOnly; header still supported for clients.  
- Pod: non-root, dropped caps, seccomp (see chart/templates).  
- Secrets out of band; chart does not embed API keys in git.  
- Mutation gated in product; cluster RBAC should still least-privilege the service account for production.

See [security.md](security.md).

## Scalability notes

- UI/API pods are largely stateless except **in-memory** credentials and conversation cache — multi-replica needs sticky sessions or external session/cred store (not default).  
- FAISS/KB on PVC: use `ReadWriteMany` (e.g. Longhorn) if scaling replicas.  
- Resource requests/limits tuned in `helm/devops-chatbot/values.yaml` for small co-tenant nodes.

## Related

- [Deployment](deployment.md) · [Argo CD GitOps](argocd-gitops.md) · [Development](development.md) · [Usage](usage.md)
