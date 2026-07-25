# Argo CD GitOps

Steady-state delivery for this repository is **pull-based Argo CD** with Helm charts as the application source of truth.

> **Flux is retired.** The old `flux/` tree and Flux bootstrap path are gone.  
> Historical note only: [flux-gitops.md](flux-gitops.md).

## Why Argo CD

- Desired state lives in git (`argocd/` + `helm/`).
- Cluster reconcile does not depend on every GitHub Actions runner successfully reaching the cluster API.
- Image updates can be automated with **Argo CD Image Updater** (SHA tags from GHCR).

## Layout

```
argocd/
  projects/bookish-octo-robot.yaml   # AppProject
  bootstrap/root-app.yaml            # App-of-apps root
  apps/
    00-k8sgpt-operator.yaml
    10-k8sgpt-instance.yaml
    20-kube-prometheus-stack.yaml
    30-alloy.yaml
    35-alloy-extras.yaml
    40-grafana-dashboards.yaml
    50-devops-chatbot.yaml           # Chatbot Helm + Image Updater annotations
helm/
  devops-chatbot/
  k8sgpt-instance/
  alloy-extras/
  grafana-dashboards/
```

Root application (`bookish-octo-robot-root`) watches `argocd/apps` on branch `main` and owns child Applications with automated prune/selfHeal.

## One-time bootstrap

Prerequisites: Argo CD installed in the cluster; `kubectl` context set; repo readable by Argo CD.

```bash
kubectl apply -n argocd -f argocd/projects/bookish-octo-robot.yaml
kubectl apply -n argocd -f argocd/bootstrap/root-app.yaml
```

Then ensure runtime secrets exist (not created by the chart by default):

```bash
kubectl create namespace devops-chatbot --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=<api-key> \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<ghcr-read-token> \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -
```

Watch:

```bash
kubectl get applications -n argocd
kubectl get pods -n devops-chatbot
kubectl get pods -n k8sgpt-operator-system
```

## Image updates

`argocd/apps/50-devops-chatbot.yaml` is annotated for Image Updater:

- Image: `ghcr.io/pandew-home/bookish-octo-robot`
- Allowed tags: 40-char git SHA
- Write-back: git → helm values on that Application manifest

Requirements (cluster-side): Image Updater installed; git write credentials; GHCR pull secret as referenced by annotations.

CI (`.github/workflows/deploy.yml`) builds and pushes SHA (+ optional `latest`) tags. Prefer SHA for deploys.

## GitHub Actions vs GitOps

| Path | Role |
|------|------|
| `deploy.yml` build/test | Continuous integration; publish image to GHCR |
| Argo CD + Image Updater | Continuous delivery in cluster |
| `workflow_dispatch` `direct_deploy=true` | Emergency/debug path only — not the default |

## Making config changes

1. Edit chart values in `helm/devops-chatbot/values.yaml` (or other charts), **or** override values in the Application CR.
2. Keep **ingress host/path**, **app.apiBaseUrl / publicUrl**, and **allowedOrigins** consistent so the SPA does not call the wrong origin.
3. Open a PR to `main`; after merge, Argo CD self-heals.

## Related docs

- [Deployment](deployment.md)
- [K8sGPT setup](k8sgpt-setup.md)
- [Architecture](architecture.md)
