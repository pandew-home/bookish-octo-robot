# Contract: GitLab deploy cutover (003)

**Synced**: 2026-07-26 — vendor-first; PVC ≥10Gi; image re-pin primary rollback; preserve conversations; local pytest OK.

## Repositories

| Repo | Project path | Role |
|------|--------------|------|
| App | `internal/jup/ept/paas/bookish-octo-robot` | Image + staging deploy |
| Operator | `internal/jup/ept/paas/bookish-octo-robot-operator` | Out of scope (happy path) |

## Cluster naming

| Term | Meaning |
|------|---------|
| `jade-2pst-b` | Overlay path key (`clusters/jade-2pst-b/`) |
| `jade-2pst-b-rgp` | EKS cluster name |
| `bookish-octo-robot` | App namespace |

## Branch contract

| Branch | Pipeline mode | Required content |
|--------|---------------|------------------|
| `main` | build-only | Full app source, Dockerfile with **vendored** Vestige, `helm/devops-chatbot` with memory/kubeApi; **pytest memory+kube_policy green before merge** (local or any runner) |
| `jadeuc-faiss` | deploy | Frozen pre-cutover FAISS chart/overlays/image pin |
| `jadeuc-staging-b` | deploy | Vestige chart/overlays; pin Vestige image SHA; Results-only RBAC **on same push as Vestige pin** |

## Image contract

```
registry.jcce.cloud/internal/jup/ept/paas/bookish-octo-robot/devops-chatbot:<CI_COMMIT_SHORT_SHA>
```

- Built only from successful `main` pipeline (or equivalent package job) **after** automated test gate.
- Staging MUST pin a SHA that includes: `vestige-mcp` binary (vendored at build), `backend/memory`, `backend/kube_policy`, supervisord dual process, health at `/api/health`.
- Staging MUST NOT pin a FAISS-only SHA while chart expects Vestige env.

## Vestige binary strategy (decided)

| Choice | Path |
|--------|------|
| **vendor (chosen)** | COPY from `third_party/vestige/` or internal OCI/blob — Vestige **v2.2.1** linux |
| curl allowlist | **Not** the happy path for this feature |

**Chosen strategy**: **Vendor first** — no public GitHub download in Dockerfile happy path.

T013–T014 MUST use the vendored path from T009.

## Runtime env contract (staging)

| Variable | Value |
|----------|--------|
| MEMORY_BACKEND | `vestige` |
| VESTIGE_HTTP_URL | `http://127.0.0.1:3928` |
| VESTIGE_DATA_DIR | `/data/vestige` |
| FASTEMBED_CACHE_PATH | `/data/vestige/model-cache` |
| KUBE_API_ALLOW_MUTATE | `false` (unless explicit reviewed override) |
| KB_SEEDING_ENABLED | **absent** or not required for chat |

Free-text remediation recommendations MUST remain allowed when mutate is off (application behavior from 002; not disabled by chart).

## Probe contract

| Probe | Path |
|-------|------|
| liveness | `/api/health` |
| readiness | `/api/health/ready` |

## RBAC contract (pod SA)

- `get/list/watch` on `core.k8sgpt.ai` / `results` only for ClusterRole bound to chatbot SA.
- No broad cluster Secret/pod list for the pod SA.
- Applied on first Vestige deploy push (not a later hardening phase).

## PVC contract

| Field | Value |
|-------|--------|
| Minimum size | **≥10Gi** |
| If already ≥10Gi | **Keep existing** (no mandatory growth) |
| 40Gi | **Not required** |
| Conversations | **Preserve** `/data/conversations`; no intentional wipe; no default volume recreate |

## Rollback contract

| Priority | Path |
|----------|------|
| **Primary** | Re-pin FAISS-era `image.tag` on `jadeuc-staging-b` and push |
| **Secondary** | Argo/branch retarget to `jadeuc-faiss` |

## Ingress / secrets (unchanged)

- Host: `k8s-assistant.staging.jadeuc.com`
- LLM secret: Vault-backed `devops-chatbot-secrets` (or VSS equivalent)
- Pull: `registry-pull-creds`

## GitOps mapping (JADE)

- Image SHA tags on `registry.jcce.cloud` (not GHCR).
- Argo desired state via compliance `jade-update-argo` (no committed `argocd/` tree in app repo).
- Satisfies constitution GitOps intent: pull-based reconcile + auditable SHA pins.
