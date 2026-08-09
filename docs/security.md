# Security

## Authentication

- **Kion temporary AWS credentials** (STS) and/or kubeconfig.  
- Credentials **in memory** with TTL (~3600s), not on disk by default.  
- Session: **HttpOnly `session_id` cookie** and/or **`X-Session-Id`**.  
- Optional target-cluster check on login when `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME` is set.

## Agent / mutation

- Default: **observe and diagnose**.  
- Mutating K8s API **execution** gated by **kubeApi policy** (`backend/kube_policy/`): Helm/env + user creds. Default `allowMutate: false`, GET-oriented methods.  
- Free-text **recommendations** are not policy-gated — only execution is.  
- **Secret identify-only:** list/metadata/key names OK; values (`data`/`stringData`) denied unless policy allows.  
- Cluster **RBAC** is the hard boundary.

### kubeApi defaults

| Setting | Default |
|---------|---------|
| `allowMutate` | `false` |
| Methods | GET-oriented |
| Secret data | Denied (identify-only) |
| Recommendations | Always allowed |

Override only via reviewed GitOps overlays. Production should keep defaults.

## Vestige memory

Shared **team** knowledge for cluster findings (not per-user private history). Scoped by deployment/PVC and optional `cluster` metadata — not by `user_id`. Secrets scrubbed before ingest; conversation history remains separate on disk.

## ServiceAccount vs session clients

| Identity | Scope |
|----------|--------|
| Pod SA (`devops-chatbot`) | get/list/watch on `core.k8sgpt.ai/results` only (Helm RBAC) |
| Per-session user clients | Live diagnostics + Result reads after cluster select |

**Session hygiene:** EKS bearer refreshed on client fetch; dedicated `ApiClient` for kubeconfig; shallow client-map copy for in-flight requests; logout/expiry scrubs secrets, closes clients, clears cookie. Chat history APIs require authenticated session.

## Pod security

Non-root; read-only root FS where feasible; no privilege escalation; drop all caps; seccomp RuntimeDefault.

## Secrets

- Never commit LLM keys, GHCR tokens, or kubeconfigs.  
- Helm `llm.createSecret: false`; create `devops-chatbot-secrets` out of band.  
- Image pulls via `ghcr-pull-secret`; K8sGPT AI secret in operator namespace.

## Network & supply chain

- ClusterIP + ingress (Traefik or other); tight CORS (`allowedOrigins`).  
- TLS via ingress + cert-manager for non-lab (`ingress.tls` in chart).  
- Deploy by **git SHA** from GHCR; Image Updater allow-tags = 40-char hex.  
- Optional: `k8s/kyverno-policies.yaml` only if Kyverno is installed and reviewed.

## Pre-deployment checklist

- [ ] Secrets out of band; not in git  
- [ ] GHCR pull secret in app namespace  
- [ ] TLS plan for non-lab exposure  
- [ ] CORS matches real UI URLs  
- [ ] Chatbot + K8sGPT RBAC least privilege  
- [ ] kubeApi defaults understood (mutate-off, Secret identify-only)  
- [ ] NetworkPolicies / PSS if required  
- [ ] Audit logging / monitoring for the namespace  

## Threat notes

| Risk | Mitigation |
|------|------------|
| Stolen session cookie | HttpOnly; short TTL; HTTPS in prod; logout clears cookie |
| Over-broad AWS keys | Short-lived Kion creds; single-cluster pin |
| Prompt-injection → mutate | kubeApi policy; RBAC; authorize chokepoint |
| Malicious image tag | SHA allow-list |
| Secret leak in logs | No token logging; Secret identify-only |
| Free recommendations | Advice only; execution still needs policy + RBAC |

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Usage](usage.md)
