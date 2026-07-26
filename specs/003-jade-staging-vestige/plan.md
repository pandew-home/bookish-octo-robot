# Implementation Plan: JADE Staging Vestige Deploy (002 Integration)

**Branch**: `003-jade-staging-vestige` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-jade-staging-vestige/spec.md`  
**Product reference**: GitHub `002-vestige-memory-mcp` @ `21bb2a53` (and later)

## Summary

Cut over JADE staging (jade-2pst-b) from FAISS-era chatbot to the Vestige MemoryPort product line implemented on GitHub 002. Snapshot `jadeuc-staging-b` → `jadeuc-faiss` for rollback; port 002 into GitLab **`main`** (image build); replace **`jadeuc-staging-b`** chart/overlays for vestige memory, grown PVC, Results-only SA, and observe-default kubeApi. Operator repo untouched unless smoke fails.

## Technical Context

**Language/Version**: Python 3.11 backend, React/TypeScript frontend, Helm 3, GitLab CI (JADE compliance + docker component)

**Primary Dependencies**: Vestige MCP binary (linux/x64), supervisord, FastAPI, existing Kion/EKS session clients, Vault Static Secrets (LLM), Argo CD (platform-managed)

**Storage**: Chatbot PVC (aws-ebs-sc RWO) for `/data/conversations` + `/data/vestige` + model-cache; grow size vs FAISS-era ~20Gi

**Testing**: GitLab pipeline scan/package; manual staging smoke; GitHub pytest suite as port verification

**Target Platform**: EKS jade-2pst-b-rgp (JADE staging), namespace `bookish-octo-robot`, ingress `k8s-assistant.staging.jadeuc.com`

**Project Type**: Multi-repo delivery (GitHub reference + GitLab app deploy; operator optional)

**Performance Goals**: Pod Ready after first vestige model warm-up within elevated start-period; chat p95 not a hard SLO for this cutover

**Constraints**:
- `main` = build-only; `jadeuc-*` = deploy
- No secrets in git; LLM via Vault path `jup/ept/paas/bookish-octo-robot`
- ResourceQuota/PDB disabled on staging by platform policy
- Possible airgap for public GitHub release downloads during docker build
- Single replica + Recreate for RWO PVC

**Scale/Scope**: One staging cluster; one app repo primary; operator only on failure

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate (constitution v3.0.0) | Plan compliance |
|----------------------------|-----------------|
| Observe-default, policy-gated mutation | Staging chart ships `kubeApi.allowMutate: false`, GET-oriented methods |
| Free recommendations always allowed | No change to ban recommendations |
| Secrets identify-only default | Wrapper policy defaults; SA not granted Secret data read |
| Live API first; memory secondary | Session clients for live tools; Vestige institutional memory only |
| Vestige-class memory (not FAISS chat path) | Image + env remove KB seeder; MEMORY_BACKEND=vestige |
| GitOps / SHA images | Image tag = GitLab main short SHA; Argo via compliance |
| runAsNonRoot + explicit UID | Align Dockerfile user with chart (prefer **1000** to match current staging chart) |
| No secrets in git | Keep VSS / existingSecret pattern |

**Gate result**: PASS (no unjustified violations). Residual risk: public curl for Vestige binary — mitigated in research (vendor/mirror).

## Project Structure

### Documentation (this feature)

```text
specs/003-jade-staging-vestige/
├── plan.md                 # This file
├── research.md             # Phase 0
├── data-model.md           # Phase 1 (deploy entities)
├── quickstart.md           # Phase 1 cutover runbook
├── contracts/
│   └── gitlab-deploy.md    # Branch/image/chart contract
├── checklists/
│   └── requirements.md
├── spec.md
└── tasks.md                # /speckit.tasks
```

### Source / deploy surfaces (cross-repo)

```text
# GitHub (reference only for this feature)
bookish-octo-robot @ 002-vestige-memory-mcp
  backend/memory/, backend/kube_policy/, Dockerfile, helm/devops-chatbot/, docker/

# GitLab bookish-octo-robot (project 5003)
main/
  Dockerfile, backend/, frontend/, libs/, helm/devops-chatbot/, docker/, .gitlab-ci.yml
jadeuc-faiss/                    # NEW snapshot of pre-cutover staging
  chart/, clusters/, k8s/, .gitlab-ci.yml
jadeuc-staging-b/                # REPLACED Vestige deploy surface
  chart/, clusters/jade-2pst-b/, k8s/rbac.yaml, .gitlab-ci.yml

# GitLab bookish-octo-robot-operator (5289) — out of scope unless smoke fails
jadeuc-staging-b/
  helm/, clusters/jade-2pst-b/
```

## Phase 0: Research

See [research.md](./research.md). Decisions:
1. Dual-line cutover: main for image, staging for deploy.
2. Snapshot branch name `jadeuc-faiss`.
3. Vestige binary supply chain: prefer vendor/copy into build context if JADE builders block GitHub; else keep curl with documented allowlist.
4. PVC: increase size in overlay (target **40Gi** unless cluster storage policy forbids; then document expand).
5. Resources: request **1Gi** memory / limit **2Gi** minimum starting point for dual process + embeddings (tune after first deploy).
6. UID: standardize on **1000** for image + chart on staging path.
7. Operator: no change in MVP.

## Phase 1: Design

- [data-model.md](./data-model.md) — deploy entities and state transitions
- [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md) — branch/image/env contract
- [quickstart.md](./quickstart.md) — ordered cutover commands

### Chart delta (GitLab `helm/devops-chatbot` + staging `chart/`)

Port from GitHub 002 `helm/devops-chatbot`:

| Area | Change |
|------|--------|
| `values.memory` | backend, vestigeHttpUrl, dataDir, modelCacheDir |
| `values.kubeApi` | allowMutate false, secrets identify-only, denylists |
| `templates/deployment.yaml` | env MEMORY_*/VESTIGE_*/KUBE_API_*; drop KB_SEEDING_*; init mkdir vestige paths; probes /api/health* |
| `templates/rbac.yaml` | Results-only ClusterRole/Binding |
| staging `k8s/rbac.yaml` | Match Results-only (replace broad ClusterRole) |
| `values-override` / cluster overlay | image tag, PVC size, resources, CORS origin, probes reset |

Preserve JADE-only: cluster metadata, Vault VSS for LLM, ingress host, registry-pull-creds, resourceQuota/pdb off, Recreate.

### Dockerfile delta (GitLab main)

- Drop `devops-kb` editable install
- Add vestige-bin stage (or COPY vendored binaries)
- supervisord + start-backend/start-vestige
- Copy `backend/memory`, `backend/kube_policy`
- HEALTHCHECK `/api/health`
- USER 1000 aligned with chart

## Phase 2: Implementation order

See [tasks.md](./tasks.md).

1. Spec-kit docs complete (this feature dir)  
2. GitLab `jadeuc-faiss` snapshot  
3. Port 002 → GitLab main MR + pipeline  
4. Replace jadeuc-staging-b  
5. Smoke + rollback doc  

## Constitution Check (post-design)

Re-validated: policy defaults, Results-only SA, Vestige memory, no secrets in git, GitOps image tags — **PASS**.

## Risks

| Risk | Mitigation |
|------|------------|
| Build cannot curl GitHub | Vendor binaries under `third_party/vestige/` or internal OCI/blob |
| Model download egress | Pre-seed PVC or allowlist; first-start longer probes |
| Image/tag skew | Pin staging tag only after main pipeline success SHA |
| SA tighten breaks Results | Smoke; operator follow-up if needed |
| PVC expand blocked | Document recreate path; keep jadeuc-faiss for app rollback |

## Complexity Tracking

No constitution violations requiring justified exceptions.
