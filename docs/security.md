# Security Guide

Security controls and practices for DevOps Chatbot v2.0.

## Security features

### Application authentication

- **Kion temporary AWS credentials** validated via STS; optional kubeconfig path.  
- Credentials held **in memory** with TTL (~3600s), not persisted to disk by default.  
- Session binding via **HttpOnly `session_id` cookie** and/or **`X-Session-Id` header**.  
- Optional **target cluster verification** on login when `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME` is set (rejects creds that cannot list/access that cluster).

### Agent / mutation controls

- Chat agent defaults to **observe and diagnose**.  
- Mutating Kubernetes API **execution** is gated by **kubeApi wrapper policy** (`backend/kube_policy/`): Helm/env defaults + user credentials. Default: `allowMutate: false`, GET-oriented methods.  
- Free-text **recommendations** (kubectl suggestions, remediation advice) are NOT gated by policy — only execution is controlled.  
- **Secret identify-only defaults:** wrappers MAY identify Secrets (list/metadata/key names) and MUST NOT return Secret values (`data`/`stringData`) to the agent unless policy explicitly allows read-data.  
- Cluster **RBAC** remains the hard boundary — the chatbot SA and user tokens must not be over-privileged.

### Institutional memory (Vestige)

Memory is **shared team knowledge** for cluster findings — not per-user private history.

| Scoped by | Not scoped by |
|-----------|----------------|
| Deployment / PVC (one Vestige store) | Individual `user_id` |
| Optional `cluster` metadata on recall/ingest | Multi-tenant user isolation (out of scope for MVP) |

Any authenticated user who can chat against a cluster may recall prior durable troubleshooting for that cluster. Secrets still scrubbed before ingest; conversation history remains separate (per `user_id` path on disk).

### ServiceAccount vs session clients

| Identity | Scope |
|----------|--------|
| Pod **ServiceAccount** (`devops-chatbot`) | **Only** `get`/`list`/`watch` on `core.k8sgpt.ai/results` (Helm `templates/rbac.yaml`). Reserved for host-local tooling; chat/weather use user session clients for Results. |
| **Per-session user clients** | Live diagnostics **and** K8sGPT Result reads for the selected cluster. Built from Kion/EKS bearer or kubeconfig after cluster select. |

**Session hygiene**

- EKS bearer is refreshed on every `get_k8s_clients_for_session` (tokens expire ~60s; AWS creds TTL remains ~1h).
- Kubeconfig sessions use a dedicated `ApiClient` (no process-global kube config).
- Request paths get a **shallow copy** of the clients map so logout `clear()` does not empty an in-flight agent dict.
- On logout (`DELETE /api/credentials/`), credential expiry (incl. 60s cleanup loop), or store eviction: secrets are scrubbed, clients closed (bearer/CA/temp kubeconfig wiped), cookie cleared.
- Chat export/list/get conversation require an authenticated session (same as query/history).

### Pod security

Chart/templates aim for restricted-style workloads:

- Non-root user  
- Read-only root filesystem where feasible  
- No privilege escalation; drop all capabilities  
- Seccomp RuntimeDefault (and related annotations as configured)

### Secrets management

- **Do not** commit LLM keys, GHCR tokens, or kubeconfigs.  
- Helm `llm.createSecret: false` for GitOps; create `devops-chatbot-secrets` out of band (or ExternalSecrets/Vault).  
- Image pulls via `ghcr-pull-secret`.  
- K8sGPT AI backend secret in the operator namespace.

### kubeApi policy layer

The `backend/kube_policy/` module enforces authorization on every Kubernetes API wrapper call:

| Default | Value |
|---------|-------|
| `allowMutate` | `false` |
| Allowed methods | GET-oriented only |
| Secret data (`data`/`stringData`) | Denied (identify-only: list/metadata/key names) |
| Recommendations | Always allowed (not gated) |

These defaults are set in Helm values (`kubeApi.*`) and can be overridden per environment via GitOps overlays. Production clusters should keep defaults unless an explicit reviewed overlay enables mutate.

### Network

- ClusterIP service; Traefik (or other) ingress for external access.  
- CORS via `app.allowedOrigins` / `ALLOWED_ORIGINS` — keep tight to real UI origins.  
- TLS: enable via ingress + cert-manager when moving beyond lab clusters (`ingress.tls` in chart values).

### Supply chain

- Deploy images by **git SHA** tags from GHCR.  
- Image Updater allow-tags restricted to 40-char hex SHAs on the chatbot Application.  
- Prefer dependency pins in `requirements.txt` / lockfiles; review CI-built images.

### Policy (optional / reference)

`k8s/kyverno-policies.yaml` and related manifests may enforce labels, resources, and hardening — apply only if Kyverno is installed and policies are reviewed for this cluster.

## Pre-deployment checklist

- [ ] Secrets created out of band; not in git  
- [ ] GHCR pull secret present in app namespace  
- [ ] Ingress TLS plan for any non-lab exposure  
- [ ] CORS origins match real UI URLs  
- [ ] Chatbot and K8sGPT RBAC reviewed (least privilege)  
- [ ] kubeApi policy defaults understood (mutate-off, Secret identify-only)  
- [ ] NetworkPolicies / PSS if required by platform standards  
- [ ] Audit logging / monitoring for the namespace  

## Threat notes

| Risk | Mitigation |
|------|------------|
| Stolen browser session cookie | HttpOnly; short TTL; HTTPS in prod; logout clears cookie |
| Over-broad AWS keys | Use short-lived Kion creds; single-cluster pin |
| Prompt-injection → cluster change | kubeApi policy (mutate-off default); RBAC; authorize chokepoint |
| Malicious image tag | SHA allow-list; signed/provenance optional future |
| Secret leak in logs | Avoid logging tokens; redaction in error handlers; Secret identify-only defaults |
| Free recommendations exploited | Recommendations are advice only; execution still requires policy + RBAC |

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Usage](usage.md)
