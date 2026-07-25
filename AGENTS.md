# Agent Requirements — bookish-octo-robot

Instructions for AI coding agents working in this repository.

**Baseline tag:** `faiss-202607` (`main` @ FAISS RAG + ArgoCD/Helm GitOps era).  
**Remote:** `https://github.com/pandew-home/bookish-octo-robot` — develop only from `main` (feature branches + PRs).

---

## What this product is

**DevOps Chatbot v2.0** — Kubernetes-native troubleshooting assistant:

| Layer | Tech |
|-------|------|
| UI | React + TypeScript (`frontend/`) |
| API | FastAPI (`backend/`) |
| RAG | FAISS index on PVC + shared libs under `libs/` |
| Diagnostics | K8sGPT Operator Result CRDs |
| Auth | Kion temporary AWS creds and/or kubeconfig; session via `X-Session-Id` **or** HttpOnly `session_id` cookie |
| Package | Multi-stage Docker image → `ghcr.io/pandew-home/bookish-octo-robot:<git-sha>` |
| GitOps | **Argo CD app-of-apps** (`argocd/`) + Helm charts (`helm/`) — **not Flux** |

### Runtime posture (important)

- Default chat mode is **observe / diagnose** using live Kubernetes API tools + K8sGPT + KB.
- Mutating Kubernetes API calls require **explicit human approval** in chat (`agentic_engine` / system prompt). Do not remove approval gates without a security review.
- Optional **single-cluster mode**: set `IN_CLUSTER_EKS_CLUSTER_NAME` or `EKS_CLUSTER_NAME` so credential submit verifies access to that cluster and cluster listing is filtered/defaulted.
- Prefer **GitOps/IaC remediation advice** over ad-hoc cluster mutation unless the user clearly wants an approved execute path.

---

## Required tools / conventions

### Spec-kit (recommended for large features)

**Constitution (binding):** [`.specify/memory/constitution.md`](.specify/memory/constitution.md) **v2.0.0**  
Observe-default + approval-gated mutation, live API first, Argo CD/Helm GitOps, SHA images, secrets/session rules.

Spec-driven flow under `.specify/` and `.claude/skills/speckit-*`:

1. `/speckit.constitution` — principles (this file + constitution.md)  
2. `/speckit.specify` — requirements  
3. `/speckit.plan` — technical plan (includes Constitution Check gates)  
4. `/speckit.tasks` — task breakdown  
5. `/speckit.implement` — implementation  

Small bugfixes and doc-only changes do not need a full spec cycle.

### Code standards

- **Python:** PEP 8, type hints, `black`/`ruff` where configured; tests via `pytest` in `backend/`.
- **YAML/Helm:** 2-space indent; set requests/limits; `runAsNonRoot` + explicit non-root UID/GID; no secrets in git.
- **Secrets:** Out-of-band only (`devops-chatbot-secrets`, GHCR pull secret, K8sGPT AI secret). Chart `llm.createSecret` stays `false` for GitOps.
- **Images:** Deploy by **git SHA tag**, not `latest` (see Helm values comments and Image Updater allow-tags).

---

## Development workflow

1. **Branch from `main`** — never commit WIP directly to `main` without PR when branch protection is on.
2. **Local stack** (see [docs/development.md](docs/development.md)):
   ```bash
   cd backend && python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   pip install -e ../libs/devops-k8s -e ../libs/devops-kb -e ../libs/devops-rag
   uvicorn app:app --reload --port 8000

   cd frontend && npm install && npm start
   ```
3. **Tests before PR:**
   ```bash
   cd backend && pytest
   cd frontend && npm test -- --no-watch
   # Optional e2e (Playwright): cd frontend && npx playwright test
   ```
4. **CI:** `.github/workflows/deploy.yml` builds/tests; image published to GHCR. Optional `direct_deploy` is emergency-only — steady state is Argo CD reconcile.
5. **Cluster verify:** After image lands, Argo CD Image Updater / sync should move `image.tag`; confirm pods, ingress, `/api/health`.

---

## Repository map (source of truth)

```
argocd/                 # App-of-apps GitOps (bootstrap + Application CRs)
  apps/                 # Wave-ordered apps: operator, instance, monitoring, alloy, chatbot
  bootstrap/root-app.yaml
helm/
  devops-chatbot/       # Primary app chart (deployment, ingress, PVC, PDB, …)
  k8sgpt-instance/      # K8sGPT instance + RBAC
  alloy-extras/         # Cleanup CronJob, scraper helpers
  grafana-dashboards/   # Dashboard ConfigMaps
backend/                # FastAPI app, agentic engine, skills, RAG integration
  api/                  # credentials, clusters, chat, weather, solutions
  skills/               # k8s-check, networking/rbac/workload triage, …
  prompts/system.md     # Agent persona / guardrails (edit carefully)
frontend/               # React UI
libs/                   # devops-k8s, devops-kb, devops-rag (editable installs for local dev)
k8s/                    # Legacy/reference raw manifests — prefer helm/ + argocd/
k8sgpt/                 # Operator notes, Alloy docs, fixtures
.github/workflows/      # deploy, k8sgpt deploy helpers, workflow-lint
docs/                   # Human docs (keep in sync with this file)
```

**Do not reintroduce Flux.** There is no `flux/` tree; [docs/flux-gitops.md](docs/flux-gitops.md) is a redirect stub only.

---

## GitOps & deployment (agent checklist)

1. **Bootstrap (once per cluster):**  
   `argocd/projects/bookish-octo-robot.yaml` → `argocd/bootstrap/root-app.yaml`  
   Root app watches `argocd/apps/*`.
2. **App config:** Change Helm values under `helm/<chart>/` or inline values in `argocd/apps/*.yaml`. Keep ingress host/path, `app.apiBaseUrl`, `app.publicUrl`, and CORS (`allowedOrigins`) aligned.
3. **Chatbot image:** `ghcr.io/pandew-home/bookish-octo-robot` — 40-char SHA tags preferred; Image Updater writes back to `argocd/apps/50-devops-chatbot.yaml`.
4. **Secrets (manual / ExternalSecrets):**  
   - `devops-chatbot` / `devops-chatbot-secrets` — LLM key, provider, model  
   - `ghcr-pull-secret`  
   - K8sGPT AI backend secret in operator namespace  
5. **Ingress (current chart defaults):** Traefik; host in `helm/devops-chatbot/values.yaml`; app path under `/chatbot` with extraPaths for `/api`, `/static`, etc. TLS optional via cert-manager annotations.

Details: [docs/deployment.md](docs/deployment.md), [docs/argocd-gitops.md](docs/argocd-gitops.md).

---

## Backend / product rules for agents

- Session identity: `get_session_id` accepts **header or cookie**; credential POST endpoints set HttpOnly `session_id`; DELETE clears it. Keep JSON `session_id` for frontend compatibility.
- Chat path uses `AgentEngine` + tools/skills — preserve tool approval semantics and `backend/prompts/system.md` placeholders unless you update `agentic_engine.py` in the same change.
- Skills live under `backend/skills/<name>/SKILL.md` and are discovered by `skills.py`.
- FAISS / KB data on PVC (`DATA_ROOT` / chart PVC); do not commit index binaries.
- Shared libraries remain packages under `libs/` (not fully inlined into backend).

---

## Security & safety

- Never commit API keys, kubeconfigs, or live credentials.
- Do not weaken Pod Security (non-root, drop caps, seccomp) in Helm templates without calling it out.
- Destructive kubectl / cluster changes: confirm with the human; prefer dry-run/diff.
- Production-facing clusters: treat chatbot RBAC as least privilege; mutation only after dual approval in product UX.

See [docs/security.md](docs/security.md).

---

## Docs to update when you change behavior

| Change type | Update |
|-------------|--------|
| Auth / session / single-cluster env | `AGENTS.md`, `docs/architecture.md`, `docs/usage.md`, `docs/security.md` |
| Ingress host/path / GitOps | `docs/deployment.md`, `docs/argocd-gitops.md`, `README.md` |
| Local dev / tests / tree layout | `docs/development.md`, `README.md` |
| K8sGPT / Alloy / Grafana | `docs/k8sgpt-setup.md`, `k8sgpt/` docs |
| Agent skills / system prompt | `AGENTS.md`, `backend/prompts/system.md` |

---

## Quick links

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)
- [Argo CD GitOps](docs/argocd-gitops.md)
- [K8sGPT setup](docs/k8sgpt-setup.md)
- [Security](docs/security.md)
- [Usage](docs/usage.md)
- [README](README.md)
