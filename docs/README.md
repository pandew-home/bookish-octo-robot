# DevOps Chatbot v2.0 Documentation

Guides for understanding, deploying, and using the chatbot.  
**GitOps:** Argo CD + Helm (Flux retired).

## Index

### Getting started
- **[Architecture](architecture.md)** — System design, agentic chat, Vestige memory, data flows  
- **[Development](development.md)** — Local setup, tests, repo layout  
- **[AGENTS.md](../AGENTS.md)** — Rules for AI coding agents  

### Deployment & platform
- **[Deployment](deployment.md)** — Images, Helm, env vars, troubleshooting  
- **[Argo CD GitOps](argocd-gitops.md)** — App-of-apps bootstrap and image updates  
- **[K8sGPT setup](k8sgpt-setup.md)** — Operator/instance and Results  
- **[Security](security.md)** — Auth, cookies, mutation gates, checklists  
- **[Flux (retired)](flux-gitops.md)** — Redirect only  

### Product
- **[Usage](usage.md)** — Login, weather, chat, KB for operators  

### Other
- **[Implementing TLS](implementing-tls.md)** — TLS notes (if still applicable)  
- **[Prompt flow redesign](prompt-flow-redesign.md)** — Historical design notes  
- Screenshots under `docs/screenshots/`  

## Quick links by role

| Role | Start here |
|------|------------|
| Developer | [development.md](development.md), [architecture.md](architecture.md) |
| Platform / GitOps | [argocd-gitops.md](argocd-gitops.md), [deployment.md](deployment.md) |
| Security | [security.md](security.md) |
| End user | [usage.md](usage.md) |

## External

- [K8sGPT docs](https://docs.k8sgpt.ai/)  
- [FastAPI](https://fastapi.tiangolo.com/)  
- [React](https://react.dev/)  
- [Argo CD](https://argo-cd.readthedocs.io/)  

## Need help?

1. [Deployment troubleshooting](deployment.md#troubleshooting)  
2. [Usage troubleshooting](usage.md#troubleshooting-end-user)  
3. Open a GitHub issue on `pandew-home/bookish-octo-robot`  
