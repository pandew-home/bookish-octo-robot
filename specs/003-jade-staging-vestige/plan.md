# Implementation Plan: JADE Staging Vestige Deploy (002 Integration)

**Branch**: `003-jade-staging-vestige` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)  
**Synced**: 2026-07-26 (spec clarifications: vendor-first, PVC ≥10Gi, image re-pin rollback primary, preserve conversations)

**Input**: Feature specification from `specs/003-jade-staging-vestige/spec.md`  
**Product reference**: GitHub `002-vestige-memory-mcp` @ `21bb2a53` (and later)

## Summary

Cut over JADE staging (**overlay** jade-2pst-b / **EKS** jade-2pst-b-rgp) from FAISS-era chatbot to the Vestige MemoryPort product line implemented on GitHub 002. Snapshot `jadeuc-staging-b` → `jadeuc-faiss` for value recovery / secondary rollback; port 002 into GitLab **`main`** with **vendored Vestige binaries** and **pytest green (local or any runner) before merge**; replace **`jadeuc-staging-b`** chart/overlays for vestige memory, PVC **≥10Gi** (keep existing if already large enough), preserve `/data/conversations`, Results-only SA, and observe-default kubeApi **in the same deploy push**. Primary rollback = image re-pin on `jadeuc-staging-b`. Operator repo untouched unless smoke fails.

## Technical Context

**Language/Version**: Python 3.11 backend, React/TypeScript frontend, Helm 3, GitLab CI (JADE compliance + docker component)

**Primary Dependencies**: Vestige MCP binary (linux/x64, **vendored**), supervisord, FastAPI, existing Kion/EKS session clients, Vault Static Secrets (LLM), Argo CD (platform-managed)

**Storage**: Chatbot PVC (aws-ebs-sc RWO) for `/data/conversations` + `/data/vestige` + optional model-cache; floor **≥10Gi**; keep current size if already ≥10Gi; **no mandatory 40Gi**; do not wipe conversations

**Testing**:
- **Required gate**: pytest for `backend/memory` + `backend/kube_policy` green **before** merge to GitLab `main` — local or any runner OK; attach green log to MR/task log (GitLab CI pytest job optional).
- GitLab pipeline scan/package for image publish.
- Manual staging smoke (chat, health, security, vestige paths, conversation preserve).

**Target Platform**:

| Role | Value |
|------|--------|
| Overlay / short id | `jade-2pst-b` (`clusters/jade-2pst-b/`) |
| EKS cluster name | `jade-2pst-b-rgp` |
| Namespace | `bookish-octo-robot` |
| Ingress | `k8s-assistant.staging.jadeuc.com` |

**Project Type**: Multi-repo delivery (GitHub reference + GitLab app deploy; operator optional)

**Performance Goals**: Pod Ready after first vestige model warm-up within elevated start-period; chat p95 not a hard SLO for this cutover

**Constraints**:
- `main` = build-only; `jadeuc-*` = deploy
- No secrets in git; LLM via Vault path `jup/ept/paas/bookish-octo-robot`
- ResourceQuota/PDB disabled on staging by platform policy
- **Vestige binaries vendor-first** (`third_party/vestige/` or internal mirror COPY) — no public GitHub curl in Dockerfile happy path
- Single replica + Recreate for RWO PVC (**same volume**; preserve conversations)
- Staging Vestige DB is small; 10Gi floor is enough

**Scale/Scope**: One staging cluster; one app repo primary; operator only on failure

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate (constitution v3.0.0) | Plan compliance |
|----------------------------|-----------------|
| Observe-default, policy-gated mutation | Staging chart ships `kubeApi.allowMutate: false`, GET-oriented methods; applied on first Vestige deploy push |
| Free recommendations always allowed | No change to ban recommendations; staging smoke notes recommendation-style reply still works with mutate off |
| Secrets identify-only default | Wrapper policy defaults; SA not granted Secret data read |
| Live API first; memory secondary | Session clients for live tools; Vestige institutional memory only |
| Vestige-class memory (not FAISS chat path) | Image + env remove KB seeder; MEMORY_BACKEND=vestige |
| GitOps / SHA images | **JADE mapping**: image tag = GitLab `main` short SHA on `registry.jcce.cloud/...`; Argo desired state via compliance `jade-update-argo` (no in-app-repo `argocd/` tree). Constitution GHCR + in-repo `argocd/` is GitHub baseline; JADE fork satisfies GitOps spirit via SHA pins + pull-based Argo. |
| runAsNonRoot + explicit UID | Align Dockerfile user with chart (**1000** to match current staging chart) |
| No secrets in git | Keep VSS / existingSecret pattern |
| Testability / automated tests | pytest memory + kube_policy green before `main` merge (local or any runner); package CI alone is **not** sufficient |

**Gate result**: PASS (no unjustified violations). Public curl risk eliminated by vendor-first decision.

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
  Dockerfile, backend/, frontend/, libs/, helm/devops-chatbot/, docker/, third_party/vestige/ (or mirror COPY), .gitlab-ci.yml
jadeuc-faiss/                    # NEW snapshot of pre-cutover staging
  chart/, clusters/, k8s/, .gitlab-ci.yml
jadeuc-staging-b/                # REPLACED Vestige deploy surface
  chart/, clusters/jade-2pst-b/, k8s/rbac.yaml, .gitlab-ci.yml

# GitLab bookish-octo-robot-operator (5289) — out of scope unless smoke fails
jadeuc-staging-b/
  helm/, clusters/jade-2pst-b/
```

## Phase 0: Research

See [research.md](./research.md). Decisions (post-clarify):
1. Dual-line cutover: main for image, staging for deploy.
2. Snapshot branch name `jadeuc-faiss`.
3. Vestige binary: **vendor-first** (v2.2.1 under `third_party/vestige/` or internal mirror). No public curl happy path.
4. PVC: floor **≥10Gi**; keep existing if already ≥10Gi; **no 40Gi mandate**; preserve conversations (no default recreate).
5. Resources: request **1Gi** memory / limit **2Gi** starting point (tune after first deploy if needed).
6. UID: standardize on **1000** for image + chart on staging path.
7. Operator: no change in happy path.
8. Security (Results-only SA + mutate-off) ships with first Vestige staging push (MVP).
9. Rollback **primary**: image re-pin on `jadeuc-staging-b`; **secondary**: Argo/branch retarget to `jadeuc-faiss`.
10. Pytest: local or any runner with green log attached.

## Phase 1: Design

- [data-model.md](./data-model.md) — deploy entities and state transitions
- [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md) — branch/image/env contract
- [quickstart.md](./quickstart.md) — ordered cutover commands (RBAC before push; primary rollback = image re-pin)

### Chart delta (GitLab `helm/devops-chatbot` + staging `chart/`)

Port from GitHub 002 `helm/devops-chatbot`:

| Area | Change |
|------|--------|
| `values.memory` | backend, vestigeHttpUrl, dataDir, modelCacheDir |
| `values.kubeApi` | allowMutate false, secrets identify-only, denylists |
| `templates/deployment.yaml` | env MEMORY_*/VESTIGE_*/KUBE_API_*; drop KB_SEEDING_*; init mkdir vestige paths; probes /api/health* |
| `templates/rbac.yaml` | Results-only ClusterRole/Binding |
| staging `k8s/rbac.yaml` | Match Results-only (replace broad ClusterRole) **before** push |
| `values-override` / cluster overlay | image tag, PVC size (**≥10Gi** / keep-as-is), resources, CORS origin, probes reset |

Preserve JADE-only: cluster metadata, Vault VSS for LLM, ingress host, registry-pull-creds, resourceQuota/pdb off, Recreate.

### Dockerfile delta (GitLab main)

- Drop `devops-kb` editable install
- **COPY vendored** Vestige binaries (no public GitHub download happy path)
- supervisord + start-backend/start-vestige
- Copy `backend/memory`, `backend/kube_policy`
- HEALTHCHECK `/api/health`
- USER 1000 aligned with chart

## Phase 2: Implementation order

See [tasks.md](./tasks.md).

1. Spec-kit docs complete (this feature dir on branch `003-jade-staging-vestige`)  
2. GitLab `jadeuc-faiss` snapshot  
3. Port 002 → GitLab main MR + vendor binaries + **pytest gate** + pipeline  
4. Replace jadeuc-staging-b (**chart + PVC floor + RBAC + probes** then push; preserve conversations)  
5. Smoke (incl. security, recommendations, vestige paths, conversation preserve) + rollback doc (image re-pin first)  

## Constitution Check (post-design)

Re-validated: policy defaults, Results-only SA on first Vestige sync, Vestige memory, vendor-first, no secrets in git, JADE GitOps SHA tags, pytest before merge — **PASS**.

## Risks

| Risk | Mitigation |
|------|------------|
| Public GitHub blocked | **Vendor-first** under `third_party/vestige/` or internal mirror (decided) |
| Model download egress / free space | Longer probes; 10Gi floor; tune memory limits if first start fails |
| Image/tag skew | Pin staging tag only after main pipeline success SHA |
| SA tighten breaks Results | Smoke same window; operator follow-up if needed (T031) |
| PVC below 10Gi | Grow in place if possible without wipe; do not default to recreate (FR-013) |
| Failed cutover | Primary: re-pin FAISS image on `jadeuc-staging-b`; secondary: `jadeuc-faiss` branch |

## Complexity Tracking

No constitution violations requiring justified exceptions. JADE GitOps path differs in letter from GitHub `argocd/`+GHCR; compliance Argo + SHA registry tags satisfy principle intent (documented above).
