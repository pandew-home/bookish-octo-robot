# Implementation Plan: Helm-Based CI/CD Migration

**Branch**: `001-devops-chatbot-v2` | **Date**: 2026-04-03 | **Spec**: [helm-spec.md](helm-spec.md)  
**Input**: Feature specification from `specs/001-devops-chatbot-v2/helm-spec.md`  
**Research**: [research.md](research.md) | **Data Model**: [data-model.md](data-model.md) | **Contract**: [contracts/helm-chart-interface.md](contracts/helm-chart-interface.md)

---

## Summary

Migrate the bookish-octo-robot CI/CD pipeline from raw `kubectl apply` to `helm upgrade --install` for three components: the **devops-chatbot** application, the **k8sgpt operator**, and the **Grafana Alloy** observability stack. Simultaneously upgrade the k8sgpt-operator Helm chart from `0.2.26` → `0.2.27`, add `ConfigMap` analyzer and Trivy integration to the K8sGPT CR, and clean up all raw manifests that can be absorbed into Helm templates or replaced by `kubectl create secret --dry-run` patterns.

**Primary driver**: Replace fragile `sed -i` image tag injection and scattered `kubectl apply` calls with a reproducible, atomic, rollback-capable Helm-based pipeline that passes `helm lint --strict` as a hard CI gate.

---

## Technical Context

**Language/Version**: Helm 3.14+, GitHub Actions, bash, YAML  
**Primary Dependencies**: `azure/setup-helm@v4`, `grafana/alloy` chart, `k8sgpt-operator/k8sgpt-operator` chart `0.2.27`, Civo CLI  
**Storage**: PVC (`devops-chatbot-data`, 5Gi, ReadWriteOnce) — preserved across releases via `helm.sh/resource-policy: keep`  
**Testing**: `helm lint --strict`, `helm template --dry-run`, `kubectl diff --dry-run=server`, smoke test `GET /api/health`  
**Target Platform**: Civo k3s cluster (`bookish-octo-robot` cluster, NYC1), Kubernetes v1.34+  
**Project Type**: CI/CD infrastructure migration (no application code changes)  
**Performance Goals**: Deploy job ≤ 8 minutes end-to-end; `helm upgrade --atomic --wait --timeout=300s` exits 0  
**Constraints**: Zero secrets in committed files; `helm lint --strict` must exit 0 on every commit; PVC never deleted by Helm  
**Scale/Scope**: 3 Helm releases (`devops-chatbot`, `k8sgpt-operator`, `alloy`); ~10 templates; 2 CI workflow files touched

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **Read-Only Product** | ✅ PASS | This migration is infrastructure-only. No change to RBAC, no new write verbs. The devops-chatbot application itself remains read-only. |
| **Explainability** | ✅ PASS | Helm `--atomic` rollback and `helm history` provide clear audit trail of every deploy. |
| **Operator as Source of Truth** | ✅ PASS | K8sGPT CR (`k8sgpt-openrouter-cr.yaml`) remains the sole source of truth for operator config. `helm-values.yaml` controls only operator deployment, not CR content. |
| **DevOps-First UX** | ✅ PASS | Helm improves dev UX (local `helm lint` before push; atomic rollback). |
| **Reliability Over Completeness** | ✅ PASS | `--atomic` ensures partial deploys are rolled back automatically. |

**Constitution Check POST-DESIGN**: Re-checked after Phase 1 design.
- Trivy integration (`skipInstall: true`) does not introduce write access to the cluster.  
- `dynamicRBAC: true` in the operator grants the operator pod (not the chatbot) additional RBAC. The chatbot's RBAC is unchanged — still read-only.  
- No violations found.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-devops-chatbot-v2/
├── plan.md                          # This file
├── research.md                      # Phase 0: version/analyzer/tool decisions
├── data-model.md                    # Phase 1: values.yaml schema + entity relationships
├── contracts/
│   └── helm-chart-interface.md      # Phase 1: chart input/output contract
├── helm-spec.md                     # Feature requirements (from /speckit.specify)
├── checklists/
│   └── helm.md                      # 41-item checklist
└── tasks.md                         # Phase 2 output (/speckit.tasks — separate command)
```

### Source Code Changes (repository root)

```text
# NEW: Helm chart for devops-chatbot application
helm/
└── devops-chatbot/
    ├── Chart.yaml
    ├── values.yaml
    ├── .helmignore
    └── templates/
        ├── _helpers.tpl
        ├── deployment.yaml          # from k8s/deployment.yaml
        ├── service.yaml             # from k8s/service.yaml
        ├── ingress.yaml             # from k8s/ingress.yaml
        ├── pvc.yaml                 # from k8s/pvc.yaml (keep annotation)
        ├── serviceaccount.yaml      # from k8s/serviceaccount.yaml
        ├── pdb.yaml                 # from k8s/pdb.yaml
        ├── resourcequota.yaml       # from k8s/resourcequota.yaml
        └── secret.yaml              # new: replaces kubectl create secret --dry-run pattern

# MODIFIED: CI workflows
.github/workflows/
├── deploy.yml                       # Replace sed+kubectl with helm upgrade --install
└── deploy-k8sgpt.yml                # Add azure/setup-helm; replace kubectl apply CR+secret

# MODIFIED: k8sgpt configuration
k8sgpt/
├── helm-values.yaml                 # Add dynamicRBAC: true; bump chart version comment to 0.2.27
└── k8sgpt-openrouter-cr.yaml        # Add ConfigMap filter; add integrations.trivy block

# RETAINED (unchanged): out-of-chart kubectl apply targets
k8s/
├── kyverno-policies.yaml            # ClusterPolicy — stays as kubectl apply (ASM-004)
└── cert-issuer.yaml                 # ClusterIssuer — stays as kubectl apply (ASM-005)

k8sgpt/Alloy/
├── alloy-values.yaml                # Already Helm-compatible; used as --values file
├── alloy-rbac.yaml                  # kubectl apply (cluster-scoped)
├── alloy-cleanup-cronjob.yaml       # kubectl apply (supplementary)
└── k8sgpt-result-scraper.yaml       # kubectl apply (supplementary)

# DEPRECATED: to be removed after Helm migration is validated
k8s/deployment.yaml                  # Absorbed into helm/devops-chatbot/templates/
k8s/service.yaml
k8s/ingress.yaml
k8s/pvc.yaml
k8s/serviceaccount.yaml
k8s/pdb.yaml
k8s/resourcequota.yaml
k8s/secrets.yaml                     # Replaced by helm template + --set pattern
```

**Structure Decision**: New `helm/` directory at repo root for the application chart. k8sgpt uses the upstream chart with values files (no custom chart created). Alloy uses the upstream chart with existing `alloy-values.yaml`. Out-of-chart items documented in `helm/devops-chatbot/README.md`.

---

## Architecture Decisions

### AD-001: Single-Layer Values (No values-override.yaml)
- **Decision**: `values.yaml` committed defaults + `--set` flags at deploy time only. No `-f values-override.yaml`.
- **Rationale**: Single Civo cluster; no multi-environment requirement (ASM-001). Adding a `values-override.yaml` would create ambiguity about which file is authoritative.

### AD-002: secret.yaml as Helm Template (not kubectl pre-step)
- **Decision**: Create `templates/secret.yaml` that renders the K8s `Secret` resource from `llm.*` values.
- **Rationale**: Replaces `kubectl create secret --dry-run | kubectl apply` in deploy.yml for the chatbot. Keeps the Secret lifecycle bound to the Helm release. Secrets are never stored in git.

### AD-003: ghcr-pull-secret as Pre-Step (not Helm hook)
- **Decision**: `ghcr-pull-secret` is created via `kubectl create secret docker-registry --dry-run | kubectl apply` before `helm upgrade --install`, not as a Helm pre-install hook.
- **Rationale**: Pull secrets must exist before the operator tries to pull the chart image. Helm hooks run inside the release and can't reliably create pull secrets before image pull. Simpler and more predictable as an explicit CI step (FR-H-010).

### AD-004: k8sgpt-operator Chart `0.2.27` with dynamicRBAC: true
- **Decision**: Upgrade to `0.2.27`, explicitly set `dynamicRBAC: true`.
- **Rationale**: v0.2.27 fixes CRD placement (crds/ dir for proper Helm lifecycle), makes dynamicRBAC default true, and fixes the `--filter` crashloop. Adding `ConfigMap` to CR filters requires dynamic RBAC to provision read access.

### AD-005: ConfigMap Analyzer Addition
- **Decision**: Add `ConfigMap` to k8sgpt CR `spec.filters`.
- **Rationale**: Core analyzer; detects missing/invalid ConfigMap keys. The cluster has application ConfigMaps that benefit from analysis. Not an OLM analyzer (k3s compatible).

### AD-006: Trivy Integration with skipInstall: true
- **Decision**: Enable `spec.integrations.trivy.enabled: true` with `skipInstall: true`.
- **Rationale**: Adds vulnerability context to k8sgpt's analysis of pods with CVEs. `skipInstall: true` avoids installing Trivy Operator (which is a separate Helm chart); standalone Trivy scan or pre-existing Trivy is assumed if available.

### AD-007: OLM Analyzers Excluded
- **Decision**: Do not add OLM analyzers (ClusterCatalog, ClusterExtension, ClusterServiceVersion, Subscription, InstallPlan, OperatorGroup, CatalogSource) to CR filters.
- **Rationale**: k3s does not run the Operator Lifecycle Manager. Including these would trigger API calls that will always 404, polluting logs with errors. If OLM is ever added to the cluster, the CR `spec.filters` list is the right place to add them at that point.

---

## Implementation Phases

### Phase 1: Helm Chart Creation (chatbot)

**Goal**: Create `helm/devops-chatbot/` chart that passes `helm lint --strict` and renders all required resources.

Milestones:
1. Create `helm/devops-chatbot/Chart.yaml` (name, version 0.1.0, appVersion latest)
2. Create `helm/devops-chatbot/values.yaml` with all schema fields from data-model.md
3. Create `templates/_helpers.tpl` with standard name/labels helpers
4. Convert each of 8 manifest files into parameterised templates
5. Add `helm.sh/resource-policy: keep` annotation to `templates/pvc.yaml`
6. Fix security contexts as non-parameterisable in `templates/deployment.yaml`
7. Create `helm/devops-chatbot/README.md` documenting out-of-chart resources
8. Run `helm lint --strict helm/devops-chatbot/` — must exit 0

### Phase 2: CI Workflow Migration (deploy.yml)

**Goal**: Replace `kubectl apply` pattern in `deploy.yml` with `helm upgrade --install`.

Milestones:
1. Add `azure/setup-helm@v4` step with `helm-version: '3.14.0'`
2. Add `helm lint --strict` + `helm template --dry-run` gate step
3. Replace `sed -i` image tag injection with `--set image.tag=${{ github.sha }}`
4. Replace `kubectl create secret --dry-run` (chatbot secrets) — now handled by `templates/secret.yaml`
5. Replace all `kubectl apply -f k8s/` calls with single `helm upgrade --install devops-chatbot`
6. Retain `kubectl apply` for `cert-issuer.yaml` and `kyverno-policies.yaml` as explicit pre-steps
7. Set `concurrency: cancel-in-progress: false` on deploy job
8. Validate: `grep -r "sed.*image" .github/` returns empty

### Phase 3: k8sgpt Operator Config Updates

**Goal**: Upgrade operator chart version, add analyzer and Trivy integration, update CI workflow.

Milestones:
1. Update `k8sgpt/helm-values.yaml` — add `dynamicRBAC: true`; update chart version comment to `0.2.27`
2. Update `k8sgpt/k8sgpt-openrouter-cr.yaml` — add `ConfigMap` to filters; add `integrations.trivy` block
3. Update `deploy-k8sgpt.yml` — add `azure/setup-helm@v4`; bump chart `--version` to `0.2.27`
4. Replace `kubectl apply -f k8sgpt/ai-secret.yaml` with `kubectl create secret --dry-run | kubectl apply` sourced from `${{ secrets.OPENROUTER_API_KEY }}`
5. Confirm `helm upgrade --install alloy grafana/alloy --values k8sgpt/Alloy/alloy-values.yaml` is correctly sequenced with supplementary `kubectl apply` steps

### Phase 4: Cleanup and Validation

**Goal**: Remove deprecated raw manifests; validate end-to-end.

Milestones:
1. Delete `k8s/deployment.yaml`, `k8s/service.yaml`, `k8s/ingress.yaml`, `k8s/pvc.yaml`, `k8s/serviceaccount.yaml`, `k8s/pdb.yaml`, `k8s/resourcequota.yaml`, `k8s/secrets.yaml` (after Helm chart is deployed and validated)
2. Delete `k8sgpt/ai-secret.yaml` (replaced by `kubectl create secret --dry-run` in CI)
3. Run `helm template helm/devops-chatbot/ --set image.tag=test` — confirm exactly 8 resource kinds
4. Run `grep -r "sk-\|ASIA\|AKIA" helm/devops-chatbot/` — confirm zero matches
5. Run smoke test: `GET /api/health` and `GET /api/health/ready` return HTTP 200 post-deploy

---

## Complexity Tracking

No constitution violations found. No complexity justification required.
