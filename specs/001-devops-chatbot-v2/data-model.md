# Data Model: Helm Chart Values Schema

**Feature**: `001-devops-chatbot-v2` — Helm-Based CI/CD Migration  
**Produced by**: `/speckit.plan` Phase 1  
**Date**: 2026-04-03

---

## 1. Helm Chart: `helm/devops-chatbot/`

### `values.yaml` — Complete Schema

All fields below are committed defaults (non-secret). Fields requiring secrets are empty-string placeholders injected at deploy time via `--set`.

```yaml
# ──────────────────────────────────────────────────────────────────────────────
# Image
# ──────────────────────────────────────────────────────────────────────────────
image:
  repository: ghcr.io/<owner>/<repo>   # REPLACE with actual owner/repo at chart creation
  tag: latest                           # Overridden at deploy time: --set image.tag=$SHA
  pullPolicy: IfNotPresent

imagePullSecrets:
  - name: ghcr-pull-secret              # Created by CI before helm upgrade

# ──────────────────────────────────────────────────────────────────────────────
# Deployment
# ──────────────────────────────────────────────────────────────────────────────
replicaCount: 1

nameOverride: ""
fullnameOverride: ""

namespace: devops-chatbot

podLabels:
  gitSha: ""                            # Injected at deploy: --set podLabels.gitSha=$SHA

# Security context: FIXED in templates, NOT exposed in values (FR-H-006)
# runAsNonRoot: true
# readOnlyRootFilesystem: true
# seccompProfile.type: RuntimeDefault

resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"

# ──────────────────────────────────────────────────────────────────────────────
# Service Account
# ──────────────────────────────────────────────────────────────────────────────
serviceAccount:
  name: devops-chatbot

# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────
service:
  type: ClusterIP
  port: 80
  targetPort: 8000

# ──────────────────────────────────────────────────────────────────────────────
# Ingress
# ──────────────────────────────────────────────────────────────────────────────
ingress:
  enabled: true
  host: <chatbot-hostname>              # REPLACE with actual hostname at chart creation
  tls:
    enabled: true
    secretName: devops-chatbot-tls
  annotations: {}                       # cert-manager annotation fixed in template (ASM-005)

# ──────────────────────────────────────────────────────────────────────────────
# PVC (Knowledge Base storage)
# ──────────────────────────────────────────────────────────────────────────────
pvc:
  enabled: true
  name: devops-chatbot-data
  storageSize: 5Gi
  storageClass: ""                      # Empty = cluster default (Civo: civo-volume)
  accessMode: ReadWriteOnce
  # Lifecycle annotation applied in template: helm.sh/resource-policy: keep
  # This prevents the PVC from being deleted on helm uninstall (FR-H-022 / SC-H-008)

# ──────────────────────────────────────────────────────────────────────────────
# Pod Disruption Budget
# ──────────────────────────────────────────────────────────────────────────────
pdb:
  enabled: true
  minAvailable: 1

# ──────────────────────────────────────────────────────────────────────────────
# Resource Quota
# ──────────────────────────────────────────────────────────────────────────────
resourceQuota:
  enabled: true
  hardLimitsCpu: "2"
  hardLimitsMemory: "2Gi"
  hardRequestsCpu: "500m"
  hardRequestsMemory: "1Gi"

# ──────────────────────────────────────────────────────────────────────────────
# LLM / Application Secrets (DO NOT COMMIT VALUES — injected at deploy time)
# ──────────────────────────────────────────────────────────────────────────────
llm:
  apiKey: ""          # --set llm.apiKey=${{ secrets.LLM_API_KEY }}
  provider: ""        # --set llm.provider=${{ secrets.LLM_PROVIDER }}
  model: ""           # --set llm.model=${{ secrets.LLM_MODEL }}
  defaultRegion: ""   # --set llm.defaultRegion=${{ secrets.DEFAULT_REGION }}
```

### Template Files (one-to-one mapping from `k8s/`)

| Template | Source | Notes |
|---|---|---|
| `templates/deployment.yaml` | `k8s/deployment.yaml` | Security contexts fixed; git-sha label from `podLabels.gitSha` |
| `templates/service.yaml` | `k8s/service.yaml` | |
| `templates/ingress.yaml` | `k8s/ingress.yaml` | TLS annotation fixed (cert-manager issuer) |
| `templates/pvc.yaml` | `k8s/pvc.yaml` | `helm.sh/resource-policy: keep` annotation in template |
| `templates/serviceaccount.yaml` | `k8s/serviceaccount.yaml` | |
| `templates/pdb.yaml` | `k8s/pdb.yaml` | |
| `templates/resourcequota.yaml` | `k8s/resourcequota.yaml` | |
| `templates/secret.yaml` | `k8s/secrets.yaml` (pattern) | Renders from `llm.*` values — replaces `kubectl create secret --dry-run` |

### `Chart.yaml` Fields

```yaml
apiVersion: v2
name: devops-chatbot
description: DevOps Chatbot v2 — Kubernetes-native troubleshooting assistant
type: application
version: 0.1.0              # Chart schema version (semver)
appVersion: latest           # Matches image.tag default
```

---

## 2. k8sgpt Operator: `k8sgpt/helm-values.yaml`

Updated schema to add `dynamicRBAC: true` and document the analyzer Trivy integration path:

```yaml
# k8sgpt-operator Helm chart values
# Chart: k8sgpt-operator/k8sgpt-operator  version: 0.2.27
# Updated: 2026-04-03

replicaCount: 1

resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"

serviceMonitor:
  enabled: true

metrics:
  enabled: true

dynamicRBAC: true   # Operator auto-provisions RBAC for analysis targets (default true in 0.2.27)

resultLogging:
  enabled: false
```

---

## 3. k8sgpt CR: `k8sgpt/k8sgpt-openrouter-cr.yaml`

Updated spec with `ConfigMap` added to filters and Trivy integration enabled:

```yaml
spec:
  version: v0.4.31          # Latest; no engine upgrade needed
  
  filters:
    - Pod
    - Log
    - Deployment
    - ReplicaSet
    - StatefulSet
    - Node
    - ConfigMap
    - PersistentVolumeClaim
    - Service
    - Ingress
    - CronJob
    - Job
    - HorizontalPodAutoscaler
    - PodDisruptionBudget
    - NetworkPolicy
    - MutatingWebhookConfiguration
    - ValidatingWebhookConfiguration
    - GatewayClass
    - Gateway
    - HTTPRoute
  
  integrations:
    trivy:
      enabled: true
      skipInstall: true       # Don't install Trivy Operator; use standalone scan if available
      namespace: k8sgpt-operator-system
  
  # ... rest of spec unchanged (ai, analysis, resources)
```

**Change log**:
- Added `ConfigMap` to `spec.filters` (20 total; OLM excluded — not installed on k3s)
- Added `spec.integrations.trivy` block with `skipInstall: true`
- `spec.version` stays at `v0.4.31` (already latest engine)

---

## 4. CI Workflow Variables Schema

### `deploy.yml` (chatbot CI) — `helm upgrade --install` invocation

```bash
helm upgrade --install devops-chatbot helm/devops-chatbot/ \
  --namespace devops-chatbot \
  --create-namespace \
  --wait \
  --timeout=300s \
  --atomic \
  --set image.tag=${{ github.sha }} \
  --set podLabels.gitSha=${{ github.sha }} \
  --set llm.apiKey=${{ secrets.LLM_API_KEY }} \
  --set llm.provider=${{ secrets.LLM_PROVIDER }} \
  --set llm.model=${{ secrets.LLM_MODEL }} \
  --set llm.defaultRegion=${{ secrets.DEFAULT_REGION }}
```

### `deploy-k8sgpt.yml` — operator Helm invocation

```bash
helm upgrade --install k8sgpt-operator k8sgpt-operator/k8sgpt-operator \
  --version 0.2.27 \
  --namespace k8sgpt-operator-system \
  --create-namespace \
  --values k8sgpt/helm-values.yaml \
  --wait \
  --timeout=120s
```

K8sGPT CR applied separately:
```bash
kubectl apply -f k8sgpt/k8sgpt-openrouter-cr.yaml
```

AI secret pattern (replaces `ai-secret.yaml`):
```bash
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=${{ secrets.OPENROUTER_API_KEY }} \
  --namespace k8sgpt-operator-system \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## 5. Entity Relationships

```
GitHub Actions Workflow
  deploy.yml
    ├── helm lint + template (gate)
    ├── kubectl apply cert-issuer.yaml  (cluster-scoped, out-of-chart)
    ├── kubectl apply kyverno-policies.yaml  (cluster-scoped, out-of-chart)
    ├── kubectl create secret ghcr-pull-secret (imagePullSecret)
    └── helm upgrade --install devops-chatbot helm/devops-chatbot/
          ├── templates/secret.yaml         → K8s Secret (llm config)
          ├── templates/serviceaccount.yaml → ServiceAccount
          ├── templates/pvc.yaml            → PVC (keep annotation)
          ├── templates/deployment.yaml     → Deployment
          ├── templates/service.yaml        → Service
          ├── templates/ingress.yaml        → Ingress (TLS via cert-manager)
          ├── templates/pdb.yaml            → PodDisruptionBudget
          └── templates/resourcequota.yaml  → ResourceQuota

  deploy-k8sgpt.yml
    ├── kubectl create secret k8sgpt-ai-secret (out-of-chart)
    ├── helm upgrade --install k8sgpt-operator (operators chart v0.2.27)
    ├── kubectl apply k8sgpt-openrouter-cr.yaml (K8sGPT CR)
    ├── helm upgrade --install alloy grafana/alloy --values alloy-values.yaml
    ├── kubectl apply alloy-rbac.yaml           (cluster-scoped)
    ├── kubectl apply alloy-cleanup-cronjob.yaml
    └── kubectl apply k8sgpt-result-scraper.yaml
```
