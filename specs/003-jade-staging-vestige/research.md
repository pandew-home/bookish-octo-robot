# Research: 003-jade-staging-vestige

**Synced**: 2026-07-26 with spec clarifications session.

## R1 — JADE branch roles

**Decision**: Port product code to GitLab **`main`** (docker build); put deploy-only Vestige overlays on **`jadeuc-staging-b`**; freeze FAISS deploy as **`jadeuc-faiss`**.

**Rationale**: Observed CI on project 5003: `main` → `PIPELINE_MODE=build-only` + docker component; `jadeuc-*` → deploy + `jade-update-argo`. Staging branch currently has **no** `backend/`/`frontend/` tree.

**Alternatives**: Put full source only on staging-b (breaks JADE main image line); deploy without updating main (image/config skew).

## R2 — Snapshot naming

**Decision**: Branch name **`jadeuc-faiss`** from tip of pre-cutover `jadeuc-staging-b`.

**Rationale**: User-requested; matches `jadeuc-*` deploy branch regex in CI; clearly signals FAISS-era rollback / value recovery.

## R3 — Vestige binary supply chain

**Decision**: **Vendor-first**. Place Vestige **v2.2.1** linux binaries under `third_party/vestige/` or COPY from an internal mirror. **No public GitHub curl in Dockerfile happy path.**

**Ordering**: Vendoring (T009) **before** Dockerfile/script port tasks (T013–T014). Record path in `contracts/gitlab-deploy.md`.

**Rationale**: Clarification session 2026-07-26; JADE networks often restrict github.com; avoids dual-path ambiguity at implement time.

**Alternatives rejected for happy path**: curl-first with vendor fallback; curl-only.

## R4 — PVC and resources

**Decision**: PVC floor **≥10Gi**. If pre-cutover size is already ≥10Gi, **keep existing**. **Do not require 40Gi.** Memory request **1Gi** / limit **2Gi** as starting pod resources. Recreate strategy retained on the **same** volume. **Preserve** `/data/conversations`; no default wipe/recreate.

**Rationale**: Clarification: small Vestige DB; 10Gi sufficient. Conversation continuity is required (FR-013).

**Alternatives rejected**: mandatory 40Gi growth; default PVC recreate with data-loss ack.

## R5 — UID alignment

**Decision**: Use **UID/GID 1000** in Dockerfile and chart for this cutover (matches current staging chart securityContext).

**Rationale**: Staging chart already `runAsUser: 1000`; GitLab main Dockerfile used 10001 historically — pick one to avoid PVC permission breaks.

## R6 — Operator scope

**Decision**: No operator changes in happy path / MVP.

**Rationale**: User locked; K8sGPT stack already on staging. Revisit only if Results list fails after SA tighten (T031).

## R7 — Probe paths

**Decision**: Remove staging override of probes to `/`; use `/api/health` and `/api/health/ready`.

**Rationale**: FAISS-era workaround for images without health routes; 002 image exposes proper health endpoints.

## R8 — Source of truth for behavior

**Decision**: GitHub `002-vestige-memory-mcp` @ `21bb2a53+` is the port reference; GitLab main becomes the JADE image source of truth after merge.

**Rationale**: Product already implemented and reviewed on GitHub; this feature is delivery, not rewrite.

## R9 — MVP includes security on first Vestige sync

**Decision**: Results-only SA + `kubeApi.allowMutate=false` ship on the **same** `jadeuc-staging-b` push as the Vestige image pin (not a deferred hardening phase).

**Rationale**: Spec FR-008/SC-007 are MUST/success criteria; intermediate broad-SA Vestige deploy is an avoidable regression window.

## R10 — Pytest gate before GitLab main merge

**Decision**: Ported `backend/memory` + `backend/kube_policy` tests must be green **before** merge. May run **locally or on any runner**; green log attached to MR/task log. GitLab CI pytest job is **optional**. Package-only scan is not sufficient.

**Rationale**: Constitution §8 / non-negotiable #10; clarification session chose local-or-any-runner flexibility.

## R11 — Cluster naming

**Decision**: Use **jade-2pst-b** for overlay paths; **jade-2pst-b-rgp** only for EKS cluster name.

**Rationale**: Removes jade-2pst-b vs jade-2pst-b-rgp terminology drift across docs.

## R12 — Rollback priority

**Decision**: **Primary** = re-pin pre-cutover FAISS `image.tag` on `jadeuc-staging-b` and push. **Secondary** = Argo/branch retarget to `jadeuc-faiss`.

**Rationale**: Clarification session; image re-pin is fastest app-only path with Maintainer git access.

## R13 — Conversation preservation

**Decision**: Preserve `/data/conversations` across cutover; no intentional wipe; avoid PVC recreate that destroys history.

**Rationale**: Clarification session FR-013 / SC-010.
