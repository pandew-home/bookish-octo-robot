# Helm Migration Checklist: DevOps Chatbot v2.0

**Purpose**: Validate the quality, completeness, and clarity of requirements for migrating the deployment from GitHub Actions + `kubectl apply` raw manifests to GitHub Actions + `helm upgrade --install` with a `values.yaml` / `values-override` strategy. Covers the chatbot application (`k8s/`), the K8sGPT operator (`k8sgpt/`), and the Grafana/Alloy observability stack.
**Created**: 2026-04-03
**Feature**: [specs/001-devops-chatbot-v2/spec.md](../spec.md)
**Audience**: Author (pre-PR)
**Depth**: Standard

---

## Requirement Completeness

- [ ] CHK001 — Are requirements defined for which Kubernetes resources currently in `k8s/` (Deployment, Service, Ingress, PVC, ServiceAccount, PDB, ResourceQuota, NetworkPolicy, CertIssuer) map to Helm chart templates? [Completeness, Gap]
- [ ] CHK002 — Are requirements specified for how the K8sGPT operator is deployed via Helm — both the operator itself (existing `k8sgpt/helm-values.yaml`) and the `K8sGPT` custom resource (`k8sgpt-openrouter-cr.yaml`)? [Completeness, Gap]
- [ ] CHK003 — Are requirements defined for how the Grafana/Alloy observability stack (`k8sgpt/Alloy/`) is managed — via a sub-chart, separate Helm release, or raw manifests? [Completeness, Gap]
- [ ] CHK004 — Is there a documented requirement for which configuration keys belong in `values.yaml` (default, committed to git) versus `values-override` files (env-specific, secret, `.gitignore`d)? [Completeness, Gap]
- [ ] CHK005 — Are requirements specified for where the `values-override` file(s) are sourced during CI — GitHub Actions secrets, a Vault lookup, or environment-specific file? [Completeness, Gap]
- [ ] CHK006 — Are requirements defined for how Kubernetes Secrets (`devops-chatbot-secrets`, `ghcr-pull-secret`, `k8sgpt-ai-secret`) are injected at `helm upgrade` time — `--set`, `--set-string`, or external secrets operator? [Completeness, Gap]
- [ ] CHK007 — Is there a requirement specifying what happens to the existing `sed`-based image tag injection (`sed -i "s|image: .*|..."`) when replaced by Helm — is `image.tag` set via `--set image.tag=$SHA` or baked into a values-override file? [Completeness, Gap]
- [ ] CHK008 — Are rollback requirements defined — specifying whether a failed `helm upgrade` automatically triggers `helm rollback` or leaves the previous release running? [Completeness, Gap]

---

## Requirement Clarity

- [ ] CHK009 — Is "values-override strategy" defined with specific file naming conventions, override precedence order, and the expected number of override files (e.g., one per environment vs. one per secret category)? [Clarity, Gap]
- [ ] CHK010 — Is FR-010 ("all runtime config in Helm `values.yaml`") sufficiently specific to distinguish what belongs in `values.yaml` vs. `ConfigMap` vs. `Secret` for the chatbot — the current spec lists all three without priority or separation of concerns? [Clarity, Spec §FR-010]
- [ ] CHK011 — Is the term "smoke test" in the current deploy workflow (`POST /api/health`, `POST /api/health/ready`) referenced in requirements with an explicit pass/fail threshold — or is it only described in the workflow file? [Clarity, Gap]
- [ ] CHK012 — Is the Helm release name (`devops-chatbot`) and namespace strategy (`devops-chatbot`) explicitly stated in requirements, or assumed from raw manifest conventions? [Clarity, Gap]
- [ ] CHK013 — Is `helm upgrade --install` vs. `helm install` + `helm upgrade` (idempotent vs. two-step) explicitly specified, or is the CI idempotency requirement left implicit? [Clarity, Gap]
- [ ] CHK014 — Are `helm lint` and `helm template` validation steps required as a CI gate before deployment, or only deployment-time validation? [Clarity, Gap]

---

## Requirement Consistency

- [ ] CHK015 — Does the requirements spec (FR-010) align with the existing `k8s/secrets.yaml` pattern, which uses `kubectl create secret --dry-run | kubectl apply` for secret management — or does the Helm approach require a breaking change to that pattern? [Consistency, Spec §FR-010]
- [ ] CHK016 — Are image repository references consistent across requirements — `ghcr.io/${{ github.repository }}` is the current standard; is this the expected `image.repository` value in `values.yaml` with `image.tag` overridden per deploy? [Consistency, Spec §FR-010]
- [ ] CHK017 — Does the K8sGPT operator Helm release strategy (which already has `k8sgpt/helm-values.yaml`) align with the chatbot Helm release strategy? Are they separate releases with separate lifecycle management requirements defined? [Consistency, Gap]
- [ ] CHK018 — Are resource limits/requests (`cpu`, `memory`) currently hardcoded in `k8s/deployment.yaml` required to be parameterised in `values.yaml` — or can they remain at fixed values? The current spec does not address this split. [Consistency, Gap]

---

## Acceptance Criteria Quality

- [ ] CHK019 — Are acceptance criteria for a successful Helm deploy measurable — e.g., `helm upgrade` exits 0, `kubectl rollout status` within 300s, health endpoints return HTTP 200? The current spec has these only in the workflow YAML, not in requirements. [Acceptance Criteria, Gap]
- [ ] CHK020 — Is there a measurable acceptance criterion for what constitutes a correctly structured Helm chart — e.g., `helm lint` passes, `helm template` renders all expected resources, all values from `k8s/` are parameterised? [Acceptance Criteria, Gap]
- [ ] CHK021 — Are acceptance criteria defined for the `values-override` strategy — e.g., deploying with only `values.yaml` (no override) renders a deployable but non-production chart, and deploying with override produces the production configuration? [Acceptance Criteria, Gap]

---

## Scenario Coverage

- [ ] CHK022 — Are requirements defined for the first-time install scenario (`helm install`) vs. upgrade scenario (`helm upgrade`) — specifically whether the CI workflow must handle both idempotently? [Coverage, Spec §FR-010]
- [ ] CHK023 — Is the cluster credential setup scenario (Civo API key → `civo kubernetes config` → `kubectl`/`helm` context) required to remain unchanged, or are there requirements for replacing it with a kubeconfig secret? [Coverage, Gap]
- [ ] CHK024 — Are requirements specified for what happens when `helm upgrade` fails mid-deploy — does it leave a `FAILED` release state, and is there a `--atomic` (auto-rollback) requirement? [Coverage, Exception Flow]
- [ ] CHK025 — Is there a requirement covering the Grafana/Alloy stack upgrade path — the Alloy stack in `k8sgpt/Alloy/` has raw manifests and a separate ArgoCD application; is this included in the Helm migration scope or explicitly excluded? [Coverage, Spec §FR-010]
- [ ] CHK026 — Is the CertManager `ClusterIssuer` (`k8s/cert-issuer.yaml`) deployment requirement addressed — currently applied with `|| echo "cert-manager not installed"` fallback; is this fallback behaviour a requirement or an implementation detail to be formalised? [Coverage, Edge Case]

---

## Edge Case Coverage

- [ ] CHK027 — Are requirements defined for the case where the Helm release already exists in a `FAILED` state when CI runs — is `--force` or `--reset-values` needed, and is this a documented requirement? [Edge Case, Gap]
- [ ] CHK028 — Is the PVC (`k8s/pvc.yaml`) life cycle during Helm upgrades addressed in requirements — Helm does not delete PVCs on `helm uninstall` by default; is this the required behaviour, and is it specified? [Edge Case, Gap]
- [ ] CHK029 — Are requirements defined for the `git-sha` label currently injected via `sed` (`git-sha: "${{ github.sha }}"`) — is this to become a Helm value (`podLabels.git-sha: {{ .Values.image.tag }}`), and is this traceability requirement documented? [Edge Case, Spec §FR-010]
- [ ] CHK030 — Is there a Helm-specific security requirement for the `readOnlyRootFilesystem`, `runAsNonRoot`, and `seccompProfile` security context values — are these fixed in templates or parameterisable, and is this posture documented as a requirement? [Edge Case, Security]

---

## Non-Functional Requirements

- [ ] CHK031 — Are Helm chart versioning requirements defined — specifically whether `Chart.yaml` `version` and `appVersion` must be kept in sync with the image tag / git SHA, and who is responsible for bumping them? [Non-Functional, Gap]
- [ ] CHK032 — Is there a requirement that the Helm chart passes `helm lint --strict` as a CI gate — or is only deployment-time correctness required? [Non-Functional, Gap]
- [ ] CHK033 — Are idempotency requirements explicitly stated for the full CI pipeline (`helm upgrade --install` run twice on the same SHA must produce no change) — this is assumed but not documented in the spec? [Non-Functional, Gap]
- [ ] CHK034 — Is there a performance requirement for Helm deploy time — the current `kubectl rollout status --timeout=300s` implies a 5-minute budget; is this carried forward as an explicit requirement for the Helm path? [Non-Functional, Spec §FR-010]

---

## Dependencies & Assumptions

- [ ] CHK035 — Is the assumption that `helm` CLI is available on the GitHub Actions runner (via `azure/setup-helm` or pre-installed) documented as a dependency? [Dependency, Gap]
- [ ] CHK036 — Is the dependency on the Civo CLI (`civo kubernetes config`) for kubeconfig generation documented — and is there a requirement to replace or retain it when switching to Helm? [Dependency, Gap]
- [ ] CHK037 — Is the dependency on `ghcr.io` as the container registry made explicit in values requirements — and is there a requirement for `imagePullSecrets` to be managed via Helm rather than the current `kubectl create secret --dry-run` pattern? [Dependency, Gap]
- [ ] CHK038 — Is there a documented assumption about the Helm version required — the `--atomic` flag behaviour and `--wait` flag semantics differ between Helm 3.x minor versions; is a minimum version specified? [Assumption, Gap]

---

## Ambiguities & Conflicts

- [ ] CHK039 — Does the existing requirement FR-010 conflict with the current practice of injecting secrets via `kubectl create secret` in CI (bypassing `values.yaml` entirely)? If secrets are never in `values.yaml`, the scope of FR-010 for the Helm migration needs clarification — what specifically moves into Helm management? [Conflict, Spec §FR-010]
- [ ] CHK040 — Is there an ambiguity in scope between the chatbot Helm chart and the K8sGPT operator Helm chart — the existing `k8sgpt/helm-values.yaml` suggests the operator already uses Helm, but the CI workflow only uses `kubectl apply`; is the CI for the operator also in scope for this migration? [Ambiguity, Gap]
- [ ] CHK041 — Is "values-override strategy" intended to support multiple environments (dev/staging/prod) or only secrets/per-deploy overrides on the single Civo cluster? The distinction changes which values are parameterised. [Ambiguity, Gap]
