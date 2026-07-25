# Flux GitOps (retired)

Flux-based deployment described in earlier revisions of this repository has been **removed**.

## Current path

Use **Argo CD app-of-apps + Helm**:

→ **[Argo CD GitOps](argocd-gitops.md)**

## What changed

| Before (Flux) | Now (Argo CD) |
|---------------|----------------|
| `flux/` tree, HelmRelease | `argocd/` Applications + `helm/` charts |
| Actions primarily direct-deploy | Actions build/push image; cluster pulls via GitOps |
| Flux bootstrap | `argocd/bootstrap/root-app.yaml` |

Do not reintroduce Flux resources without an explicit platform decision and doc update.
