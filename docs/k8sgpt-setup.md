# K8sGPT Setup Guide

Install and operate K8sGPT so the DevOps Chatbot weather widget and chat agent can consume **Result CRDs**.

## Overview

K8sGPT Operator (+ instance) runs analyzers on a schedule and writes Result custom resources. The chatbot reads those CRDs for health summaries and as supporting diagnostic signal (always verify against live API state).

Preferred install path in this repo: **Argo CD Applications + Helm charts**, not ad-hoc one-off manifests alone.

## GitOps path (recommended)

After Argo CD root app is bootstrapped ([argocd-gitops.md](argocd-gitops.md)):

| Application | Purpose |
|-------------|---------|
| `00-k8sgpt-operator` | Operator install |
| `10-k8sgpt-instance` | Instance CR + RBAC (`helm/k8sgpt-instance`) |
| `30-alloy` / `35-alloy-extras` | Telemetry + cleanup CronJob helpers |
| `40-grafana-dashboards` | Dashboard ConfigMaps |

Create the AI backend secret **before** the instance becomes healthy:

```bash
kubectl create namespace k8sgpt-operator-system --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system
# Secret name/keys must match what the instance chart/values expect — verify helm/k8sgpt-instance
```

## Manual / Helm path

```bash
helm repo add k8sgpt https://charts.k8sgpt.ai/
helm repo update

kubectl create namespace k8sgpt-operator-system
# install operator per upstream docs, then:
helm upgrade --install k8sgpt-instance ./helm/k8sgpt-instance \
  -n k8sgpt-operator-system
```

Reference fixtures and Alloy notes also live under `k8sgpt/` (including `k8sgpt/Alloy/ALLOY_INTEGRATION.md` where present).

## Verify

```bash
kubectl get pods -n k8sgpt-operator-system
kubectl get results.core.k8sgpt.ai -A
kubectl get k8sgpt -A
```

Chatbot weather empty? Confirm Results exist and the chatbot’s credentials/SA can **get/list** those CRDs in the relevant namespaces.

## CI helpers

`.github/workflows/deploy-k8sgpt.yml` and `k8sgpt-deploy-shared.yml` support scripted/operator-oriented deploys. Steady state remains Argo CD when GitOps is enabled.

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Argo CD GitOps](argocd-gitops.md)
