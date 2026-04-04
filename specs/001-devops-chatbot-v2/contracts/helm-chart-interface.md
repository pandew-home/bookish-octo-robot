# Contract: Helm Chart Values Interface

**Feature**: `001-devops-chatbot-v2` — Helm-Based CI/CD Migration  
**Produced by**: `/speckit.plan` Phase 1  
**Date**: 2026-04-03

This document defines the public interface of the `helm/devops-chatbot/` chart — the values callers must provide and the resources it produces. It serves as the contract between the CI pipeline and the chart.

---

## Inputs (values.yaml + --set overrides)

### Required at Deploy Time (never committed)

| `--set` Key | Type | Source | Notes |
|---|---|---|---|
| `image.tag` | string | `${{ github.sha }}` | Full SHA of the image to deploy |
| `podLabels.gitSha` | string | `${{ github.sha }}` | Traceability label on pod spec |
| `llm.apiKey` | string | `${{ secrets.LLM_API_KEY }}` | LLM provider API key |
| `llm.provider` | string | `${{ secrets.LLM_PROVIDER }}` | e.g. `openrouter` |
| `llm.model` | string | `${{ secrets.LLM_MODEL }}` | e.g. `qwen/qwen3-coder` |
| `llm.defaultRegion` | string | `${{ secrets.DEFAULT_REGION }}` | AWS region (for credential flows) |

### Optional Overrides (have committed defaults in values.yaml)

| Key | Default | Overridable? | Notes |
|---|---|---|---|
| `image.repository` | `ghcr.io/<owner>/<repo>` | Yes | Change for fork/mirror scenarios |
| `image.pullPolicy` | `IfNotPresent` | Yes | |
| `replicaCount` | `1` | Yes | Keep at 1; CredentialStore is in-memory |
| `resources.requests.cpu` | `100m` | Yes | |
| `resources.requests.memory` | `256Mi` | Yes | |
| `resources.limits.cpu` | `500m` | Yes | |
| `resources.limits.memory` | `512Mi` | Yes | |
| `ingress.host` | `<hostname>` | Yes | Cluster hostname |
| `pvc.storageSize` | `5Gi` | Yes | |
| `pvc.storageClass` | `""` (cluster default) | Yes | |
| `pdb.minAvailable` | `1` | Yes | |

### Non-Overridable (fixed in templates)

| Field | Fixed Value | Why |
|---|---|---|
| `securityContext.runAsNonRoot` | `true` | Compliance; weakening disallowed |
| `securityContext.readOnlyRootFilesystem` | `true` | Compliance |
| `securityContext.seccompProfile.type` | `RuntimeDefault` | Compliance |
| cert-manager annotation on Ingress | `cert-manager.io/cluster-issuer: letsencrypt-prod` | Single issuer environment |

---

## Outputs (resources created by chart)

`helm template helm/devops-chatbot/ --set image.tag=test` MUST render exactly these resource kinds (SC-H-007):

| Kind | Name | Namespace |
|---|---|---|
| `Deployment` | `devops-chatbot` | `devops-chatbot` |
| `Service` | `devops-chatbot` | `devops-chatbot` |
| `Ingress` | `devops-chatbot` | `devops-chatbot` |
| `PersistentVolumeClaim` | `devops-chatbot-data` | `devops-chatbot` |
| `ServiceAccount` | `devops-chatbot` | `devops-chatbot` |
| `PodDisruptionBudget` | `devops-chatbot` | `devops-chatbot` |
| `ResourceQuota` | `devops-chatbot` | `devops-chatbot` |
| `Secret` | `devops-chatbot-secrets` | `devops-chatbot` |

**Not rendered by chart** (applied by CI separately):
- `ClusterIssuer` (cert-issuer.yaml — cluster-scoped)
- `ClusterPolicy` (kyverno-policies.yaml — cluster-scoped)
- `Secret` `ghcr-pull-secret` (created by CI pre-step)

---

## Helm Release Contract

| Attribute | Value |
|---|---|
| Release name | `devops-chatbot` |
| Target namespace | `devops-chatbot` |
| `--create-namespace` | Required (namespace may not pre-exist) |
| `--wait` | Required |
| `--timeout` | `300s` |
| `--atomic` | Required (auto-rollback on failure) |
| Idempotent | Yes — second run with same values produces no changes |

---

## PVC Lifecycle Contract

The `PersistentVolumeClaim` template MUST carry the annotation:

```yaml
annotations:
  helm.sh/resource-policy: keep
```

This ensures `helm uninstall devops-chatbot` does NOT delete the PVC, preserving the knowledge base data.

---

## Secret Security Contract

- `helm get values devops-chatbot --all` MUST NOT expose any secret value
- `helm template helm/devops-chatbot/ ...` output captured to CI logs MUST NOT contain API keys
- A CI step MUST run `grep -r "sk-\|ASIA\|AKIA" helm/devops-chatbot/` and exit non-zero if any match is found
- The chart MUST NOT reference any external secret management system (Vault, SSM) — secrets come exclusively from `--set` at deploy time

---

## Downstream Consumers

| Consumer | How it uses the chart |
|---|---|
| `deploy.yml` GitHub Actions | Calls `helm upgrade --install` with required `--set` flags |
| Developer workstation | Calls `helm lint` + `helm template` for local validation |
| CI smoke test | Reads `helm status devops-chatbot` and calls `GET /api/health` |
