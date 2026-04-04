# Tasks: Helm-Based CI/CD Migration

**Feature**: `001-devops-chatbot-v2` | **Branch**: `001-devops-chatbot-v2`  
**Plan**: [plan.md](plan.md) | **Scope**: Deployment infrastructure + GitHub Actions only

> ## HARD SCOPE BOUNDARY
>
> **IN scope**: `helm/` chart files, `.github/workflows/deploy.yml`, `.github/workflows/deploy-k8sgpt.yml`, `k8sgpt/helm-values.yaml`, `k8sgpt/k8sgpt-openrouter-cr.yaml`, retained `k8s/cert-issuer.yaml` and `k8s/kyverno-policies.yaml`
>
> **OUT of scope — do not touch**:
> - `backend/`, `frontend/`, `libs/` — application code must not change
> - Grafana dashboard JSON files — must not change
> - `k8sgpt/Alloy/alloy-values.yaml` config content — must not change
>
> **Tests**: Existing CI test steps MUST NOT be deleted. They may be skipped via `if:` conditions where Helm changes require it. New tests may be added.

---

## Group 1: Helm Chart Scaffolding

> **Prerequisite**: None — start here.

### [X] TASK-001 — Create `helm/devops-chatbot/Chart.yaml`

**File**: `helm/devops-chatbot/Chart.yaml`  
**Action**: Create new file.

```yaml
apiVersion: v2
name: devops-chatbot
description: DevOps troubleshooting chatbot for Kubernetes
type: application
version: 0.1.0
appVersion: "latest"
```

**Done when**: File exists at `helm/devops-chatbot/Chart.yaml` with `apiVersion: v2`.

---

### [X] TASK-002 — Create `helm/devops-chatbot/values.yaml`

**File**: `helm/devops-chatbot/values.yaml`  
**Action**: Create new file with all schema fields defined in `data-model.md`.

Key fields (non-exhaustive — see data-model.md for full schema):
- `image.repository`, `image.tag`, `image.pullPolicy`
- `replicaCount`
- `service.type`, `service.port`
- `ingress.enabled`, `ingress.host`, `ingress.tls`, `ingress.className`
- `resources.requests`, `resources.limits`
- `pvc.size`, `pvc.storageClass`
- `pdb.minAvailable`
- `llm.apiKey`, `llm.provider`, `llm.model`, `llm.defaultRegion`
- `serviceAccount.name`
- `podAnnotations`, `podSecurityContext`, `securityContext`

**Done when**: `helm lint --strict helm/devops-chatbot/` exits 0 referencing the values file.

---

### [X] TASK-003 — Create `helm/devops-chatbot/.helmignore`

**File**: `helm/devops-chatbot/.helmignore`  
**Action**: Create new file.

Minimum content:
```
*.orig
*.backup
*.bak
.DS_Store
```

**Done when**: File exists.

---

### [X] TASK-004 — Create `helm/devops-chatbot/templates/_helpers.tpl`

**File**: `helm/devops-chatbot/templates/_helpers.tpl`  
**Action**: Create new file with standard Helm helpers.

Required helpers:
- `devops-chatbot.name` — chart name truncated to 63 chars
- `devops-chatbot.fullname` — release-name + chart name (63-char limit)
- `devops-chatbot.labels` — standard `app.kubernetes.io/*` labels including `helm.sh/chart`
- `devops-chatbot.selectorLabels` — `app.kubernetes.io/name` + `app.kubernetes.io/instance`
- `devops-chatbot.serviceAccountName` — resolves `serviceAccount.name` or defaults to fullname

**Done when**: `helm template helm/devops-chatbot/ --set image.tag=test` exits 0 with helpers used by all templates.

---

## Group 2: Helm Templates

> **Prerequisite**: TASK-001 through TASK-004 complete.

### [X] TASK-005 — Create `templates/serviceaccount.yaml`

**Source**: `k8s/serviceaccount.yaml`  
**File**: `helm/devops-chatbot/templates/serviceaccount.yaml`  
**Action**: Parameterise serviceaccount — use `{{ include "devops-chatbot.fullname" . }}` for name, standard labels from `_helpers.tpl`.

**Done when**: `helm template` renders a `ServiceAccount` resource with name matching release fullname.

---

### [X] TASK-006 — Create `templates/secret.yaml`

**Source**: Replaces `kubectl create secret` step in `deploy.yml`  
**File**: `helm/devops-chatbot/templates/secret.yaml`  
**Action**: Create new template rendering a `Secret` of type `Opaque`.

Required keys:
- `llm-api-key`: `{{ .Values.llm.apiKey | b64enc | quote }}`
- `llm-provider`: `{{ .Values.llm.provider | b64enc | quote }}`
- `llm-model`: `{{ .Values.llm.model | b64enc | quote }}`

Secret name: `devops-chatbot-secrets` (must match what `deployment.yaml` `envFrom` references).

> **Security**: Default `llm.apiKey` in `values.yaml` must be empty string `""`. Secret is only populated via `--set llm.apiKey=${{ secrets.OPENROUTER_API_KEY }}` at deploy time — never committed.

**Done when**: `helm template` renders a `Secret`; `grep -r "sk-\|ASIA\|AKIA" helm/devops-chatbot/` returns empty.

---

### [X] TASK-007 — Create `templates/pvc.yaml`

**Source**: `k8s/pvc.yaml`  
**File**: `helm/devops-chatbot/templates/pvc.yaml`  
**Action**: Parameterise PVC; add `keep` annotation.

Critical requirement: Add annotation to prevent Helm from deleting PVC on `helm uninstall`:
```yaml
metadata:
  annotations:
    "helm.sh/resource-policy": keep
```

Values to parameterise: `pvc.size`, `pvc.storageClass`.

**Done when**: Template renders with `helm.sh/resource-policy: keep` annotation; `helm template` exits 0.

---

### [X] TASK-008 — Create `templates/deployment.yaml`

**Source**: `k8s/deployment.yaml`  
**File**: `helm/devops-chatbot/templates/deployment.yaml`  
**Action**: Convert to Helm template. Key parameterisations:

- `spec.replicas`: `{{ .Values.replicaCount }}`
- `spec.template.spec.containers[0].image`: `{{ .Values.image.repository }}:{{ .Values.image.tag }}`
- `spec.template.spec.containers[0].imagePullPolicy`: `{{ .Values.image.pullPolicy }}`
- `spec.template.spec.containers[0].resources`: use `.Values.resources`
- `envFrom[0].secretRef.name`: `devops-chatbot-secrets` (matches TASK-006)
- `spec.template.metadata.labels`: add `git-sha: {{ .Values.podLabels.gitSha | default "" }}` so the label is present when injected at deploy time (FR-H-016)
- Security contexts: **do not parameterise** — `runAsNonRoot: true`, `readOnlyRootFilesystem: false`, `runAsUser: 1000` are fixed (Kyverno enforced)
- `imagePullSecrets`: reference `ghcr-pull-secret` (created as pre-step in CI, not by Helm)

**Done when**: `helm template` renders a `Deployment`; image tag renders correctly from `.Values.image`; `spec.template.metadata.labels` contains `git-sha` key.

---

### [X] TASK-009 — Create `templates/service.yaml`

**Source**: `k8s/service.yaml`  
**File**: `helm/devops-chatbot/templates/service.yaml`  
**Action**: Parameterise service type and port from `service.type` and `service.port`.

**Done when**: `helm template` renders a `Service` resource.

---

### [X] TASK-010 — Create `templates/ingress.yaml`

**Source**: `k8s/ingress.yaml`  
**File**: `helm/devops-chatbot/templates/ingress.yaml`  
**Action**: Parameterise ingress using `ingress.enabled`, `ingress.host`, `ingress.tls`, `ingress.className`.

Wrap entire resource in `{{- if .Values.ingress.enabled }}`.

Retain existing annotations for `cert-manager.io/cluster-issuer` and `nginx` class.

**Done when**: `helm template --set ingress.enabled=true` renders an `Ingress`; `helm template --set ingress.enabled=false` renders nothing.

---

### [X] TASK-011 — Create `templates/pdb.yaml`

**Source**: `k8s/pdb.yaml`  
**File**: `helm/devops-chatbot/templates/pdb.yaml`  
**Action**: Parameterise `minAvailable` from `pdb.minAvailable`.

**Done when**: `helm template` renders a `PodDisruptionBudget`.

---

### [X] TASK-012 — Create `templates/resourcequota.yaml`

**Source**: `k8s/resourcequota.yaml`  
**File**: `helm/devops-chatbot/templates/resourcequota.yaml`  
**Action**: Convert static manifest to Helm template with standard labels. Quota values may remain static (single cluster, no multi-environment).

**Done when**: `helm template` renders a `ResourceQuota`.

---

### [X] TASK-013 — Create `helm/devops-chatbot/README.md`

**File**: `helm/devops-chatbot/README.md`  
**Action**: Create new file documenting out-of-chart resources that require separate `kubectl apply`:

- `k8s/cert-issuer.yaml` — `ClusterIssuer` (cluster-scoped; cert-manager must be pre-installed)
- `k8s/kyverno-policies.yaml` — `ClusterPolicy` (cluster-scoped; Kyverno must be pre-installed)
- `k8sgpt/Alloy/alloy-rbac.yaml` — cluster-scoped RBAC for Alloy scraper
- `k8sgpt/Alloy/alloy-cleanup-cronjob.yaml` — supplementary CronJob outside Alloy Helm chart
- `k8sgpt/Alloy/k8sgpt-result-scraper.yaml` — ConfigMap for Alloy scraper pipeline

Also document: `ghcr-pull-secret` is a CI pre-step, not a Helm-managed resource.

**Done when**: README exists with all 5 out-of-chart resources documented.

---

### [X] TASK-014 — Validate chart with `helm lint --strict`

**Action**:
```bash
helm lint --strict helm/devops-chatbot/
```

Fix any lint errors before proceeding to Group 3.

**Done when**: Command exits 0.

---

## Group 3: `deploy.yml` GitHub Actions Migration

> **Prerequisite**: TASK-001 through TASK-014 complete (chart must exist before CI can reference it).

### [X] TASK-015 — Add `azure/setup-helm@v4` step to `deploy` job

**File**: `.github/workflows/deploy.yml`  
**Job**: `deploy`  
**Action**: Add a `Setup Helm` step after `Verify cluster access`:

```yaml
- name: Setup Helm
  uses: azure/setup-helm@v4
  with:
    version: '3.14.0'
```

**Done when**: `deploy.yml` contains `azure/setup-helm@v4` in the `deploy` job.

---

### [X] TASK-016 — Add `helm lint` + `helm template` gate step to `deploy` job

**File**: `.github/workflows/deploy.yml`  
**Action**: Add a single `Helm Validate` step immediately after `Setup Helm`, before any cluster-affecting steps. The step runs **both** commands and fails the job if either exits non-zero (FR-H-011):

```yaml
- name: Helm Validate
  run: |
    helm lint --strict helm/devops-chatbot/
    helm template helm/devops-chatbot/ --set image.tag=lint-check > /dev/null
```

**Done when**: Both commands are present in the step; step appears before `Configure Civo + kubectl`.

---

### [X] TASK-017 — Remove `sed -i` image tag injection step

**File**: `.github/workflows/deploy.yml`  
**Action**: Delete the entire `Update image tag in manifests` step. Image tag is now passed via `--set image.tag=` in the Helm upgrade step (TASK-019).

**Done when**: `grep -r "sed.*image" .github/workflows/` returns empty.

---

### [X] TASK-018 — Remove `devops-chatbot-secrets` kubectl secret creation

**File**: `.github/workflows/deploy.yml`  
**Action**: In the `Create secrets` step, delete the `kubectl create secret generic devops-chatbot-secrets` block. Secret is now managed by `templates/secret.yaml` rendered via `--set llm.*` (TASK-019).

Keep the `ghcr-pull-secret` creation — it remains a pre-step (AD-003).

**Done when**: `Create secrets` step contains only the `ghcr-pull-secret` block.

---

### [X] TASK-019 — Replace `kubectl apply -f k8s/` with `helm upgrade --install`

**File**: `.github/workflows/deploy.yml`  
**Action**: Replace the `Deploy application` step (which applies 7 separate `kubectl apply -f k8s/*.yaml` calls) with:

```yaml
- name: Deploy cert-manager ClusterIssuers
  run: |
    kubectl apply -f k8s/cert-issuer.yaml || echo "cert-manager not installed - HTTPS will not be available"

- name: Apply Kyverno policies
  run: kubectl apply -f k8s/kyverno-policies.yaml || true

- name: Deploy application (Helm)
  run: |
    helm upgrade --install devops-chatbot helm/devops-chatbot/ \
      --namespace ${{ env.NAMESPACE }} \
      --create-namespace \
      --set image.repository=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }} \
      --set image.tag=${{ needs.build.outputs.image_tag }} \
      --set podLabels.gitSha=${{ needs.build.outputs.image_tag }} \
      --set llm.apiKey=${{ secrets.OPENROUTER_API_KEY }} \
      --set llm.provider=openrouter \
      --set llm.model=mistralai/devstral-2512 \
      --set llm.defaultRegion=us-east-1 \
      --atomic \
      --wait \
      --timeout=300s
```

The existing `Wait for rollout` step can be removed — `--atomic --wait` handles this.

> **Note**: `kubectl apply -f k8s/namespace.yaml` step may be removed since `--create-namespace` covers it. Verify namespace does not carry required labels first.

**Done when**: `deploy` job contains `helm upgrade --install devops-chatbot` with `--atomic --wait --timeout=300s` and `--set podLabels.gitSha=`.

---

### [X] TASK-019b — Add `helm history` audit step to `deploy` job

**File**: `.github/workflows/deploy.yml`  
**Action**: Add a step at the end of the `deploy` job that emits the release history regardless of success or failure (FR-H-020):

```yaml
- name: Helm release history
  if: always()
  run: helm history devops-chatbot -n ${{ env.NAMESPACE }} || true
```

`|| true` ensures the step itself never fails (history may be absent on first-install failure).

**Done when**: `deploy` job contains a `helm history` step with `if: always()`.

---

### [X] TASK-020 — Update `deploy.yml` trigger paths to include `helm/**`

**File**: `.github/workflows/deploy.yml`  
**Action**: Update `on.push.paths` to add `helm/**`:

```yaml
paths:
  - 'backend/**'
  - 'frontend/**'
  - 'helm/**'
  - 'k8s/**'
  - 'Dockerfile'
  - '.github/workflows/deploy.yml'
```

> Keep `k8s/**` until TASK-027 cleanup — `cert-issuer.yaml` and `kyverno-policies.yaml` are retained.

**Done when**: `deploy.yml` `on.push.paths` includes `helm/**`.

---

### [X] TASK-021 — Add `concurrency.cancel-in-progress: false` to `deploy` job

**File**: `.github/workflows/deploy.yml`  
**Action**: Add `concurrency` block to the `deploy` job:

```yaml
deploy:
  name: Deploy to bookish-octo
  concurrency:
    group: deploy-production
    cancel-in-progress: false
  runs-on: ubuntu-latest
```

**Done when**: `deploy` job has `concurrency.cancel-in-progress: false`.

---

## Group 4: `deploy-k8sgpt.yml` GitHub Actions Updates

> **Prerequisite**: None — independent of Group 3.

### [X] TASK-022 — Add `azure/setup-helm@v4` to `deploy-k8sgpt.yml`

**File**: `.github/workflows/deploy-k8sgpt.yml`  
**Action**: Add `Setup Helm` step before `Add Helm repos`:

```yaml
- name: Setup Helm
  uses: azure/setup-helm@v4
  with:
    version: '3.14.0'
```

**Done when**: `deploy-k8sgpt.yml` contains `azure/setup-helm@v4`.

---

### [X] TASK-023 — Bump k8sgpt-operator chart version to `0.2.27`

**File**: `.github/workflows/deploy-k8sgpt.yml`  
**Action**: In the `Deploy K8sGPT operator` step, change:

```yaml
# From:
--version 0.2.26

# To:
--version 0.2.27
```

**Done when**: `grep "version 0.2.26" .github/workflows/deploy-k8sgpt.yml` returns empty.

---

### [X] TASK-024 — Verify no `kubectl apply -f k8sgpt/ai-secret.yaml` reference

**File**: `.github/workflows/deploy-k8sgpt.yml`  
**Action**: Confirm the `Create k8sgpt AI secret` step uses inline `kubectl create secret --dry-run | kubectl apply` (already the case). Confirm no reference to `k8sgpt/ai-secret.yaml` file path exists. If `k8sgpt/ai-secret.yaml` exists as a committed file, flag for deletion in TASK-028.

**Done when**: `grep "ai-secret.yaml" .github/workflows/deploy-k8sgpt.yml` returns empty.

---

## Group 5: k8sgpt Config File Updates

> **Prerequisite**: None — independent file changes.

### [X] TASK-025 — Add `dynamicRBAC: true` to `k8sgpt/helm-values.yaml`

**File**: `k8sgpt/helm-values.yaml`  
**Action**: Add `dynamicRBAC: true` and update chart version comment:

```yaml
# Chart version: k8sgpt-operator/k8sgpt-operator v0.2.27
dynamicRBAC: true
```

**Done when**: `grep "dynamicRBAC: true" k8sgpt/helm-values.yaml` exits 0.

---

### [X] TASK-026 — Verify `k8sgpt/k8sgpt-openrouter-cr.yaml` complete

**File**: `k8sgpt/k8sgpt-openrouter-cr.yaml`  
**Action**: Verify the following are present (updated in previous session):

1. `ConfigMap` in `spec.filters` list (20 total filters, OLM excluded)
2. `spec.integrations.trivy.enabled: true` and `spec.integrations.trivy.skipInstall: true`
3. `spec.version: v0.4.31`

If any are missing, add them per `data-model.md` CR schema.

**Done when**: `grep -c "ConfigMap\|trivy" k8sgpt/k8sgpt-openrouter-cr.yaml` returns ≥ 2.

---

## Group 6: Cleanup (after validated Helm deploy)

> **Prerequisite**: Groups 3–5 complete AND successful end-to-end deploy confirmed in GitHub Actions.

### TASK-027 — Delete deprecated `k8s/` raw manifests

**Files to delete**:
- `k8s/deployment.yaml`
- `k8s/service.yaml`
- `k8s/ingress.yaml`
- `k8s/pvc.yaml`
- `k8s/serviceaccount.yaml`
- `k8s/pdb.yaml`
- `k8s/resourcequota.yaml`
- `k8s/secrets.yaml`

**Retain**:
- `k8s/cert-issuer.yaml` — out-of-chart, still `kubectl apply`'d
- `k8s/kyverno-policies.yaml` — out-of-chart, still `kubectl apply`'d
- `k8s/namespace.yaml` — retain until `--create-namespace` confirmed sufficient

**Done when**: Only retained files remain in `k8s/`.

---

### TASK-028 — Delete `k8sgpt/ai-secret.yaml` if it exists

**File**: `k8sgpt/ai-secret.yaml` (check with `ls k8sgpt/`)  
**Action**: If the file exists, delete it. Secret is inlined in CI.

**Done when**: `ls k8sgpt/ai-secret.yaml` returns "No such file".

---

## Group 7: Validation

> **Prerequisite**: Groups 1–5 complete.

### [X] TASK-029 — Confirm `helm template` renders exactly 8 resource kinds

**Action**:
```bash
helm template devops-chatbot helm/devops-chatbot/ \
  --set image.tag=test \
  --set llm.apiKey=placeholder \
  --set ingress.enabled=true | grep "^kind:" | sort | uniq
```

Expected (8 kinds):
```
kind: Deployment
kind: Ingress
kind: PersistentVolumeClaim
kind: PodDisruptionBudget
kind: ResourceQuota
kind: Secret
kind: Service
kind: ServiceAccount
```

**Done when**: Exactly 8 distinct `kind:` values appear.

---

### [X] TASK-030 — Verify no secrets committed to chart

**Action**:
```bash
grep -r "sk-\|ASIA\|AKIA\|openrouter\|openai-api-key" helm/devops-chatbot/
```

**Done when**: Zero matches.

---

### [X] TASK-031 — Verify `sed -i` fully removed

**Action**:
```bash
grep -r "sed.*image" .github/workflows/
```

**Done when**: Zero matches.

---

### TASK-032 — Push branch and confirm GitHub Actions green

**Action**: Push `001-devops-chatbot-v2` branch. Verify:

- `Build & Deploy` workflow: build → test → deploy (helm upgrade exits 0) → smoke-test all green
- `Deploy K8sGPT Operator & Observability` workflow: deploy job green (operator at 0.2.27)
- `GET /api/health` returns HTTP 200 in smoke-test job
- `kubectl get pods -n devops-chatbot` shows Running pods

**Done when**: Both workflow runs show green on the branch PR.

---

## Dependency Order

```
TASK-001 → TASK-002 → TASK-003 → TASK-004
                                    ↓
              TASK-005 through TASK-013 (parallel, Group 2)
                                    ↓
                               TASK-014 (lint gate)
                                    ↓
TASK-015 → TASK-016 → TASK-017 → TASK-018 → TASK-019 → TASK-020 → TASK-021

TASK-022 → TASK-023 → TASK-024  (independent — Group 4)

TASK-025 → TASK-026              (independent — Group 5)

TASK-027 → TASK-028              (Group 6, after deploy validated)

TASK-029 → TASK-030 → TASK-031 → TASK-032  (Group 7, after Groups 1–5)
```

---

## Out-of-Scope (Explicit Exclusions)

| Item | Reason |
|------|---------|
| `backend/` code changes | Application code — excluded per scope constraint |
| `frontend/` code changes | Application code — excluded per scope constraint |
| `libs/` changes | Library code — excluded per scope constraint |
| Grafana dashboard JSON | Dashboard — excluded per scope constraint |
| `k8sgpt/Alloy/alloy-values.yaml` content | Alloy config content — excluded per scope constraint |
| ArgoCD `argocd/` manifests | Not the CI mechanism for this feature |
| Slack notification sink | Deferred to future release |
| MCP server integration | Deferred to future release |
| OLM analyzers | k3s has no OLM (AD-007) |
