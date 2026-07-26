# Research: 003-jade-staging-vestige

## R1 — JADE branch roles

**Decision**: Port product code to GitLab **`main`** (docker build); put deploy-only Vestige overlays on **`jadeuc-staging-b`**; freeze FAISS deploy as **`jadeuc-faiss`**.

**Rationale**: Observed CI on project 5003: `main` → `PIPELINE_MODE=build-only` + docker component; `jadeuc-*` → deploy + `jade-update-argo`. Staging branch currently has **no** `backend/`/`frontend/` tree.

**Alternatives**: Put full source only on staging-b (breaks JADE main image line); deploy without updating main (image/config skew).

## R2 — Snapshot naming

**Decision**: Branch name **`jadeuc-faiss`** from tip of pre-cutover `jadeuc-staging-b`.

**Rationale**: User-requested; matches `jadeuc-*` deploy branch regex in CI; clearly signals FAISS-era rollback.

## R3 — Vestige binary supply chain

**Decision**: Default port keeps Dockerfile download of Vestige **v2.2.1** linux gnu tarball; if JADE package job fails on egress, switch to **vendored binaries** committed or fetched from internal registry in the same MR.

**Rationale**: GitHub 002 already validates 2.2.1; JADE networks often restrict github.com.

**Alternatives**: Multi-stage from internal mirror image; install via company artifactory.

## R4 — PVC and resources

**Decision**: Target PVC **40Gi** (from ~20Gi) and memory request **1Gi** / limit **2Gi** as initial staging overlay; Recreate strategy retained.

**Rationale**: Model cache + SQLite vestige + dual process; single replica RWO already uses Recreate to avoid multi-attach.

**Alternatives**: 30Gi if quota tight; noop-first (rejected by user).

## R5 — UID alignment

**Decision**: Use **UID/GID 1000** in Dockerfile and chart for this cutover (matches current staging chart securityContext).

**Rationale**: Staging chart already `runAsUser: 1000`; GitLab main Dockerfile used 10001 historically — pick one to avoid PVC permission breaks.

## R6 — Operator scope

**Decision**: No operator changes in MVP.

**Rationale**: User locked; K8sGPT stack already on staging. Revisit only if Results list fails after SA tighten.

## R7 — Probe paths

**Decision**: Remove staging override of probes to `/`; use `/api/health` and `/api/health/ready`.

**Rationale**: FAISS-era workaround for images without health routes; 002 image exposes proper health endpoints.

## R8 — Source of truth for behavior

**Decision**: GitHub `002-vestige-memory-mcp` @ `21bb2a53+` is the port reference; GitLab main becomes the JADE image source of truth after merge.

**Rationale**: Product already implemented and reviewed on GitHub; this feature is delivery, not rewrite.
