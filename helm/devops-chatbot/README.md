# devops-chatbot Helm Chart

This chart deploys the `devops-chatbot` application resources.

## Out-of-Chart Resources

The following resources are intentionally managed outside this chart and are applied via `kubectl apply` in CI:

- `k8s/cert-issuer.yaml`: `ClusterIssuer` resources (cluster-scoped)
- `k8s/kyverno-policies.yaml`: `ClusterPolicy` resources (cluster-scoped)
- `k8sgpt/Alloy/alloy-rbac.yaml`: cluster-scoped RBAC for Alloy scraper
- `k8sgpt/Alloy/alloy-cleanup-cronjob.yaml`: supplementary cleanup CronJob
- `k8sgpt/Alloy/k8sgpt-result-scraper.yaml`: Alloy scraper ConfigMap/workload resources

## Pre-Step Secret

`ghcr-pull-secret` is created as a CI pre-step and is not managed by this Helm release.
