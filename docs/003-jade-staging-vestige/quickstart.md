# Quickstart: JADE staging Vestige cutover

## Prerequisites

- `glab` authenticated to `gitlab.jadeuc.com` as a project Maintainer/Developer
- Access to GitHub `002-vestige-memory-mcp` tree (or exported patch)
- Ability to watch GitLab pipelines and Argo apps for jade-2pst-b

## 0) Record pre-cutover state

```bash
glab api "projects/5003/repository/branches/jadeuc-staging-b" --hostname gitlab.jadeuc.com
# Note: commit SHA, image tag in chart/values-override.yaml and clusters/.../values.yaml
```

## 1) Snapshot FAISS staging

```bash
# Create jadeuc-faiss from current jadeuc-staging-b tip and push
glab api --method POST "projects/5003/repository/branches" \
  --hostname gitlab.jadeuc.com \
  -f branch=jadeuc-faiss \
  -f ref=jadeuc-staging-b
```

Confirm branch exists and document SHA + image tag in a short commit message on a docs-only note if desired.

## 2) Port 002 → GitLab main

1. Clone GitLab app repo; checkout `main`.
2. Port from GitHub 002: backend memory/kube_policy, Dockerfile, docker scripts, helm/devops-chatbot, frontend KB removal, tests, drop devops-kb.
3. Align UID 1000; resolve Vestige binary download vs vendor.
4. Open MR → merge → wait for **main** docker push success; record `CI_COMMIT_SHORT_SHA`.

## 3) Replace jadeuc-staging-b

1. Checkout `jadeuc-staging-b`.
2. Sync `chart/` templates/values from updated `helm/devops-chatbot` while **keeping** JADE cluster/ingress/Vault blocks.
3. Update overlays:
   - `image.tag: <new shortsha>`
   - `memory.backend: vestige` (+ URL/dirs)
   - PVC size → 40Gi
   - resources memory 1Gi/2Gi
   - probes `/api/health` and `/api/health/ready`
   - remove KB seeding env
4. Replace `k8s/rbac.yaml` with Results-only.
5. Push `jadeuc-staging-b`; wait for deploy pipeline / Argo sync.

## 4) Smoke

- `https://k8s-assistant.staging.jadeuc.com` loads
- `/api/health` and `/api/health/ready` OK
- Login + cluster select + one chat turn
- No Save-to-KB UI
- Optional: `kubectl exec` check `/data/vestige` exists

## 5) Rollback

```bash
# Option A: retarget Argo / redeploy jadeuc-faiss branch (platform process)
# Option B: on jadeuc-staging-b, re-pin FAISS image tag from jadeuc-faiss values and push
```

Prefer documented platform process for branch-based Argo source; image re-pin is the fastest app-only rollback.
