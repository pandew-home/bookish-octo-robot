<!--
Sync Impact Report
- Version change: 2.0.0 → 3.0.0 (MAJOR)
- Rationale: Mutation authorization moves from in-band chat approval / prompt
  gates to Helm kubeApi wrapper policy + user credentials. Free-text
  recommendations are allowed. Secrets are identify-only by default. Long-term
  memory migrates from FAISS RAG to Vestige-class MCP (feature 002).
- Modified principles:
  - "Observe-Default, Approval-Gated Mutation" → "Observe-Default, Policy-Gated Mutation"
  - Purpose #3–4: FAISS → institutional memory (Vestige); agent access model
  - Env-scoped privileges: approval-gated → policy-gated
- Added: Secrets identify-vs-read under Secrets principle; Architectural Decision
  for code-enforced kube wrappers; Vestige supersedes FAISS ADR status
- Removed: Dual verbal chat approval as non-negotiable security control
- Templates: plan/spec constitution gates should be refreshed in feature work
- Deferred: None
-->

# DevOps Chatbot (bookish-octo-robot) Constitution

> Core principles and invariants that govern this platform's development and operation.

## Meta

- **Project**: DevOps Chatbot v2.0 (`bookish-octo-robot`) — Kubernetes troubleshooting assistant
- **Repository**: https://github.com/pandew-home/bookish-octo-robot
- **Baseline tag**: `faiss-202607` (pre–Vestige memory; supersession in progress on feature branches)
- **Ratified**: 2026-03-29
- **Last Amended**: 2026-07-25
- **Version**: 3.0.0

## Purpose

This platform helps DevOps engineers diagnose Kubernetes issues using:

1. **Live cluster state** via authenticated Kubernetes API access (Kion temporary AWS creds and/or kubeconfig).
2. **K8sGPT Result CRDs** as continuous analyzer signals (weather widget + chat context).
3. **Institutional agent memory** (Vestige-class MCP, cluster-local) for troubleshooting lessons—not in-process FAISS as the long-term design.
4. An **agentic chat backend** (tools + skills) that may **recommend** remediations freely; **execution** of cluster mutations is gated by **wrapper policy (Helm/env) + user credentials**, defaulting to mutate-off.

Delivery is **Argo CD app-of-apps + Helm** (`argocd/`, `helm/`). Images ship as **git SHA** tags to GHCR. Flux is not part of this platform.

## Core Principles

### 1. Observe-Default, Policy-Gated Mutation (NON-NEGOTIABLE)

**Invariant**: Mutating Kubernetes API **execution** MUST default to disabled at the application wrapper layer. Whether a mutation runs is determined by **(1) Helm/`kubeApi` (or env) policy** and **(2) the authenticated user’s cluster credentials**—not by system-prompt sermons or multi-step verbal “approve” rituals in chat.

**Enforcement**:

- Python kube API wrappers MUST enforce a single authorize chokepoint (method, mutate flag, denylists, secrets policy) before any apiserver call.
- Chart defaults MUST ship `allowMutate: false` and GET-oriented methods unless an environment overlay explicitly enables mutate.
- Free-text **recommendations** (including suggested kubectl/YAML for the user to run) MUST be allowed even when mutate is disabled.
- System prompt MUST NOT be the primary authorization mechanism; it MUST instruct agents to use **only** approved Python wrappers for cluster I/O.
- Secrets: by default wrappers MAY **identify** Secrets (list/metadata/key names) and MUST NOT return Secret **values** (`data` / `stringData`) to the agent; Secret mutate via wrappers MUST be denied by default.
- Production ServiceAccounts and user tokens SHOULD remain least-privilege.

**Rationale**: Prompt-based approval is unreliable and fights useful remediation advice. Real safety is fail-closed policy + RBAC.

### 2. Live API First; K8sGPT and Memory as Supporting Signals

**Invariant**: Ground truth is live Kubernetes API state. K8sGPT Results and institutional memory MAY inform answers but MUST be treated as potentially stale or secondary until verified.

**Enforcement**:

- Chat assessments MUST prefer live tool observations over Result CRD or memory text alone.
- Weather and dashboards MAY summarize Results; chat MUST NOT present unverified findings as definitive without live check guidance.
- Result schema changes MUST update reader code and dashboard assumptions as needed.

**Rationale**: Stale diagnostics or wrong memories cause bad remediations.

### 3. Explainability

**Invariant**: Every AI recommendation MUST include why it was flagged, what evidence was observed, and what remediation means (not only a bare command).

**Enforcement**:

- System prompt response structure (assessment / hypothesis / remediation) MUST be preserved unless intentionally redesigned with tests.
- Skills and tools MUST surface concrete resource names and errors—no placeholder names like `<pod>`.
- Prefer GitOps/IaC remediation advice for lasting fixes.

**Rationale**: Knowledge transfer beats black-box answers under incident pressure.

### 4. GitOps as Delivery Truth

**Invariant**: Steady-state cluster desired state for this product lives in git via **Argo CD + Helm**. Imperative deploy is emergency-only.

**Enforcement**:

- Application config changes go through `helm/` and/or `argocd/apps/*` on `main` (PR workflow).
- Chart `llm.createSecret` MUST remain false for GitOps; secrets are out-of-band.
- Production images MUST use **git SHA** tags; `latest` MUST NOT be the production pin.
- Flux resources MUST NOT be reintroduced without a constitution amendment and doc rewrite.
- `k8s/` raw manifests are reference/legacy—new features prefer Helm templates.
- `kubeApi` policy defaults and memory service config MUST be GitOps-visible (values/env), not ad-hoc pod edits.

**Rationale**: Pull-based reconcile and auditable pins beat brittle runner deploys.

### 5. Secrets and Session Integrity

**Invariant**: Credentials and LLM keys MUST never be committed. Sessions MUST support short-lived auth without logging tokens. Agent-visible Secret **payloads** MUST default to identify-only.

**Enforcement**:

- No API keys, kubeconfigs, or GHCR tokens in git.
- Credential store is in-memory with TTL; session binding via HttpOnly `session_id` cookie and/or `X-Session-Id` header.
- Logs MUST NOT include access keys, session tokens, full kubeconfig, or Secret values.
- Wrapper redaction MUST strip Secret `data`/`stringData` before tool results reach the model unless policy explicitly allows read-data.
- Institutional memory ingest MUST scrub high-risk secret patterns; MUST NOT store raw secret values by design.
- Optional single-cluster pin (`IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`) MUST verify access on credential submit when set.

**Rationale**: Temporary creds and redaction reduce blast radius; secret leakage is an incident.

### 6. Reliability Over Completeness

**Invariant**: Prefer accurate, actionable findings over noisy comprehensive coverage.

**Enforcement**:

- Weather and chat SHOULD de-emphasize low-confidence or unverified noise.
- False-positive patterns discovered in ops SHOULD be suppressed or documented.

**Rationale**: Alert fatigue trains engineers to ignore real issues.

### 7. DevOps-First UX

**Invariant**: Optimize for time-to-resolution: dense status, fast auth, clear cluster context, minimal ceremony for common tasks.

**Enforcement**:

- Auth, weather, and chat MUST remain usable without multi-page wizards for the happy path.
- Ingress host/path, `app.apiBaseUrl`, `app.publicUrl`, and CORS MUST stay aligned when URLs change.
- Manual “Save to knowledge base” MUST NOT be required for institutional memory (auto memory is the product path).

**Rationale**: Incident response is high-pressure; friction kills adoption.

### 8. Testability and Determinism

**Invariant**: Core logic MUST be testable without a production cluster; fixtures cover common failure modes.

**Enforcement**:

- Kubernetes access goes through mockable wrapper layers; unit tests use fixtures and table-driven policy matrices.
- Backend: `pytest`; frontend: Jest/RTL; optional Playwright e2e.
- CI MUST run unit/contract tests without live cluster credentials.
- MemoryPort fakes and kube policy tests MUST cover mutate-off and secret redaction defaults.

**Rationale**: Flaky cluster-only tests block delivery.

### 9. Observability of the Assistant

**Invariant**: Queries and analysis paths MUST be reconstructable enough to debug "what did the bot see?"

**Enforcement**:

- API logging includes session id (truncated), timestamp, and outcome class—not secrets.
- Conversation history retains cluster-scoped context where designed.
- Deployments expose `/api/health` (or equivalent) for smoke checks.
- Denied wrapper calls SHOULD log reason codes when `logDeniedRequests` is enabled (no secret bodies).

**Rationale**: Post-incident review needs assistant context.

### 10. Environment-Scoped Privileges

**Invariant**: Dev/test may enable broader `kubeApi` mutate overlays for validation. Production-facing defaults MUST keep mutate off and secret data denied unless an explicit, reviewed overlay enables them.

**Enforcement**:

- Separate values/secrets per environment; never copy prod keys into git or local fixtures.
- Agents MAY deploy and test in designated non-prod clusters with human oversight.
- Labels or platform policy for `environment=production` override any "agent convenience" shortcuts.

**Rationale**: Agents need real clusters to verify; production stays constrained by defaults.

## Architectural Decisions

### Code-Enforced Kube Wrappers (policy + credentials)

**Status**: Accepted (v3.0.0)  
**Context**: Prompt dual-approval and anti-recommendation guards were unreliable and blocked useful advice.  
**Consequences**: Single authorize chokepoint; Helm `kubeApi` defaults; free recommendations; constitution v2 chat-approval model superseded.

### Approval-Gated Agentic Tools (chat phrases)

**Status**: **Superseded** by Code-Enforced Kube Wrappers  
**Context**: v2 interim model.  
**Consequences**: Do not reintroduce phrase-based auth as the primary gate without a new MAJOR amend.

### Argo CD + Helm (not Flux)

**Status**: Accepted  
**Context**: Flux path removed; app-of-apps + charts under `argocd/` and `helm/`.  
**Consequences**: Image Updater can write SHA tags; Actions direct_deploy is emergency-only.

### Institutional Memory (Vestige-class MCP)

**Status**: Accepted (target)  
**Context**: FAISS in-process KB is being replaced by cluster-local MCP memory with auto recall/ingest.  
**Consequences**: Single-writer memory service; AGPL process boundary; no dual-write FAISS after cutover.

### FAISS Knowledge Base on PVC

**Status**: **Superseded** (runtime) by Vestige-class memory for product path  
**Context**: Historical design.  
**Consequences**: Optional one-time import only; do not keep FAISS on the request path after cutover.

### Decoupled K8sGPT Operator

**Status**: Accepted  
**Context**: Operator/instance analyze in-cluster; chatbot consumes Results + live API.  
**Consequences**: Operator lifecycle managed via GitOps apps.

### In-Memory Credentials + Session Cookie

**Status**: Accepted  
**Context**: Short-lived Kion sessions; multi-replica needs sticky sessions or future external store.  
**Consequences**: Default chatbot replicaCount often 1; horizontal scale requires session redesign.

## Non-Negotiable Rules

1. MUST NOT execute cluster mutations when wrapper policy has mutate disabled (default).
2. MUST NOT return Secret **values** to the agent under default policy (identify-only).
3. MUST NOT use system-prompt dual-approval or anti-recommend rules as the security boundary.
4. MUST NOT commit secrets, kubeconfigs, or embedding/FAISS index binaries.
5. MUST NOT pin production chatbot image to floating `latest`.
6. MUST NOT reintroduce Flux as delivery without amending GitOps principle and docs.
7. MUST NOT log credentials, full session tokens, or Secret values.
8. MUST ground chat claims in live evidence or clearly mark unverified K8sGPT/memory signal.
9. MUST keep Helm/Argo ingress, API base URL, and CORS aligned when changing public URLs.
10. MUST run automated tests for behavioral changes in auth, chat tools, kube policy, or Result parsing.

## Enforcement Mechanisms

| Principle | Code / Config | Verification |
|-----------|---------------|--------------|
| Policy-gated mutation | `kube_policy` authorize + Helm `kubeApi` | Table-driven unit tests; mutate-off default |
| Secrets identify-only | redact on Secret responses | Tests: no base64 data in tool payload |
| Live API first | Agent tools + prompt | Review + integration smoke |
| Explainability | `prompts/system.md` structure | Prompt regression tests |
| GitOps | `argocd/`, `helm/` | Argo sync; no secret-in-chart |
| Session/secrets hygiene | credentials API, scrub on memory ingest | No secrets in git; auth tests |
| Testability | mocks, fixtures, CI | `pytest`, frontend tests |

## Exceptions

### Non-production elevated access

**Exception**: Dev/test may set `kubeApi.allowMutate: true` and broader method allowlists via GitOps overlay.  
**Constraint**: Does not apply to production defaults without explicit reviewed overlay.

### Emergency direct deploy

**Exception**: GitHub Actions `direct_deploy` (or manual helm/kubectl) may bypass pull-based flow during outages.  
**Constraint**: Document the change; return desired state to git promptly.

### Temporary debug namespaces

**Exception**: Isolated debug namespaces for chaos/load tests.  
**Constraint**: Time-bounded; not shared with production app namespaces.

## Review Process

This constitution is reviewed:

- **On every major feature**: Plan Constitution Check must pass or justify Complexity Tracking.
- **On security/incident**: Any secret leak or unexpected mutation triggers immediate review.
- **At least quarterly**: Principles still match deployed product.

Amendments require:

1. PR updating `.specify/memory/constitution.md` with Sync Impact Report comment.
2. Semver bump: MAJOR (incompatible principle change), MINOR (new principle), PATCH (clarification).
3. Propagation to plan/spec/tasks templates and `AGENTS.md` / `docs/` when behavior changes.
4. Approval from repository maintainers before merge to `main`.

## Appendix: Key paths

| Path | Role |
|------|------|
| `argocd/` | App-of-apps GitOps |
| `helm/devops-chatbot` | Primary app chart (`kubeApi` defaults) |
| `backend/kube_policy/` | Authorize + redact (target) |
| `backend/memory/` | MemoryPort + Vestige client (target) |
| `backend/agentic_engine.py` | Agent loop |
| `backend/prompts/system.md` | Minimal agent instructions |
| `backend/skills/` | Skill packs |
| `docs/` | Human documentation |
| `AGENTS.md` | AI agent operating rules |

## Appendix: K8sGPT Result CRD (reference)

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: <resource>-<kind>-<hash>
  namespace: <namespace>
spec:
  kind: <Pod|Deployment|Service|...>
  name: <resource-name>
  namespace: <namespace>
  error: <error-type>
  details: <explanation>
  severity: <critical|major|minor|unknown>
```

Treat `details` as assistive text; verify against live API before acting.
