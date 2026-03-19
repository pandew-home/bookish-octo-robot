# K8sGPT + Grafana Alloy Integration

Grafana Alloy tails k8sgpt-operator pod logs and ships them to Loki. A separate CronJob handles Result CRD cleanup to prevent unbounded growth.

## Architecture

```
K8sGPT Operator (k8sgpt-operator-system)
    │ pod logs
    ▼
Grafana Alloy (DaemonSet, monitoring namespace)
    │ loki.source.kubernetes → loki.process → loki.write
    ▼
Loki → Grafana (K8sGPT Results dashboard)

CronJob: k8sgpt-result-cleanup (hourly, 24h retention)
    └─ kubectl delete results older than 24h
```

## Files

| File | Purpose |
| ---- | ------- |
| `alloy-config.yaml` | Alloy River config (source of truth) |
| `alloy-configmap.yaml` | Applied ConfigMap (name: `alloy`, namespace: `monitoring`) |
| `alloy-patch.yaml` | Env vars patch for Alloy DaemonSet |
| `alloy-rbac.yaml` | ServiceAccount + ClusterRole for CRD read/delete |
| `alloy-cleanup-cronjob.yaml` | Hourly CronJob to delete Results >24h old |
| `grafana-k8sgpt-dashboard.yaml` | 4-panel Grafana dashboard (provisioned via label) |
| `grafana-nodeport-patch.yaml` | Exposes Grafana on NodePort 30300 |
| `loki-datasource-fix.yaml` | Fixes `isDefault` conflict in loki-loki-stack ConfigMap |
| `argocd-application.yaml` | K8sGPT Operator Helm deployment via ArgoCD |

## Deploy Order (fresh environment)

Assumes kube-prometheus-stack, Loki, and Grafana Alloy are already installed in `monitoring` namespace.

```bash
# 1. RBAC for CRD cleanup CronJob
kubectl apply -f k8sgpt/Alloy/alloy-rbac.yaml

# 2. Fix Loki datasource isDefault conflict (blocks Grafana datasource provisioning)
kubectl apply -f k8sgpt/Alloy/loki-datasource-fix.yaml

# 3. Expose Grafana as NodePort 30300
kubectl apply -f k8sgpt/Alloy/grafana-nodeport-patch.yaml

# 4. Update Alloy config and patch env vars
kubectl apply -f k8sgpt/Alloy/alloy-configmap.yaml
kubectl patch daemonset alloy -n monitoring --patch-file k8sgpt/Alloy/alloy-patch.yaml
kubectl rollout restart daemonset/alloy -n monitoring

# 5. Cleanup CronJob and Grafana dashboard
kubectl apply -f k8sgpt/Alloy/alloy-cleanup-cronjob.yaml
kubectl apply -f k8sgpt/Alloy/grafana-k8sgpt-dashboard.yaml

# 6. K8sGPT instance
kubectl apply -f k8sgpt/k8sgpt-openrouter-cr.yaml
```

## Grafana

Dashboard URL: `http://localhost:30300/d/k8sgpt-results`

Panels:

- **K8sGPT Operator Logs** — live stream tagged `source=k8sgpt`
- **Analysis Activity** — requests/min time series
- **HPA & Scaling Issues** — logs filtered for HPA/scaling/replica keywords
- **All K8sGPT Findings** — full `k8sgpt-operator-system` namespace logs (last 1h)

Useful LogQL queries:
```logql
# All k8sgpt operator logs
{source="k8sgpt"}

# Filter for scaling-related entries
{source="k8sgpt"} |= "HorizontalPodAutoscaler"

# Filter for errors
{source="k8sgpt"} |= "error"
```

## Cleanup CronJob

The `k8sgpt-result-cleanup` CronJob runs hourly and deletes Result CRDs older than 24 hours.

```bash
# Check recent cleanup jobs
kubectl get jobs -n monitoring | grep k8sgpt-result-cleanup

# Check cleanup logs
kubectl logs -n monitoring -l job-name=<job-name>

# Adjust retention (edit CronJob env var)
kubectl set env cronjob/k8sgpt-result-cleanup -n monitoring RETENTION_HOURS=48
```

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
