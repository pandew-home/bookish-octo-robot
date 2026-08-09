# Usage

Kubernetes troubleshooting with DevOps Chatbot v2.0.

## Getting started

### 1. Authentication

1. Open the app (cluster ingress, e.g. `http://<host>/chatbot`, or local http://localhost:3000).  
2. Sign in with **Kion temporary AWS credentials** or kubeconfig + context.  
3. On success the API validates creds, optionally checks the configured target cluster, returns `session_id`, and sets an **HttpOnly** cookie (`X-Session-Id` still works for API clients).

Credentials live in server memory (~1 hour TTL). Re-authenticate when expired.

### 2. Cluster selection

- **Multi-cluster:** pick from the list (EKS discovery or kubeconfig contexts).  
- **Single-cluster:** list may show only the configured target.

Selection configures the API client for weather and chat.

## Features

### Weather widget

Status from **K8sGPT Result CRDs** (poll ~1 minute):

| Icon | Meaning (approx.) |
|------|-------------------|
| Sunny | No critical issues |
| Partly cloudy | Few low-severity issues |
| Cloudy | Moderate |
| Rainy | Elevated |
| Stormy | Many / high severity |

Empty weather → operator missing, no Results, or RBAC.

### Chat

1. Ask about the **currently selected** cluster.  
2. Agent may use live API tools, K8sGPT findings, Vestige recall, and skills.  
3. Responses: live assessment, root-cause hypothesis, remediation.  
4. Memory is **automatic** (no manual "Save to KB"; that path returns 410).

**Mutations:** default observe/diagnose. Execution gated by kubeApi policy + user RBAC. Free-text recommendations always allowed. Prefer GitOps/IaC for production fixes.

### Switching clusters

Selector refreshes the API client and conversation context for that cluster.

## Example queries

- "Why is my pod crashing?" / CrashLoopBackOff in namespace X  
- "What did K8sGPT find for Deployments?"  
- "Is the HPA scaling correctly for service Y?"  
- "Summarize node pressure and recent events"  
- "Show NetworkPolicy / Service endpoints for app Z"

## URLs

| Mode | Typical URL |
|------|-------------|
| Local frontend | http://localhost:3000 |
| Local API | http://localhost:8000/docs |
| In-cluster | `http://<ingress.host>/chatbot` with API under `/api` |

Host/path from Helm/Argo values per environment.

## Troubleshooting (end user)

| Symptom | Try |
|---------|-----|
| Login fails | New Kion session; region; clock skew |
| No clusters | IAM/EKS permissions; single-cluster env mismatch |
| Weather empty | Admin: K8sGPT Results CRDs |
| Chat 401 | Re-login; cookie/same-site origin |
| CORS / blank API | Origin vs `allowedOrigins`; path mismatch |

Deploy issues: [deployment.md](deployment.md).
