# K8sGPT + Grafana Alloy Integration

This guide explains how to integrate K8sGPT Result CRDs with Grafana Alloy for centralized observability and automated cleanup.

## Why Use Alloy for K8sGPT?

**Benefits:**
- ✅ **Centralized Observability**: K8sGPT results in Loki alongside other logs
- ✅ **Metrics & Alerting**: Track result counts, cleanup status in Prometheus/Grafana
- ✅ **Automated Cleanup**: No separate CronJob needed - Alloy handles it
- ✅ **Unified Stack**: One agent for logs, metrics, traces, and K8sGPT results
- ✅ **Better Querying**: Use LogQL to search/filter K8sGPT results in Grafana

**vs. Standalone CronJob:**
- Alloy is likely already deployed in your cluster
- Integrated metrics and alerting
- Consistent RBAC and security model
- Easier to manage (one less workload)

## Architecture

```
┌─────────────────┐
│  K8sGPT Operator│
│  (creates CRDs) │
└────────┬────────┘
         │
         │ Result CRDs
         ▼
┌─────────────────┐
│  Grafana Alloy  │
│  ┌───────────┐  │
│  │ Scraper   │──┼──> Loki (structured logs)
│  ├───────────┤  │
│  │ Metrics   │──┼──> Prometheus/Mimir (metrics)
│  ├───────────┤  │
│  │ Cleanup   │──┼──> Delete old CRDs (24h retention)
│  └───────────┘  │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│     Grafana     │
│  (dashboards &  │
│    alerting)    │
└─────────────────┘
```

## Prerequisites

1. **Grafana Alloy** deployed in your cluster (typically in `monitoring` namespace)
2. **Loki** endpoint for log storage
3. **Prometheus/Mimir** endpoint for metrics
4. **kubectl** and **jq** available in Alloy pod

## Installation

### Step 1: Deploy RBAC for Alloy

```bash
# Apply RBAC permissions for Alloy to read/delete Result CRDs
kubectl apply -f alloy-rbac.yaml

# Verify ServiceAccount and ClusterRole
kubectl get sa alloy-k8sgpt -n monitoring
kubectl get clusterrole alloy-k8sgpt-reader-cleaner
```

### Step 2: Deploy Cleanup Script ConfigMap

```bash
# Create ConfigMap with cleanup script
kubectl apply -f alloy-configmap.yaml

# Verify ConfigMap
kubectl get configmap alloy-k8sgpt-scripts -n monitoring
```

### Step 3: Update Alloy Configuration

**Option A: Add to existing Alloy ConfigMap**

```bash
# Edit your Alloy ConfigMap
kubectl edit configmap alloy-config -n monitoring

# Add the content from alloy-k8sgpt-integration.yaml
```

**Option B: Use separate ConfigMap (recommended)**

```bash
# Alloy supports loading multiple config files
# Mount alloy-k8sgpt-config ConfigMap as a separate file
# Update your Alloy Deployment/DaemonSet to include:

volumeMounts:
  - name: k8sgpt-config
    mountPath: /etc/alloy/k8sgpt-integration.alloy
    subPath: k8sgpt-integration.alloy
  - name: k8sgpt-scripts
    mountPath: /etc/alloy/scripts
    
volumes:
  - name: k8sgpt-config
    configMap:
      name: alloy-k8sgpt-config
  - name: k8sgpt-scripts
    configMap:
      name: alloy-k8sgpt-scripts
      defaultMode: 0755  # Make scripts executable
```

### Step 4: Configure Environment Variables

Update your Alloy Deployment with required environment variables:

```yaml
env:
  - name: CLUSTER_NAME
    value: "prod-eks-cluster"  # Your cluster name
  
  - name: LOKI_URL
    value: "http://loki-gateway.monitoring.svc:3100/loki/api/v1/push"
  
  - name: PROMETHEUS_URL
    value: "http://prometheus.monitoring.svc:9090/api/v1/write"
  
  # Optional: Authentication
  # - name: LOKI_USERNAME
  #   valueFrom:
  #     secretKeyRef:
  #       name: loki-credentials
  #       key: username
  # - name: LOKI_PASSWORD
  #   valueFrom:
  #     secretKeyRef:
  #       name: loki-credentials
  #       key: password
  
  # Cleanup configuration
  - name: RETENTION_HOURS
    value: "24"  # Delete results older than 24 hours
```

### Step 5: Restart Alloy

```bash
# Restart Alloy to pick up new configuration
kubectl rollout restart deployment/alloy -n monitoring
# or
kubectl rollout restart daemonset/alloy -n monitoring

# Check Alloy logs
kubectl logs -n monitoring -l app=alloy -f
```

## Verification

### Check Alloy is Scraping K8sGPT Results

```bash
# Check Alloy logs for K8sGPT activity
kubectl logs -n monitoring -l app=alloy | grep k8sgpt

# Expected output:
# level=info msg="K8sGPT cleanup: Total=15, Deleted=3, Remaining=12, Errors=0"
```

### Query K8sGPT Results in Loki

In Grafana, use LogQL queries:

```logql
# All K8sGPT results
{source="k8sgpt"}

# Results by namespace
{source="k8sgpt", namespace="production"}

# Results by error type
{source="k8sgpt"} | json | severity="error"

# Results for specific resource
{source="k8sgpt"} | json | parent_object=~"Pod/.*"

# Count results over time
sum(count_over_time({source="k8sgpt"}[5m]))
```

### Check Cleanup Metrics in Prometheus

Query Prometheus/Grafana for cleanup metrics:

```promql
# Total K8sGPT results in cluster
k8sgpt_results_total

# Results deleted by cleanup
k8sgpt_results_deleted_total

# Remaining results after cleanup
k8sgpt_results_remaining

# Cleanup errors
k8sgpt_cleanup_errors_total

# Last cleanup run time
k8sgpt_cleanup_last_run_timestamp_seconds
```

### Verify Cleanup is Working

```bash
# Create a test result (will be cleaned up after 24 hours)
kubectl apply -f - <<EOF
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: test-old-result
  namespace: default
  creationTimestamp: "2024-01-01T00:00:00Z"  # Old timestamp
spec:
  kind: Pod
  name: test-pod
  error:
    - text: "Test error"
      severity: "error"
  details: "This is a test result"
  parentObject: "Pod/test-pod"
EOF

# Wait for next cleanup cycle (or trigger manually)
# Check if it was deleted
kubectl get result test-old-result -n default
# Should return: Error from server (NotFound)
```

## Configuration Options

### Adjust Retention Period

Edit the `RETENTION_HOURS` environment variable in Alloy deployment:

```yaml
env:
  - name: RETENTION_HOURS
    value: "48"  # Keep results for 48 hours instead of 24
```

### Change Cleanup Frequency

Edit the `scrape_interval` in `alloy-k8sgpt-integration.yaml`:

```alloy
prometheus.scrape "k8sgpt_cleanup" {
  scrape_interval = "3h"  # Run cleanup every 3 hours instead of 6
  # ...
}
```

### Filter by Namespace

To only scrape/cleanup specific namespaces, modify the configuration:

```alloy
prometheus.exporter.kubernetes "k8sgpt_results" {
  resources {
    api_version = "core.k8sgpt.ai/v1alpha1"
    kind        = "Result"
    namespace   = "production"  # Only production namespace
  }
}
```

## Grafana Dashboards

### Sample Dashboard Queries

**Panel 1: K8sGPT Results Over Time**
```promql
sum(k8sgpt_results_total) by (cluster)
```

**Panel 2: Results by Namespace**
```promql
sum(k8sgpt_results_total) by (namespace)
```

**Panel 3: Cleanup Activity**
```promql
rate(k8sgpt_results_deleted_total[1h])
```

**Panel 4: Recent K8sGPT Issues (Loki)**
```logql
{source="k8sgpt"} | json | line_format "{{.namespace}}/{{.parent_object}}: {{.error_text}}"
```

### Import Pre-built Dashboard

A sample Grafana dashboard JSON is available in the repository:
```bash
# TODO: Create k8sgpt-dashboard.json
```

## Alerting

### Sample Prometheus Alerts

```yaml
groups:
  - name: k8sgpt
    interval: 5m
    rules:
      # Alert when too many K8sGPT results
      - alert: K8sGPTHighResultCount
        expr: k8sgpt_results_total > 50
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High number of K8sGPT results in {{ $labels.cluster }}"
          description: "{{ $labels.cluster }} has {{ $value }} K8sGPT results, indicating cluster issues"
      
      # Alert when cleanup is failing
      - alert: K8sGPTCleanupFailing
        expr: increase(k8sgpt_cleanup_errors_total[1h]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "K8sGPT cleanup errors in {{ $labels.cluster }}"
          description: "Cleanup has encountered {{ $value }} errors in the last hour"
      
      # Alert when cleanup hasn't run
      - alert: K8sGPTCleanupStale
        expr: (time() - k8sgpt_cleanup_last_run_timestamp_seconds) > 28800  # 8 hours
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "K8sGPT cleanup hasn't run recently in {{ $labels.cluster }}"
          description: "Last cleanup was {{ $value | humanizeDuration }} ago"
```

## Troubleshooting

### Alloy Not Scraping Results

1. Check RBAC permissions:
```bash
kubectl auth can-i get results.core.k8sgpt.ai --as=system:serviceaccount:monitoring:alloy-k8sgpt
kubectl auth can-i delete results.core.k8sgpt.ai --as=system:serviceaccount:monitoring:alloy-k8sgpt
```

2. Check Alloy logs:
```bash
kubectl logs -n monitoring -l app=alloy | grep -i error
```

3. Verify Result CRDs exist:
```bash
kubectl get results.core.k8sgpt.ai --all-namespaces
```

### Cleanup Not Working

1. Check script is mounted:
```bash
kubectl exec -n monitoring deployment/alloy -- ls -la /etc/alloy/scripts/
```

2. Check script has execute permissions:
```bash
kubectl exec -n monitoring deployment/alloy -- cat /etc/alloy/scripts/k8sgpt-cleanup.sh
```

3. Manually run cleanup:
```bash
kubectl exec -n monitoring deployment/alloy -- /etc/alloy/scripts/k8sgpt-cleanup.sh
```

4. Check for kubectl/jq in Alloy pod:
```bash
kubectl exec -n monitoring deployment/alloy -- which kubectl
kubectl exec -n monitoring deployment/alloy -- which jq
```

### No Metrics in Prometheus

1. Check Prometheus remote_write endpoint:
```bash
kubectl exec -n monitoring deployment/alloy -- curl -v $PROMETHEUS_URL
```

2. Check Alloy metrics endpoint:
```bash
kubectl port-forward -n monitoring deployment/alloy 12345:12345
curl http://localhost:12345/metrics | grep k8sgpt
```

### No Logs in Loki

1. Check Loki endpoint:
```bash
kubectl exec -n monitoring deployment/alloy -- curl -v $LOKI_URL
```

2. Query Loki directly:
```bash
curl -G -s "http://loki-gateway.monitoring.svc:3100/loki/api/v1/query" \
  --data-urlencode 'query={source="k8sgpt"}' | jq
```

## Comparison: Alloy vs. CronJob

| Feature | Alloy Integration | Standalone CronJob |
|---------|-------------------|-------------------|
| **Deployment** | Add to existing Alloy | New workload |
| **Observability** | Built-in metrics & logs | Manual setup |
| **Alerting** | Native Prometheus alerts | Requires custom setup |
| **Resource Usage** | Minimal (shared with Alloy) | Dedicated pod every 6h |
| **Maintenance** | Part of observability stack | Separate lifecycle |
| **Complexity** | Medium (Alloy config) | Low (simple CronJob) |
| **Flexibility** | High (custom pipelines) | Low (bash script) |

**Recommendation**: Use Alloy if you already have it deployed. Use CronJob if you want a simple, standalone solution.

## Uninstallation

```bash
# Remove Alloy configuration
kubectl delete configmap alloy-k8sgpt-config -n monitoring
kubectl delete configmap alloy-k8sgpt-scripts -n monitoring

# Remove RBAC
kubectl delete clusterrolebinding alloy-k8sgpt-reader-cleaner
kubectl delete clusterrole alloy-k8sgpt-reader-cleaner
kubectl delete serviceaccount alloy-k8sgpt -n monitoring

# Restart Alloy to remove K8sGPT integration
kubectl rollout restart deployment/alloy -n monitoring
```

## References

- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/latest/)
- [K8sGPT Documentation](https://docs.k8sgpt.ai/)
- [Prometheus Exporter Script](https://grafana.com/docs/alloy/latest/reference/components/prometheus.exporter.script/)
- [Loki Source Kubernetes](https://grafana.com/docs/alloy/latest/reference/components/loki.source.kubernetes/)
