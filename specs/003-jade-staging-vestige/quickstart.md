# Quickstart: JADE staging Vestige cutover

**Synced**: 2026-07-26 — vendor-first; PVC ≥10Gi; image re-pin rollback primary; preserve conversations; local pytest OK.

## Prerequisites

- `glab` authenticated to `gitlab.jadeuc.com` as a project Maintainer/Developer
- Access to GitHub `002-vestige-memory-mcp` tree (or exported patch)
- Ability to watch GitLab pipelines and Argo apps for staging
- Overlay key: **jade-2pst-b** · EKS name: **jade-2pst-b-rgp** · namespace: `bookish-octo-robot`

## 0) Record pre-cutover state

```bash
glab api "projects/5003/repository/branches/jadeuc-staging-b" --hostname gitlab.jadeuc.com
# Note commit SHA
# Note image.tag from chart/values-override.yaml and clusters/jade-2pst-b/devops-chatbot.values.yaml
# Note current PVC size (floor required: ≥10Gi; keep if already large enough)
```

Store values here for rollback:

| Field | Value |
|-------|--------|
| Pre-cutover staging commit | _(fill)_ |
| Pre-cutover image.tag | _(fill)_ |
| Pre-cutover PVC size | _(fill)_ |

## 1) Snapshot FAISS staging

```bash
# Create jadeuc-faiss from current jadeuc-staging-b tip and push
glab api --method POST "projects/5003/repository/branches" \
  --hostname gitlab.jadeuc.com \
  -f branch=jadeuc-faiss \
  -f ref=jadeuc-staging-b
```

Confirm branch exists; tip SHA matches pre-cutover; image pin documented on that branch (values files frozen at snapshot).

## 2) Port 002 → GitLab main

1. Clone GitLab app repo; checkout `main`.
2. **Vendor Vestige first**: place **v2.2.1** linux binaries under `third_party/vestige/` (or internal mirror COPY path); record in MR. **Do not** use public GitHub curl in Dockerfile happy path.
3. Port from GitHub 002: backend memory/kube_policy, Dockerfile (COPY vendored vestige), docker scripts, helm/devops-chatbot, frontend KB removal, tests, drop devops-kb.
4. Align UID **1000**.
5. **Test gate (required)**: from the ported tree run pytest for memory + kube_policy (**locally or any runner**). Attach green log to MR. GitLab CI pytest job optional.
6. Open MR → merge only after tests green → wait for **main** docker push success; record `CI_COMMIT_SHORT_SHA`.

## 3) Replace jadeuc-staging-b (single push includes security)

1. Checkout `jadeuc-staging-b`.
2. Sync `chart/` templates/values from updated `helm/devops-chatbot` while **keeping** JADE cluster/ingress/TLS/Vault/pull-secret/ResourceQuota-off/PDB-off/Recreate blocks.
3. Update overlays:
   - `image.tag: <new shortsha>`
   - `memory.backend: vestige` (+ URL/dirs)
   - PVC size **≥10Gi** — **keep existing** if already ≥10Gi; grow only if below 10Gi; **not 40Gi**
   - resources memory 1Gi/2Gi (starting point)
   - probes `/api/health` and `/api/health/ready`
   - remove KB seeding env
   - `kubeApi.allowMutate: false` (and related observe-default defaults)
4. Replace `k8s/rbac.yaml` with Results-only ClusterRole/Binding for chatbot SA (**before** push).
5. `helm template` (or equivalent) to confirm mutate-off + Results-only SA wiring.
6. Push `jadeuc-staging-b`; wait for deploy pipeline / Argo sync.

Do **not** push a Vestige image pin with the old broad ClusterRole still applied.  
Do **not** wipe `/data/conversations` or recreate the PVC by default.

## 4) Smoke

- `https://k8s-assistant.staging.jadeuc.com` loads
- `/api/health` and `/api/health/ready` OK
- Login + cluster select + one chat turn (Vault LLM path still works)
- No Save-to-KB UI
- Free-text recommendation still returned when mutate is off
- Session can list/diagnose live pods; pod SA cannot list Secrets cluster-wide
- `kubectl exec` (or logs): `/data/vestige` exists; note model-cache if created
- Spot-check: pre-cutover `/data/conversations` still present (SC-010)
- Record: degraded-memory unit test names from T016b **or** optional degraded smoke
- Record: memory cluster-scoped per 002 (FR-012)

## 5) Rollback

### Primary — Image re-pin on `jadeuc-staging-b`

1. Checkout `jadeuc-staging-b`.
2. Set `image.tag` in `chart/values-override.yaml` **and** `clusters/jade-2pst-b/devops-chatbot.values.yaml` to the **pre-cutover FAISS pin** recorded in §0 / frozen on `jadeuc-faiss`.
3. Optionally restore FAISS-era probe/KB env from `jadeuc-faiss` if the FAISS image requires them.
4. Push `jadeuc-staging-b`; wait for deploy pipeline / Argo sync.
5. Confirm pod runs pre-cutover image and chat works.

### Secondary — Branch / Argo retarget to `jadeuc-faiss`

1. Ensure `jadeuc-faiss` still points at pre-cutover SHA (do not delete).
2. Retarget the Argo CD Application for `bookish-octo-robot` on jade-2pst-b to branch **`jadeuc-faiss`** (or re-run platform compliance job that sets source branch to `jadeuc-faiss` / equivalent).
3. Sync Application; wait for Healthy.
4. Confirm image tag matches pre-cutover pin from §0.

```bash
# Example only — adjust app name/namespace to platform reality
# argocd app set <app-name> --revision jadeuc-faiss
# argocd app sync <app-name>
#
# Or: platform jade-update-argo / glab pipeline against jadeuc-faiss per JADE runbook
```

**PVC note**: After Vestige cutover, `/data/vestige` may remain on the volume after rollback to FAISS image; harmless leftover dirs. Conversations under `/data/conversations` are preserved by design.
