# K8sGPT + Grafana Alloy Integration

Grafana Alloy tails k8sgpt-operator pod logs and ships them to Loki. A separate CronJob handles Result CRD cleanup to prevent unbounded growth. Grafana is exposed via Traefik ingress at `/grafana` subpath for centralized multi-cluster observability.

## Architecture

```
K8sGPT Operator (k8sgpt-operator-system)
    │ pod logs
    ▼
Grafana Alloy (DaemonSet, monitoring namespace)
    │ loki.source.kubernetes → loki.process → loki.write
    ▼
Loki (loki namespace) → Grafana (monitoring namespace)
                            │ Traefik Ingress at /grafana
                            ▼
                    http://cluster.host/grafana

CronJob: k8sgpt-result-cleanup (hourly, 24h retention)
    └─ kubectl delete results older than 24h
```

## Files

| File | Purpose |
| ---- | ------- |
| `alloy-values.yaml` | Alloy Helm values with River config |
| `alloy-rbac.yaml` | ServiceAccount + ClusterRole for CRD read/delete |
| `alloy-cleanup-cronjob.yaml` | Hourly CronJob to delete Results >24h old |
| `kube-prometheus-stack-values-base.yaml` | Shared Grafana/Prometheus base config (datasources, dashboards) |
| `kube-prometheus-stack-values-civo-traefik.yaml` | Civo cluster overrides: Traefik ingress at `/grafana`, Grafana server config for subpath serving |
| `k8sgpt-result-scraper.yaml` | 5-minute CronJob to scrape Result CRDs and export to Loki |

**Superseded files** (do not use):
- `grafana-nodeport-patch.yaml` — replaced by Helm ingress (kube-prometheus-stack-values-civo-traefik.yaml)
- `loki-datasource-fix.yaml` — Loki datasource now in base values
- `grafana-k8sgpt-dashboard.yaml`  — dashboard built and pushed by workflows

## Deploy Order (fresh environment)

Assumes Loki is pre-deployed in `loki` namespace and Grafana Alloy Helm chart is accessible.

**Via GitHub Actions workflow** (recommended):
- `.github/workflows/deploy-k8sgpt.yml` orchestrates everything in the correct order
- Run via `git push main` (auto-triggers on k8sgpt/** changes)

**Manual deployment** (dev/testing):

```bash
# 1. Create namespaces
kubectl apply -f k8sgpt/namespace.yaml
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# 2. RBAC for CRD cleanup CronJob
kubectl apply -f k8sgpt/Alloy/alloy-rbac.yaml

# 3. Deploy K8sGPT Operator
helm repo add k8sgpt-operator https://charts.k8sgpt.ai/
helm repo update
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=$OPENROUTER_API_KEY \
  -n k8sgpt-operator-system
helm upgrade --install k8sgpt-operator k8sgpt-operator/k8sgpt-operator \
  -n k8sgpt-operator-system --version 0.2.27 \
  --values k8sgpt/helm-values.yaml --wait --timeout=120s
kubectl apply -f k8sgpt/rbac.yaml
kubectl apply -f k8sgpt/k8sgpt-openrouter-cr.yaml

# 4. Deploy monitoring stack (Grafana, Prometheus, Loki datasource)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  --values k8sgpt/Alloy/kube-prometheus-stack-values-base.yaml \
  --values k8sgpt/Alloy/kube-prometheus-stack-values-civo-traefik.yaml \
  --wait --timeout=120s

# 5. Deploy Alloy (log collection)
helm upgrade --install alloy grafana/alloy \
  -n monitoring \
  --values k8sgpt/Alloy/alloy-values.yaml \
  --wait --timeout=120s

# 6. Cleanup CronJob and Result scraper
kubectl apply -f k8sgpt/Alloy/alloy-cleanup-cronjob.yaml
kubectl apply -f k8sgpt/Alloy/k8sgpt-result-scraper.yaml
```

## Grafana

**Access:** `http://cluster-host/grafana` (Traefik subpath ingress)

**Dashboard:** K8sGPT Findings & Fixes (UID: `k8sgpt-findings-v2`)

**Panels:**
- **K8sGPT Operator Logs** — live stream tagged `source=k8sgpt`, with level filtering
- **Analysis Activity** — Result creation rate over time
- **Error Trends** — error-level logs highlighted by type
- **All K8sGPT Findings** — full `k8sgpt-operator-system` namespace logs (last 1h)

**Useful LogQL queries:**
```logql
# All k8sgpt operator logs
{source="k8sgpt"}

# Filter for scaling-related entries
{source="k8sgpt"} |= "HorizontalPodAutoscaler"

# Filter for errors
{source="k8sgpt", level="error"}

# Group errors by kind
{source="k8sgpt"} | json | count by kind
```

**Grafana Server Config (for subpath serving):**
- `root_url: http://cluster-host/grafana`
- `serve_from_sub_path: true`

These settings are in `kube-prometheus-stack-values-civo-traefik.yaml` and ensure Grafana generates correct redirect URLs and serves static assets from `/grafana/public/` instead of `/public/`.

## Cleanup CronJob

The `k8sgpt-result-cleanup` CronJob runs **hourly** and deletes Result CRDs older than 24 hours (configurable via `RETENTION_HOURS` env var).

```bash
# Check recent cleanup jobs
kubectl get jobs -n monitoring | grep k8sgpt-result-cleanup

# Check cleanup logs
kubectl logs -n monitoring -l job-name=<job-name>

# Adjust retention
kubectl set env cronjob/k8sgpt-result-cleanup -n monitoring RETENTION_HOURS=48

# Monitor cleanup job status
kubectl describe cronjob k8sgpt-result-cleanup -n monitoring
```

## Result Scraper

The `k8sgpt-result-scraper` CronJob runs every **5 minutes** and exports Result CRDs to Loki for long-term retention and searchability in Grafana Logs.

## Verification

```bash
# Confirm Alloy is tailing k8sgpt-operator pods
kubectl logs -n monitoring -l app.kubernetes.io/name=alloy --tail=10 | grep k8sgpt

# Confirm K8sGPT is analyzing
kubectl logs -n k8sgpt-operator-system -l app.kubernetes.io/name=k8sgpt --tail=10

# Check current Results
kubectl get results.core.k8sgpt.ai --all-namespaces

# Run test HPA result
kubectl apply -f k8sgpt/test-hpa-result-cr.yaml
```

## Troubleshooting

### Alloy config parse error

```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=alloy --tail=20 | grep -i error
```

### Loki datasource missing in Grafana after helm upgrade

Re-apply: `kubectl apply -f k8sgpt/Alloy/loki-datasource-fix.yaml`

### Grafana NodePort lost after helm upgrade

Re-apply: `kubectl apply -f k8sgpt/Alloy/grafana-nodeport-patch.yaml`

### RBAC for cleanup CronJob

```bash
kubectl auth can-i delete results.core.k8sgpt.ai \
  --as=system:serviceaccount:monitoring:alloy-k8sgpt --all-namespaces
```
