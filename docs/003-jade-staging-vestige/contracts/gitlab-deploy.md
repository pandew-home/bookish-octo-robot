# Contract: GitLab deploy cutover (003)

## Repositories

| Repo | Project path | Role |
|------|--------------|------|
| App | `internal/jup/ept/paas/bookish-octo-robot` | Image + staging deploy |
| Operator | `internal/jup/ept/paas/bookish-octo-robot-operator` | Out of scope (MVP) |

## Branch contract

| Branch | Pipeline mode | Required content |
|--------|---------------|------------------|
| `main` | build-only | Full app source, Dockerfile with Vestige, `helm/devops-chatbot` with memory/kubeApi |
| `jadeuc-faiss` | deploy | Frozen pre-cutover FAISS chart/overlays/image pin |
| `jadeuc-staging-b` | deploy | Vestige chart/overlays; pin Vestige image SHA; Results-only RBAC |

## Image contract

```
registry.jcce.cloud/internal/jup/ept/paas/bookish-octo-robot/devops-chatbot:<CI_COMMIT_SHORT_SHA>
```

- Built only from successful `main` pipeline (or equivalent package job).
- Staging MUST pin a SHA that includes: `vestige-mcp` binary, `backend/memory`, `backend/kube_policy`, supervisord dual process, health at `/api/health`.
- Staging MUST NOT pin a FAISS-only SHA while chart expects Vestige env.

## Runtime env contract (staging)

| Variable | Value |
|----------|--------|
| MEMORY_BACKEND | `vestige` |
| VESTIGE_HTTP_URL | `http://127.0.0.1:3928` |
| VESTIGE_DATA_DIR | `/data/vestige` |
| FASTEMBED_CACHE_PATH | `/data/vestige/model-cache` |
| KUBE_API_ALLOW_MUTATE | `false` (unless explicit reviewed override) |
| KB_SEEDING_ENABLED | **absent** or not required for chat |

## Probe contract

| Probe | Path |
|-------|------|
| liveness | `/api/health` |
| readiness | `/api/health/ready` |

## RBAC contract (pod SA)

- `get/list/watch` on `core.k8sgpt.ai` / `results` only for ClusterRole bound to chatbot SA.
- No broad cluster Secret/pod list for the pod SA.

## Ingress / secrets (unchanged)

- Host: `k8s-assistant.staging.jadeuc.com`
- LLM secret: Vault-backed `devops-chatbot-secrets` (or VSS equivalent)
- Pull: `registry-pull-creds`
