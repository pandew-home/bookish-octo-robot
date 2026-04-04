# Feature Specification: Helm-Based CI/CD Migration

**Feature Branch**: `helm-cicd-migration`  
**Created**: 2026-04-03  
**Status**: Draft  
**Extends**: [spec.md](spec.md) — Requirement FR-010 (Deployment and Infrastructure)

> **HARD SCOPE BOUNDARY**: This feature covers Helm chart creation and CI/CD workflow changes **only**.
> - `backend/`, `frontend/`, `libs/` application code MUST NOT be changed.
> - Grafana dashboard JSON files MUST NOT be changed.
> - Existing CI tests MUST NOT be removed. New tests may be added or existing test steps may be skipped (using `if:` conditions) where required to accommodate Helm, but zero test deletions are permitted.
> - All changes are confined to: `helm/`, `.github/workflows/deploy.yml`, `.github/workflows/deploy-k8sgpt.yml`, `k8sgpt/helm-values.yaml`, `k8sgpt/k8sgpt-openrouter-cr.yaml`, and retained `k8s/cert-issuer.yaml` / `k8s/kyverno-policies.yaml`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Platform Engineer Deploys Chatbot via Helm (Priority: P1)

A platform engineer merges a change to `main`. GitHub Actions builds the container image, runs `helm lint` and `helm template` as gates, then executes `helm upgrade --install devops-chatbot helm/devops-chatbot/ --set image.tag=$SHA --set <secret-keys>`. The chatbot rolls out in the `devops-chatbot` namespace and the existing PVC is preserved. Health endpoints return HTTP 200 within 300 seconds.

**Why this priority**: Core delivery pipeline — without this, no other user story is reachable.

**Independent Test**: Push a commit that only changes `backend/app.py`. The workflow builds a new image, lints the chart, and deploys. `kubectl rollout status` exits 0. Health endpoint returns 200.

**Acceptance Scenarios**:

1. **Given** a commit is pushed to `main`, **When** the `Build & Deploy` workflow runs, **Then** `helm lint helm/devops-chatbot/` exits 0 before any cluster interaction occurs.
2. **Given** `helm lint` passes, **When** `helm upgrade --install` is executed with `--wait --timeout=300s --atomic`, **Then** the command exits 0 and all Deployment pods reach `Running` state.
3. **Given** the release already exists (upgrade scenario), **When** `helm upgrade --install` is re-executed with the same SHA, **Then** no resources are modified and the command exits 0 (idempotent run).
4. **Given** the release does not yet exist (first install), **When** `helm upgrade --install` is executed, **Then** the release is created, all resources are created, and the command exits 0 without pre-existing state being required.
5. **Given** `helm upgrade` fails mid-rollout (e.g., image pull error), **When** the `--atomic` flag is active, **Then** Helm automatically rolls back to the previous revision and the workflow exits non-zero to fail the CI job.
6. **Given** a successful deploy, **When** the smoke test step runs `curl /api/health` and `curl /api/health/ready`, **Then** both return HTTP 200 within 30 seconds of the `helm upgrade` command completing.

---

### User Story 2 — Platform Engineer Deploys K8sGPT Operator via Helm (Priority: P2)

A platform engineer changes `k8sgpt/helm-values.yaml` or the K8sGPT custom resource. The `Deploy K8sGPT Operator & Observability` workflow runs `helm upgrade --install` for the operator (replacing the existing `kubectl apply -f` calls for the CR and secret). The operator secret is injected via `--set` from GitHub Actions secrets, not written to any file.

**Why this priority**: K8sGPT results drive the cluster health widget and chat enrichment — breakages here surface as degraded functionality.

**Independent Test**: Change `k8sgpt/helm-values.yaml` (e.g., adjust `resultLogging` flag). The workflow runs, upgrades the operator, and `kubectl get k8sgpt -n k8sgpt-operator-system` shows the updated resource.

**Acceptance Scenarios**:

1. **Given** `k8sgpt/helm-values.yaml` is updated, **When** the workflow runs, **Then** `helm upgrade --install k8sgpt-operator` exits 0 using `k8sgpt/helm-values.yaml` plus `--set ai.secret.name=k8sgpt-ai-secret`.
2. **Given** the `k8sgpt-ai-secret` Kubernetes Secret does not exist, **When** the workflow runs, **Then** the secret is created via `kubectl create secret --dry-run=client | kubectl apply` before the Helm release, and its value is sourced exclusively from the `OPENROUTER_API_KEY` GitHub Actions secret.
3. **Given** the K8sGPT custom resource (`k8sgpt-openrouter-cr.yaml`) is applied after operator install, **When** `kubectl wait k8sgpt/k8sgpt-openrouter --for=condition=Ready --timeout=120s` runs, **Then** it exits 0 within 120 seconds.
4. **Given** the operator Helm release is in a `FAILED` state from a prior run, **When** the workflow runs `helm upgrade --install`, **Then** the upgrade succeeds without requiring manual `helm delete` or `--force`.

---

### User Story 3 — Platform Engineer Deploys Alloy Observability Stack (Priority: P3)

The Grafana Alloy observability stack is deployed (or upgraded) in the `monitoring` namespace using a dedicated `helm upgrade --install alloy` step. Raw manifest files (`alloy-rbac.yaml`, `alloy-cleanup-cronjob.yaml`, `k8sgpt-result-scraper.yaml`) that cannot be expressed as Helm values remain as supplementary `kubectl apply` calls in the same CI step, explicitly noted as out-of-chart scope in the spec.

**Why this priority**: Observability is secondary to the chatbot and operator being healthy. Alloy failures must not block chatbot or K8sGPT deployment steps.

**Independent Test**: Modify `k8sgpt/Alloy/alloy-values.yaml`. The workflow upgrades only the Alloy release. The chatbot and K8sGPT steps are not re-triggered.

**Acceptance Scenarios**:

1. **Given** `k8sgpt/Alloy/alloy-values.yaml` is changed, **When** the K8sGPT workflow runs, **Then** `helm upgrade --install alloy grafana/alloy --values k8sgpt/Alloy/alloy-values.yaml` exits 0.
2. **Given** the Alloy Helm step fails, **When** the workflow evaluates job status, **Then** the chatbot deploy job and K8sGPT operator deploy job are unaffected (Alloy is a separate, non-blocking job or a `continue-on-error: true` step).
3. **Given** the `kube-prometheus-stack` upgrade step runs, **When** it completes, **Then** it uses `--reuse-values` so that existing Grafana dashboards and datasources are not reset.

---

### User Story 4 — Developer Validates Chart Locally Before Push (Priority: P3)

A developer runs `helm lint helm/devops-chatbot/` and `helm template helm/devops-chatbot/ --set image.tag=local-test` locally and gets clean output before pushing, reducing CI failures.

**Why this priority**: Developer experience — reduces wasted CI runs but does not block delivery.

**Independent Test**: Clone the repository, run `helm lint helm/devops-chatbot/` with no cluster access. The command exits 0 and produces no errors or warnings.

**Acceptance Scenarios**:

1. **Given** a developer clones the repository and has `helm` installed, **When** they run `helm lint helm/devops-chatbot/`, **Then** the command exits 0 with zero errors.
2. **Given** `helm template helm/devops-chatbot/ --set image.tag=test-sha`, **When** the command runs, **Then** it renders all expected resource kinds: `Deployment`, `Service`, `Ingress`, `PersistentVolumeClaim`, `ServiceAccount`, `PodDisruptionBudget`, `ResourceQuota`, and outputs valid YAML.
3. **Given** `helm template` output is piped to `kubeval` or `kubectl --dry-run=client`, **When** the validation runs, **Then** all resources pass schema validation.

---

### Edge Cases

- What happens when `helm upgrade --atomic` triggers rollback but the previous revision's image is no longer in GHCR? The rollback will produce an `ImagePullBackOff` and the release will remain in a degraded state — the workflow must alert but cannot automatically recover; this is accepted behaviour and must be documented.
- What happens when the PVC exists from a prior Helm-managed release and `helm uninstall` is called? By default Helm does not delete PVCs. The PVC lifecycle must be managed independently, and this must be explicitly encoded in the `Chart.yaml` with `keep` annotation or documented as an operational procedure.
- What happens when GitHub Actions secrets (`LLM_API_KEY`, `OPENROUTER_API_KEY`, `CIVO_API_KEY`) are rotated mid-pipeline? The current run uses the at-pipeline-start value; rotation takes effect on the next run. No additional handling is needed.
- What happens when `helm upgrade` is triggered concurrently by two commits in rapid succession? GitHub Actions environment concurrency controls must be set to `cancel-in-progress: false` (queue, not cancel) to prevent partial upgrade states. This is a CI configuration requirement, not a Helm requirement.
- What happens when `helm lint --strict` fails on a template that was previously deployed via raw `kubectl apply`? The CI gate blocks deployment — this is the intended behaviour to enforce chart quality.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Chart Structure

- **FR-H-001**: The system MUST include a Helm chart at `helm/devops-chatbot/` with a `Chart.yaml`, `values.yaml`, and `templates/` directory containing exactly the following 8 template files: Deployment, Service, Ingress, PersistentVolumeClaim, ServiceAccount, PodDisruptionBudget, ResourceQuota, and Secret (the Secret template replaces the `kubectl create secret --dry-run` pattern; see FR-H-009). `ClusterIssuer` is explicitly **excluded** from the chart — it is cluster-scoped and applied via `kubectl apply` per ASM-005.
- **FR-H-002**: The `helm/devops-chatbot/Chart.yaml` MUST declare `name: devops-chatbot`, `type: application`, a semantic `version` field (chart schema version, starting `0.1.0`), and an `appVersion` field set to `latest` as the committed default.
- **FR-H-003**: The `helm/devops-chatbot/values.yaml` MUST define all configuration that is non-secret and environment-independent as committed defaults, including: `image.repository` (`ghcr.io/<owner>/<repo>`), `image.tag` (`latest`), `image.pullPolicy` (`IfNotPresent`), `replicaCount` (`1`), `namespace` (`devops-chatbot`), `ingress.host`, `resources.requests`, `resources.limits`, `pvc.storageSize`, `pvc.storageClass`, `service.port`, `serviceAccount.name`, `pdb.minAvailable`, `resourceQuota.*`, and `podLabels` (including the `git-sha` label key).
- **FR-H-004**: The `helm/devops-chatbot/values.yaml` MUST NOT contain any secret values. Fields requiring secrets (`llmApiKey`, `llmProvider`, `llmModel`, `defaultRegion`, `ghcrPullSecretData`) MUST exist as empty-string placeholders with a comment indicating they are injected at deploy time.
- **FR-H-005**: The `kyverno-policies.yaml` content, if it contains ClusterScoped resources not appropriate for chart-level management, MAY be excluded from the Helm chart and continue to be applied via `kubectl apply -f k8s/kyverno-policies.yaml` in CI; this exclusion MUST be documented in the chart's `README.md`.
- **FR-H-006**: Security context values (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `seccompProfile.type: RuntimeDefault`) MUST be fixed (non-parameterisable) in the Deployment template and not exposed in `values.yaml`, to prevent accidental weakening via value override.

#### Values and Override Strategy

- **FR-H-007**: The deployment pipeline MUST follow a two-layer values strategy: Layer 1 is `values.yaml` (committed defaults), Layer 2 is `--set key=value` flags passed at `helm upgrade` time for secrets and the image tag. There is no `values-override.yaml` file committed or expected in the repository. The override strategy is secrets-injection-only, not multi-environment (see Assumptions).
- **FR-H-008**: The image tag MUST be injected at deploy time via `--set image.tag=${{ github.sha }}` and MUST NOT be committed in `values.yaml` or any file tracked by git.
- **FR-H-009**: Kubernetes Secrets for the chatbot (`LLM_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `DEFAULT_REGION`) MUST be injected via `--set` flags sourced from GitHub Actions secrets. The Helm chart MUST contain a `templates/secret.yaml` template that creates the Kubernetes Secret resource from these values. The `k8s/secrets.yaml` `kubectl create secret --dry-run` pattern MUST be retired and replaced by this template.
- **FR-H-010**: The `ghcr-pull-secret` (`imagePullSecret`) MUST be created via a `helm upgrade --install` pre-hook (`helm.sh/hook: pre-install,pre-upgrade`) or a dedicated `kubectl create secret docker-registry --dry-run | kubectl apply` step in CI before the Helm release. This choice MUST be explicitly documented in the workflow file. The pull secret MUST be referenced in `values.yaml` under `imagePullSecrets[0].name`.

#### CI Gates

- **FR-H-011**: The `Build & Deploy` workflow MUST include a `Helm Validate` step that runs both of the following commands before any cluster connection is established. If either exits non-zero the workflow MUST fail and skip all subsequent deploy steps:
  1. `helm lint --strict helm/devops-chatbot/`
  2. `helm template helm/devops-chatbot/ --set image.tag=lint-check > /dev/null`
- **FR-H-012**: The `Deploy K8sGPT Operator & Observability` workflow MUST NOT require `helm lint` for the upstream `k8sgpt-operator` chart (it is an external chart). It MUST verify `helm repo update` succeeds before running `helm upgrade --install`.
- **FR-H-013**: The `helm` CLI MUST be installed on the GitHub Actions runner via `azure/setup-helm@v4` with a pinned minimum version of `3.14.0`. The version MUST be specified explicitly; the runner default MUST NOT be relied upon.

#### Deployment Behaviour

- **FR-H-014**: The `helm upgrade --install devops-chatbot` command MUST use `--wait --timeout=300s --atomic`. The `--wait` flag waits for all resources to be ready. The `--atomic` flag rolls back the release automatically if the timeout is exceeded or any resource fails to become ready.
- **FR-H-015**: The Helm release name for the chatbot MUST be `devops-chatbot` and the target namespace MUST be `devops-chatbot`. The namespace MUST be created by the Helm chart itself (using `--create-namespace` in the `helm upgrade --install` command).
- **FR-H-016**: The `git-sha` traceability label currently injected via `sed` MUST be preserved as a pod label, set via `--set podLabels.git-sha=${{ github.sha }}` and rendered in the Deployment template as `spec.template.metadata.labels.git-sha: {{ .Values.podLabels.gitSha }}`.
- **FR-H-017**: The K8sGPT custom resource (`k8sgpt-openrouter-cr.yaml`) MUST continue to be applied via `kubectl apply -f k8sgpt/k8sgpt-openrouter-cr.yaml` after the operator Helm upgrade, as it is an application-layer CRD instance and not part of the operator chart. This is an explicit scope boundary, not a gap.
- **FR-H-018**: The `ClusterIssuer` from `k8s/cert-issuer.yaml` MUST be applied with the existing `|| echo "cert-manager not installed"` fallback pattern, either via a dedicated `kubectl apply` step or a Helm pre-install hook with `failurePolicy: ignore`. This fallback behaviour is a documented requirement, not an implementation detail.

#### Rollback

- **FR-H-019**: A failed `helm upgrade --atomic` MUST automatically roll back to the most recent successful revision. The rollback is performed by Helm internally; no additional `helm rollback` step is needed in the workflow.
- **FR-H-020**: The workflow MUST emit the output of `helm history devops-chatbot -n devops-chatbot` in the workflow log after every deploy step (success or failure) for audit and debugging purposes.

#### Idempotency

- **FR-H-021**: Running `helm upgrade --install devops-chatbot` twice consecutively with identical values and image tag MUST produce no changes to cluster state and MUST exit 0 on both runs. A `helm diff` or `--dry-run` pre-check is NOT required but MUST be achievable without errors.
- **FR-H-022**: The PVC MUST NOT be deleted or recreated when `helm upgrade` runs. The PVC template MUST include the annotation `helm.sh/resource-policy: keep` to prevent accidental deletion on `helm uninstall`.

#### Chart Versioning

- **FR-H-023**: The `Chart.yaml` `version` field (chart schema version) MUST follow semver. It MUST be bumped manually by the developer making chart structural changes (new templates, renamed values keys, breaking changes). It MUST NOT be auto-incremented by CI.
- **FR-H-024**: The `Chart.yaml` `appVersion` field MUST be set to `"latest"` in the committed file. At deploy time the `appVersion` MUST NOT be overridden; the actual image version is communicated via the `image.tag` value and the `git-sha` pod label.

### Key Entities

- **Helm Release `devops-chatbot`**: Manages all chatbot application resources in the `devops-chatbot` namespace. Owns: Deployment, Service, Ingress, PVC (with `keep` policy), ServiceAccount, PDB, ResourceQuota, Secret.
- **Helm Release `k8sgpt-operator`**: Manages the K8sGPT operator in the `k8sgpt-operator-system` namespace. Values sourced from `k8sgpt/helm-values.yaml`. Secret (`k8sgpt-ai-secret`) created outside the chart via `kubectl`.
- **Helm Release `alloy`**: Manages Grafana Alloy in the `monitoring` namespace. Values sourced from `k8sgpt/Alloy/alloy-values.yaml`. Supplementary raw manifests (`alloy-rbac.yaml`, `alloy-cleanup-cronjob.yaml`, `k8sgpt-result-scraper.yaml`) remain as `kubectl apply` calls.
- **`values.yaml`**: Committed defaults for the `devops-chatbot` Helm chart. Contains no secrets. Is the single source of truth for all non-secret, non-ephemeral configuration.
- **CI Secret Injection Layer**: GitHub Actions secrets passed as `--set` flags at deploy time. Includes: `LLM_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `DEFAULT_REGION`, `OPENROUTER_API_KEY`, `CIVO_API_KEY`. Never written to disk or logged.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-H-001**: `helm lint helm/devops-chatbot/ --strict` exits 0 with zero errors and zero warnings on every commit to `main`, measured in CI across 10 consecutive deploys.
- **SC-H-002**: `helm upgrade --install devops-chatbot` with `--wait --timeout=300s --atomic` exits 0 and all pods reach `Running` state within 300 seconds on every successful deploy.
- **SC-H-003**: Running the same `helm upgrade --install` command twice with identical parameters produces no resource modifications on the second run (verified by `helm diff` or `kubectl get events` showing zero changes after second run).
- **SC-H-004**: A simulated deploy failure (bad image tag) triggers automatic rollback within 300 seconds, leaving the previous revision serving traffic (verified by `helm history` showing the previous revision as `DEPLOYED`).
- **SC-H-005**: The chatbot smoke test (`GET /api/health` and `GET /api/health/ready`) returns HTTP 200 on both endpoints within 30 seconds of `helm upgrade --install` exiting 0.
- **SC-H-006**: Zero secret values appear in any committed file, `helm template` output captured to CI logs, or `helm get values` output when called with `--all`. Verified by a `grep -r "sk-\|ASIA\|AKIA"` check on the chart directory in CI.
- **SC-H-007**: `helm template helm/devops-chatbot/ --set image.tag=test` renders exactly the following resource kinds: `Deployment`, `Service`, `Ingress`, `PersistentVolumeClaim`, `ServiceAccount`, `PodDisruptionBudget`, `ResourceQuota`, `Secret`. No additional or missing resources.
- **SC-H-008**: The PVC is not deleted after `helm uninstall devops-chatbot` is run in a test environment, confirmed by `kubectl get pvc -n devops-chatbot` returning the PVC with `Bound` status.
- **SC-H-009**: The existing `sed`-based image tag injection is completely removed from `deploy.yml`. Zero occurrences of `sed -i` referencing image tags remain in any workflow file, verified by `grep -r "sed.*image" .github/`.
- **SC-H-010**: The `Build & Deploy` workflow total duration for the deploy job (Helm validate + cluster auth + helm upgrade + smoke test) does not exceed 8 minutes, measured against the current `kubectl apply` baseline of approximately 5 minutes, allowing a 3-minute tolerance for the added Helm steps.

---

## Assumptions *(mandatory)*

- **ASM-001**: The override strategy covers **secrets and per-deploy ephemeral values only** (image tag, secret keys). It does NOT cover multiple environments (dev/staging/prod). The single Civo cluster is the only deployment target. If multi-environment support is added in future, a `values-<env>.yaml` file pattern can be layered on top without breaking this spec.
- **ASM-002**: The `helm` CLI minimum version is **3.14.0**. The `--atomic` flag combining rollback with `--wait` is available from Helm 3.2+. Version 3.14+ is chosen as the minimum to align with current LTS and avoid known bugs in `--wait` behaviour present in earlier 3.x minor versions.
- **ASM-003**: The K8sGPT operator CI workflow (`deploy-k8sgpt.yml`) already uses `helm upgrade --install` for the operator itself. The scope of this migration for that workflow is: (a) ensuring `azure/setup-helm` is used with a pinned version, (b) replacing `kubectl apply -f k8sgpt/ai-secret.yaml` with the `kubectl create secret --dry-run | kubectl apply` pattern, and (c) confirming the existing `--wait --timeout=120s` flags are sufficient.
- **ASM-004**: The `kyverno-policies.yaml` file contains `ClusterPolicy` resources that are cluster-scoped and apply globally. These are intentionally excluded from the `devops-chatbot` Helm chart to avoid coupling cluster-wide policies to an application release. They continue to be applied via `kubectl apply` in CI.
- **ASM-005**: The `ClusterIssuer` from `cert-issuer.yaml` is cluster-scoped and shared with other workloads. It is excluded from the `devops-chatbot` Helm chart for the same reason as Kyverno policies. It is applied as a pre-deploy `kubectl apply` step with the existing `|| echo` fallback.
- **ASM-006**: GitHub Actions `environment: production` concurrency is configured to **queue** (not cancel) concurrent runs, so that two near-simultaneous pushes cannot produce a split-brain Helm release state. This is a GitHub Actions configuration requirement outside the Helm chart scope.
- **ASM-007**: The Grafana Loki stack and `kube-prometheus-stack` are already deployed and are outside the migration scope for chart creation. The `helm upgrade --install kube-prometheus-stack --reuse-values` pattern is retained as-is; no new Helm chart is created for them.

---

## Dependencies

- **DEP-001**: `azure/setup-helm@v4` GitHub Actions action must be added to both `deploy.yml` and `deploy-k8sgpt.yml` with `helm-version: '3.14.0'` (or `>= 3.14.0`) before any Helm commands are run.
- **DEP-002**: The Civo CLI (`civo kubernetes config`) kubeconfig generation step is retained unchanged. The kubeconfig it produces is sufficient for `helm` CLI usage; no additional cluster authentication changes are required.
- **DEP-003**: The `ghcr.io` container registry is the only registry in use. The `imagePullSecrets` reference in `values.yaml` (`imagePullSecrets[0].name: ghcr-pull-secret`) must match the secret name created by CI before chart install.
- **DEP-004**: `helm repo add k8sgpt-operator` and `helm repo add grafana` must be called before their respective `helm upgrade --install` commands. These are already present in the K8sGPT workflow and must be retained.
- **DEP-005**: The `k8sgpt-operator` Helm chart version is currently pinned to `0.2.26` in the K8sGPT workflow. This pin must be preserved in the migrated workflow and documented in the workflow file with a comment indicating the pin date and minimum tested version.
