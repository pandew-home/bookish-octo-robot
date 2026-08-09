# K8sGPT setup

K8sGPT Operator (+ instance) runs analyzers on a schedule and writes **Result** CRs. The chatbot weather widget and agent consume those CRDs (always verify against live API state).

Preferred path: **Argo CD + Helm** — see [deployment.md](deployment.md).

## GitOps apps

| Application | Purpose |
|-------------|---------|
| `00-k8sgpt-operator` | Operator |
| `10-k8sgpt-instance` | Instance CR + RBAC (`helm/k8sgpt-instance`) |
| `30-alloy` / `35-alloy-extras` | Telemetry + cleanup helpers |
| `40-grafana-dashboards` | Dashboard ConfigMaps |

AI backend secret **before** the instance is healthy:

```bash
kubectl create namespace k8sgpt-operator-system --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system
# Name/keys must match helm/k8sgpt-instance values
```

## Manual Helm

```bash
helm repo add k8sgpt https://charts.k8sgpt.ai/ && helm repo update
kubectl create namespace k8sgpt-operator-system
# install operator per upstream, then:
helm upgrade --install k8sgpt-instance ./helm/k8sgpt-instance \
  -n k8sgpt-operator-system
```

Fixtures and Alloy notes: `k8sgpt/` (e.g. `k8sgpt/Alloy/`).

## Verify

```bash
kubectl get pods -n k8sgpt-operator-system
kubectl get results.core.k8sgpt.ai -A
kubectl get k8sgpt -A
```

Empty weather → no Results, operator down, or missing get/list on Result CRDs.

CI helpers: `.github/workflows/deploy-k8sgpt.yml` — steady state remains Argo CD.

## Related

- [Deployment](deployment.md) · [Architecture](architecture.md)
