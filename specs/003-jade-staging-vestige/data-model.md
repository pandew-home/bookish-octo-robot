# Data Model: Deploy entities (003)

This feature does not introduce application domain entities beyond 002 memory. It introduces **delivery state** entities.

## Entities

### DeployBranchSnapshot

| Field | Description |
|-------|-------------|
| name | `jadeuc-faiss` |
| source | pre-cutover `jadeuc-staging-b` commit SHA |
| purpose | FAISS-era rollback |
| imagePin | short SHA recorded at snapshot time |

### ImageBuildLine

| Field | Description |
|-------|-------------|
| branch | GitLab `main` |
| artifact | `registry.jcce.cloud/internal/jup/ept/paas/bookish-octo-robot/devops-chatbot:<shortsha>` |
| contents | 002 app + vestige-mcp + no FAISS chat path |

### StagingDeployLine

| Field | Description |
|-------|-------------|
| branch | `jadeuc-staging-b` |
| cluster | jade-2pst-b / jade-2pst-b-rgp |
| chart | `chart/` (synced from main helm + JADE overlays) |
| overlay | `clusters/jade-2pst-b/devops-chatbot.values.yaml` |
| memoryBackend | `vestige` |
| pvcSize | grown (target 40Gi) |
| saScope | K8sGPT Results read-only |

### PersistentVolumeClaimState

| Path | Purpose |
|------|---------|
| `/data/conversations` | chat history |
| `/data/vestige` | Vestige SQLite / store |
| `/data/vestige/model-cache` | FastEmbed / model cache |

### RollbackBinding

| From | To |
|------|-----|
| failed Vestige staging | `jadeuc-faiss` tip and/or prior image pin |
| note | PVC may retain vestige dirs after rollback; harmless |

## State transitions

```text
[FAISS staging] --snapshot--> [jadeuc-faiss frozen]
       |
       +-- main port 002 --> [Vestige image in registry]
       |
       +-- replace jadeuc-staging-b --> [Argo sync] --> [Vestige staging live]
       |
       X-- failure --> rollback to jadeuc-faiss
```
