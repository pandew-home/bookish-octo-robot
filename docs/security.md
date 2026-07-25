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
- Mutating Kubernetes API tool calls require **human approval** in the product path (`agentic_engine` / system prompt).  
- Cluster **RBAC** remains the hard boundary — the chatbot SA and user tokens must not be over-privileged.

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
- [ ] Mutation approval UX understood by operators  
- [ ] NetworkPolicies / PSS if required by platform standards  
- [ ] Audit logging / monitoring for the namespace  

## Threat notes

| Risk | Mitigation |
|------|------------|
| Stolen browser session cookie | HttpOnly; short TTL; HTTPS in prod; logout clears cookie |
| Over-broad AWS keys | Use short-lived Kion creds; single-cluster pin |
| Prompt-injection → cluster change | Approval gates; RBAC; prefer read-only SA in prod |
| Malicious image tag | SHA allow-list; signed/provenance optional future |
| Secret leak in logs | Avoid logging tokens; redaction in error handlers |

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Usage](usage.md)
