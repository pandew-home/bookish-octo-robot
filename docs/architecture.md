# Architecture

DevOps Chatbot v2.0 separates **continuous cluster diagnostics** (K8sGPT) from the **user-facing assistant** (React + FastAPI + Vestige memory), delivered via **Argo CD + Helm**.

## System overview

```
┌────────────────────────────────────────────────────────────┐
│  Target cluster(s)                                         │
│                                                            │
│  K8sGPT Operator + Instance  →  Result CRDs (periodic)     │
│  Grafana Alloy → Loki → Grafana (observability)            │
│  Argo CD reconciles apps from this git repo                │
│  ┌─ devops-chatbot (Helm, single image) ────────────────┐  │
│  │  static React UI + FastAPI (agentic tools)           │  │
│  │  colocated Vestige MCP (supervisord → :3928)         │  │
│  │  kubeApi policy layer (authorize + redact)           │  │
│  │  PVC /data → conversations + /data/vestige           │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────┬───────────────────────────────┘
                             │ LLM provider
                             ▼
                    External model API
```

Users authenticate with **Kion temporary AWS credentials** and/or kubeconfig. The backend stores credentials **in memory** with TTL, binds them to a **session id** (HttpOnly cookie and/or `X-Session-Id`), and uses STS + EKS token flows (or kubeconfig) for the Kubernetes API.

### Single-cluster vs multi-cluster

- **Multi-cluster (default):** discover EKS clusters credentials can list; user picks a target.
- **Single-cluster:** set `IN_CLUSTER_EKS_CLUSTER_NAME` or `EKS_CLUSTER_NAME`. Login verifies access; listing is filtered/defaulted.

## Key components

### Frontend (`frontend/`)

React 18 + TypeScript SPA: auth forms, weather widget, chat UI; hooks for credentials/cluster/chat/weather; Playwright under `frontend/e2e/`.

### Backend (`backend/`)

| Area | Role |
|------|------|
| `api/credentials.py` | Validate/store creds; session cookie + header |
| `api/clusters.py` | Discover/switch clusters; single-cluster filter |
| `api/chat.py` | Chat entry; agent run; memory recall/ingest |
| `api/weather.py` | Health summary from K8sGPT Results |
| `agentic_engine.py` / `agent_tools.py` | Tool-using agent; kubeApi policy |
| `memory/` | MemoryPort + Vestige MCP client + scrub |
| `kube_policy/` | Authorize + redact wrapper for K8s API calls |
| `skills/` + `skills.py` | Skill packs (k8s-check, triage, …) |
| `prompts/system.md` | System prompt template |
| `rag_integration.py` | LLM client singleton |
| `k8sgpt_reader.py` / `weather_calculator.py` | Result CRDs → weather |
| `conversation_history.py` | Per-session/cluster history |

### Shared libraries (`libs/`)

- **devops-k8s** — cluster/client helpers  
- **devops-rag** — LLM client abstraction  

Local dev: editable installs from `backend/`. Production: root `Dockerfile`.

### GitOps (`argocd/` + `helm/`)

App-of-apps → numbered Applications (operator → instance → monitoring → alloy → chatbot). Image Updater can rewrite chatbot SHA. Raw `k8s/` manifests are legacy/reference.

### K8sGPT + observability

Operator + instance emit Result CRDs; Alloy extras (cleanup CronJob, scrapers); Grafana dashboards chart.

## Data flows

### Authentication

1. Submit Kion AWS fields or kubeconfig.  
2. Validate (STS or kubeconfig).  
3. Optional single-cluster access check.  
4. Session UUID; JSON `session_id` **and** HttpOnly cookie.  
5. Later requests: cookie and/or `X-Session-Id`.

### Cluster selection

List (filtered in single-cluster mode) → on select, EKS bearer or kubeconfig context → cache clients → conversation context switches with cluster.

### Health (weather)

Frontend polls weather API → backend reads Result CRDs → calculator maps severity → UI icon/status.

### Chat (agentic)

1. Query → `AgentEngine` with K8s tools, skills, K8sGPT summary, Vestige recall.  
2. Default observe/diagnose; mutations gated by **kubeApi policy** + user creds.  
3. Free-text recommendations always allowed.  
4. Response per `prompts/system.md`.  
5. History updated; durable turns auto-ingest memory.

### Vestige memory

1. Binary baked into image; supervisord on `127.0.0.1:3928`.  
2. SQLite + embedding cache on PVC `/data/vestige`.  
3. Recall every turn; durable turns ingest.  
4. `MEMORY_BACKEND=vestige` (chart default) or `noop`. Unset → factory `noop` for safe local boot.

## API errors

```json
{
  "error": {
    "code": "rbac_forbidden",
    "message": "User-facing sentence.",
    "details": null,
    "request_id": "a1b2c3d4",
    "recoverable": true
  },
  "detail": "User-facing sentence."
}
```

- `X-Request-Id` on every response.  
- Chat soft failures stay **HTTP 200** with `errors[]`.  
- Recoverable chat errors keep history (rephrase without re-login).

## Security (summary)

- Temporary creds only; TTL store; no long-lived AWS keys in app.  
- HttpOnly session cookie; header still supported.  
- Pod: non-root, drop caps, seccomp.  
- Secrets out of band.  
- **kubeApi policy** chokepoint: mutate-off, GET-oriented, Secret identify-only by default.  
- Recommendations not gated — only mutation execution.  
- Pod SA: **K8sGPT Result CRDs only**; live diagnostics use per-session user clients.

See [security.md](security.md).

## Scalability

- UI/API largely stateless except in-memory creds/conversation cache — multi-replica needs sticky sessions or external store (not default).  
- Vestige colocated: prefer `replicaCount: 1`.  
- Resources in `helm/devops-chatbot/values.yaml`.

## Related

- [Deployment](deployment.md) · [Development](development.md) · [Usage](usage.md)
