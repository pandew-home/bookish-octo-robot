# Data Model: Deploy entities (003)

This feature does not introduce application domain entities beyond 002 memory. It introduces **delivery state** entities.

**Synced**: 2026-07-26 with spec clarifications.

**Cluster naming**: overlay/short id **jade-2pst-b** (`clusters/jade-2pst-b/`); EKS name **jade-2pst-b-rgp** for the same staging environment.

## Entities

### DeployBranchSnapshot

| Field | Description |
|-------|-------------|
| name | `jadeuc-faiss` |
| source | pre-cutover `jadeuc-staging-b` commit SHA |
| purpose | FAISS-era value recovery + secondary rollback |
| imagePin | short SHA recorded at snapshot time |

### ImageBuildLine

| Field | Description |
|-------|-------------|
| branch | GitLab `main` |
| artifact | `registry.jcce.cloud/internal/jup/ept/paas/bookish-octo-robot/devops-chatbot:<shortsha>` |
| contents | 002 app + **vendored** vestige-mcp + no FAISS chat path |
| testGate | pytest memory + kube_policy green before merge (local or any runner) |
| vestigeBinary | vendor-first (`third_party/vestige/` or internal mirror) |

### StagingDeployLine

| Field | Description |
|-------|-------------|
| branch | `jadeuc-staging-b` |
| overlayKey | `jade-2pst-b` |
| eksClusterName | `jade-2pst-b-rgp` |
| chart | `chart/` (synced from main helm + JADE overlays) |
| overlay | `clusters/jade-2pst-b/devops-chatbot.values.yaml` |
| memoryBackend | `vestige` |
| pvcSize | **≥10Gi** (keep existing if already ≥10Gi; not 40Gi) |
| saScope | K8sGPT Results read-only (applied before first Vestige sync) |
| kubeApiAllowMutate | `false` (observe-default) |
| conversations | preserved under `/data/conversations` |

### PersistentVolumeClaimState

| Path | Purpose | Cutover rule |
|------|---------|--------------|
| `/data/conversations` | chat history | **Preserve** (FR-013 / SC-010) |
| `/data/vestige` | Vestige SQLite / store | Created/used by Vestige |
| `/data/vestige/model-cache` | FastEmbed / model cache | Optional; small-DB posture |

### RollbackBinding

| Priority | From | To |
|----------|------|-----|
| **Primary** | failed Vestige staging | Prior FAISS `image.tag` re-pin on `jadeuc-staging-b` |
| **Secondary** | failed Vestige staging | `jadeuc-faiss` tip (Argo/branch retarget) |
| note | | PVC may retain vestige dirs after rollback; conversations preserved |

## State transitions

```text
[FAISS staging] --snapshot--> [jadeuc-faiss frozen]
       |
       +-- main port 002 + vendor vestige + pytest gate --> [Vestige image in registry]
       |
       +-- replace jadeuc-staging-b (chart+PVC≥10Gi+RBAC, preserve convos)
             --> [Argo sync] --> [Vestige staging live]
       |
       X-- failure --> primary: image re-pin on jadeuc-staging-b
                    --> secondary: jadeuc-faiss branch retarget
```
