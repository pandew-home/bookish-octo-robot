# Usage Guide

How to use DevOps Chatbot v2.0 for Kubernetes troubleshooting.

## Getting started

### 1. Authentication

1. Open the app URL (cluster ingress, e.g. `http://<host>/chatbot`, or local http://localhost:3000).  
2. Sign in with **Kion temporary AWS credentials** (access key, secret, session token, region) **or** kubeconfig upload + context.  
3. On success the API:
   - Validates credentials (STS or kubeconfig)
   - Optionally checks access to a configured target cluster (`IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`)
   - Returns a `session_id` and sets an **HttpOnly** `session_id` cookie (header `X-Session-Id` still works for API clients)

Credentials live in server memory with a **~1 hour TTL**. Re-authenticate when expired.

### 2. Cluster selection

- **Multi-cluster:** choose a cluster from the list (EKS discovery or kubeconfig contexts).  
- **Single-cluster deployments:** the list may show only the configured target; if none match, you get a clear access error.

Selecting a cluster configures the Kubernetes API client (EKS bearer token or kubeconfig) for subsequent weather and chat calls.

## Features

### Health monitoring (weather widget)

Status is derived from **K8sGPT Result CRDs** (not a separate metrics product):

| Icon | Meaning (approx.) |
|------|-------------------|
| Sunny | No critical issues |
| Partly cloudy | Few low-severity issues |
| Cloudy | Moderate volume/severity |
| Rainy | Elevated issues |
| Stormy | Many issues or high severity |

Poll interval is on the order of a minute. Empty weather usually means operator not installed, no Results, or RBAC.

### Chat troubleshooting

1. Ask a natural-language question about the **currently selected** cluster.  
2. The backend agent may:
   - Read live Kubernetes API state (tooling)
   - Use K8sGPT findings as supporting signal
   - Search the FAISS knowledge base
   - Load **skills** (e.g. networking/rbac/workload triage, k8s-check)
3. Responses follow the system prompt structure: live assessment, root cause hypothesis, remediation.

#### Mutations and approval

The assistant is **not** free-fire admin:

- Default posture is diagnose / observe.  
- Mutating Kubernetes API actions require **explicit user approval** in the product flow (and still must be allowed by cluster RBAC).  
- Prefer GitOps/IaC remediations when advising production changes.

### Knowledge base

- Save useful answers via **Save to KB** (metadata + content).  
- Entries feed semantic search for later chats (FAISS on shared PVC in cluster).

### Switching clusters

Changing the selector refreshes the API client and conversation context for that cluster (where history is scoped).

## Example queries

- "Why is my pod crashing?" / "Pods in CrashLoopBackOff in namespace X"  
- "What did K8sGPT find for Deployments?"  
- "Is the HPA scaling correctly for service Y?"  
- "Summarize node pressure and recent events"  
- "Show NetworkPolicy / Service endpoints for app Z"  

## Local vs cluster URLs

| Mode | Typical URL |
|------|-------------|
| Local frontend | http://localhost:3000 |
| Local API | http://localhost:8000/docs |
| In-cluster (chart defaults) | `http://<ingress.host>/chatbot` with API under `/api` |

Exact host/path come from `helm/devops-chatbot/values.yaml` / Argo CD values — they change per environment.

## Troubleshooting (end user)

| Symptom | What to try |
|---------|-------------|
| Login fails | New Kion session; correct region; clock skew |
| No clusters | IAM/EKS permissions; single-cluster env mismatch |
| Weather empty | Ask admin to verify K8sGPT Results CRDs |
| Chat 401 | Re-login; cookie blocked? try same-site origin |
| CORS / blank API | Wrong origin vs `allowedOrigins`; path mismatch |

Admin-oriented deploy issues: [deployment.md](deployment.md).
