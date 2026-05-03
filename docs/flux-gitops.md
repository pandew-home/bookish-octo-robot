# Flux GitOps Setup (Civo k3s)

This repository now supports pull-based deployment with Flux.

## Why this change

Direct deploys from GitHub-hosted runners to Civo can fail intermittently on cluster/API connectivity.
Flux runs in-cluster and continuously pulls desired state from git, so cluster sync no longer depends on runner-to-cluster reachability for every deployment.

## What changed in this repo

- Flux resources were added under `flux/`.
- App deployment source of truth is now `flux/apps/devops-chatbot/helmrelease.yaml`.
- GitHub Actions updates image tag fields in that file (`tag` + `gitSha`) after pushes.
- Direct deploy jobs in `.github/workflows/deploy.yml` are now opt-in via `workflow_dispatch` input `direct_deploy=true`.
- `.github/workflows/deploy-k8sgpt.yml` is manual-only.

## One-time cluster bootstrap

1) Install Flux CLI locally.

```bash
curl -s https://fluxcd.io/install.sh | sudo bash
flux --version
```

2) Point `kubectl` at your Civo cluster.

```bash
civo apikey save deploy-key "$CIVO_API_KEY"
civo apikey current deploy-key
civo kubernetes config bookish-octo-robot --save
kubectl get nodes
```

3) Bootstrap Flux against this repo path.

```bash
flux bootstrap github \
  --owner=pandew-home \
  --repository=bookish-octo-robot \
  --branch=main \
  --path=flux/clusters/civo/bookish-octo-robot \
  --personal
```

4) Create pull secret for GHCR images in `devops-chatbot` namespace.

```bash
kubectl create namespace devops-chatbot --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<ghcr-read-token> \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -
```

5) Ensure runtime app secret exists (chart no longer creates it by default).

```bash
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=<api-key> \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -
```

6) Watch first reconciliation.

```bash
flux get sources git -A
flux get kustomizations -A
flux get helmreleases -A
kubectl get pods -n devops-chatbot
```

## Ongoing flow

1) Push code to `main`.
2) Build workflow publishes image tag `${GITHUB_SHA}`.
3) `gitops-tag-update.yml` commits the same SHA into `flux/apps/devops-chatbot/helmrelease.yaml`.
4) Flux reconciles and upgrades release in-cluster.

## Emergency rollback

Use git revert on `flux/apps/devops-chatbot/helmrelease.yaml` to previous known-good `tag/gitSha`, then push.
Flux will reconcile back to that version.