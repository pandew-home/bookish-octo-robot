# Research: Helm CI/CD Migration

**Feature**: `001-devops-chatbot-v2` — Helm-Based CI/CD Migration  
**Produced by**: `/speckit.plan` Phase 0  
**Date**: 2026-04-03

---

## 1. k8sgpt CLI / Engine Version

**Decision**: Keep `spec.version: v0.4.31` in the K8sGPT CR.  
**Rationale**: `v0.4.31` is the current latest k8sgpt engine release. The CR already pins this version. No upgrade is needed for the engine itself.  
**Alternatives considered**: Upgrading to a hypothetical newer version — none exists at time of research.

---

## 2. k8sgpt-operator Helm Chart Version

**Decision**: Upgrade from Helm chart `0.2.26` → `0.2.27`.  
**Rationale**: `v0.2.27` (released 2026-03-28) is the latest operator release. Key changes:
- `dynamicRBAC` now defaults to `true` (opt-out instead of opt-in) — operator automatically provisions RBAC for the resources it needs to analyse, removing the need for manual ClusterRole grants.
- CRDs moved from `templates/` to `crds/` for proper Helm 3 lifecycle management (prevents accidental CRD deletion on `helm uninstall`).
- `v0.2.26` fixes: removed broken `--filter` flag on `k8sgpt serve` (was causing crashloopbackoff in certain configs), `K8SGPT_TOP_P=0` fix for Anthropic, proper `use: 'latest'` when version unspecified.
- Support for `deploymentLabels` and `deploymentAnnotations` on the K8sGPT CRD — useful for future Grafana annotation tracking.

**Migration impact**: `dynamicRBAC: true` default means the operator chart must have permission to create ClusterRoles/ClusterRoleBindings. The existing `helm-values.yaml` may need `dynamicRBAC: true` explicitly set to confirm intent.  
**Alternatives considered**: Staying on `0.2.26` — rejected because `0.2.27` is stable and the CRD placement fix is a correctness improvement.

---

## 3. Available k8sgpt Analyzers (vs. Current CR)

### Built-in Core Analyzers (default, no explicit listing required)
Pod, Deployment, ReplicaSet, PersistentVolumeClaim, Service, Ingress, StatefulSet, Job, CronJob, Node, ValidatingWebhookConfiguration, MutatingWebhookConfiguration, **ConfigMap**

### Optional Analyzers (must be explicitly listed in `spec.filters`)
HorizontalPodAutoscaler, PodDisruptionBudget, NetworkPolicy, Log, GatewayClass, Gateway, HTTPRoute

### Analyzers Added in Recent Versions (v0.4.23/v0.4.24)
- `ClusterCatalog`, `ClusterExtension` (v0.4.23) — OLM v1 resources
- `ClusterServiceVersion`, `Subscription`, `InstallPlan`, `OperatorGroup`, `CatalogSource` (v0.4.24) — OLM/Operator Framework resources

**Current CR filters** (19 items): Pod, Log, Deployment, ReplicaSet, StatefulSet, Node, HorizontalPodAutoscaler, PersistentVolumeClaim, Service, Ingress, CronJob, Job, NetworkPolicy, PodDisruptionBudget, MutatingWebhookConfiguration, ValidatingWebhookConfiguration, GatewayClass, Gateway, HTTPRoute

**Decision**: Add `ConfigMap` to the CR filters list. OLM analyzers excluded.  
**Rationale**: `ConfigMap` is a core analyzer — detects misconfigured ConfigMaps (missing required keys, invalid data). OLM (ClusterCatalog, ClusterExtension, ClusterServiceVersion, Subscription, InstallPlan, OperatorGroup, CatalogSource) is not installed on k3s and has no counterpart in this cluster's workload. Including them would add API calls that will always 404 and pollute logs. Total: 20 analyzers covering all resource types present on this cluster.

---

## 4. k8sgpt AI Skills / Integrations

### Trivy Integration
**Decision**: Enable `spec.integrations.trivy.enabled: true` with `skipInstall: true`.  
**Rationale**: Trivy lets k8sgpt include CVE and vulnerability context in its analysis of pods — directly relevant for a DevOps chatbot that surfaces actionable remediation steps. `skipInstall: true` avoids installing the Trivy Operator; k8sgpt uses Trivy CLI/reports if available, and degrades gracefully if not.  
**Tradeoff**: If Trivy is not present in the cluster, this setting has no effect but also no cost.

### Slack / Webhook Sink
**Decision**: Defer — add as a future enhancement, not in scope for Helm migration.  
**Rationale**: k8sgpt supports `spec.sink` (Slack, Mattermost, CloudEvents). Sending analysis results to a Slack channel on new findings is a high-value DevOps skill (proactive alerting). However, it requires a Slack webhook URL secret and a new GitHub Actions secret. Adding it as a follow-on `spec.sink` block in the CR is low-effort and well-isolated.

### Backstage Integration
**Decision**: Out of scope. No Backstage instance exists.  
**Rationale**: `spec.extraOptions.backstage.enabled: true` pushes k8sgpt results into a Backstage developer portal. Noted for future consideration.

### MCP Server (k8sgpt as MCP tool)
**Decision**: Out of scope for this migration.  
**Rationale**: k8sgpt v0.4.27+ exposes cluster analysis as MCP tools, enabling AI agents to call k8sgpt directly. Integrating MCP into the chatbot's agentic engine is a separate feature.

### Custom Analyzer (gRPC)
**Decision**: Document the extension point; defer implementation.  
**Rationale**: Custom analyzers require a gRPC server implementing the k8sgpt analyzer proto interface. No custom analyzer is planned currently but the `spec.customAnalyzers[].connection` field is available.

---

## 5. Helm CI Best Practices for GitHub Actions

**Decision**: Use `azure/setup-helm@v4` with `helm-version: '3.14.0'` pinned; run `helm lint --strict` + `helm template > /dev/null` as hard CI gates before cluster access.  
**Rationale**:
- `azure/setup-helm@v4` is the maintained GitHub-official Helm installer action.
- Pinning `3.14.0` avoids the broken `--wait` behaviour in early Helm 3.x and aligns with current LTS.
- `helm lint --strict` catches template warnings as errors (prevents subtle misconfigurations from slipping through).
- `helm template` dry run validates rendering without cluster access (fast gate).

**Alternatives considered**:
- `helm/chart-testing-action` — designed for chart libraries, not application charts; overkill for a single-app chart.
- `helm/chart-releaser-action` — for publishing charts to chart repos; not applicable to a private application chart.
- `helm diff` plugin in CI — useful for PR preview but adds complexity; deferred to optional enhancement.

---

## 6. Raw Manifest Cleanup Scope

### Into Helm Chart (`helm/devops-chatbot/templates/`)
| File (current `k8s/`) | Template |
|---|---|
| `deployment.yaml` | `templates/deployment.yaml` |
| `service.yaml` | `templates/service.yaml` |
| `ingress.yaml` | `templates/ingress.yaml` |
| `pvc.yaml` | `templates/pvc.yaml` |
| `serviceaccount.yaml` | `templates/serviceaccount.yaml` |
| `pdb.yaml` | `templates/pdb.yaml` |
| `resourcequota.yaml` | `templates/resourcequota.yaml` |
| `secrets.yaml` (pattern) | `templates/secret.yaml` (from `--set` values) |

### Stays as `kubectl apply` (Out-of-Chart)
| File | Reason |
|---|---|
| `k8s/kyverno-policies.yaml` | ClusterPolicy resources; cluster-scoped; global scope (ASM-004) |
| `k8s/cert-issuer.yaml` | ClusterIssuer; cluster-scoped; shared with other workloads (ASM-005) |
| `k8sgpt/Alloy/alloy-rbac.yaml` | ClusterRole/ClusterRoleBinding for Alloy scraper; cluster-scoped |
| `k8sgpt/Alloy/alloy-cleanup-cronjob.yaml` | Supplementary manifest not integrated into Alloy chart values |
| `k8sgpt/Alloy/k8sgpt-result-scraper.yaml` | Custom scraper; out of upstream Alloy chart scope |
| `k8sgpt/ai-secret.yaml` | Replaced by `kubectl create secret --dry-run | kubectl apply` pattern in CI |

### k8sgpt Alloy Deployment
The `k8sgpt/Alloy/alloy-values.yaml` is already in Helm values format. The `helm upgrade --install alloy grafana/alloy --values k8sgpt/Alloy/alloy-values.yaml` command replaces any current `kubectl apply -f` calls for the Alloy Helm release itself. Supplementary raw manifests (alloy-rbac.yaml, alloy-cleanup-cronjob.yaml, k8sgpt-result-scraper.yaml) are applied via `kubectl apply` after the Alloy Helm upgrade in the same CI step.

---

## 7. Cluster-Specific Items (Ingress, Grafana, Alloy)

**Decision**: Cluster-specific configuration (ingress host, storage class, namespace) remains in `values.yaml` as committed defaults (single-cluster deployment). No per-environment values files are created (ASM-001).

**Ingress**: The ingress hostname (`ingress.host`) is committed in `values.yaml` as a non-secret default. TLS cert-manager annotation is fixed in the template (non-parameterisable) since there is only one cert issuer.

**Grafana/kube-prometheus-stack**: Already deployed; `helm upgrade --install kube-prometheus-stack --reuse-values` pattern retained as-is (ASM-007). No new chart created.

**Alloy observability**: Uses upstream `grafana/alloy` chart with `k8sgpt/Alloy/alloy-values.yaml`. Alloy is deployed in its own CI job/step, independent of the chatbot deploy, so Alloy failures do not block chatbot deployment (US3 / FR-H-003).

---

## 8. k8sgpt-operator dynamicRBAC Impact

**Decision**: Explicitly set `dynamicRBAC: true` in `k8sgpt/helm-values.yaml` for clarity, even though `0.2.27` defaults to true.  
**Rationale**: Explicit is safer — the operator needs ClusterRole/ClusterRoleBinding permissions to create the RBAC resources for the `ConfigMap` and other analyzers. Adding `ConfigMap` to the filter list triggers dynamic RBAC to provision the necessary read access automatically.

---

## Summary of Resolved Unknowns

| Unknown | Resolution |
|---|---|
| k8sgpt CLI latest version | `v0.4.31` — already pinned; no change |
| k8sgpt-operator latest Helm chart | `0.2.27` — upgrade from `0.2.26` |
| New analyzers worth adding | `ConfigMap` only; OLM excluded (not installed on k3s) |
| AI skills/extensions | Enable Trivy integration; MCP server deferred |
| Helm CI action choice | `azure/setup-helm@v4` with pinned `3.14.0` |
| Raw manifest cleanup scope | 8 into chart; 6 remain as kubectl apply (documented above) |
| Alloy deployment approach | Helm chart with supplementary kubectl apply steps |
| dynamicRBAC | Set explicitly `true` in helm-values.yaml |
