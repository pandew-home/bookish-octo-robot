<!--
Sync Impact Report
- Version change: 1.0.0 → 2.0.0 (MAJOR)
- Rationale: Product is no longer absolute read-only; agentic Kubernetes tools may
  mutate only after explicit human approval. Delivery is Argo CD + Helm (Flux retired).
  FAISS RAG, session cookies, and single-cluster pins are first-class.
- Modified principles:
  - "Read-Only Product Safety" → "Observe-Default, Approval-Gated Mutation"
  - "Operator as Source of Truth" → "Live API First; K8sGPT as Supporting Signal"
  - "Development Access for Testing" → "Environment-Scoped Privileges"
  - Remaining principles refined for GitOps, FAISS, and agentic stack
- Added sections: GitOps & Supply Chain (principle), Secrets & Session Integrity (principle),
  Architectural Decisions for Argo CD / FAISS / approval gates
- Removed sections: Absolute ban on all write RBAC and "never suggest kubectl mutate"
  as product-wide absolutes (replaced by approval + RBAC dual control)
- Templates:
  - .specify/templates/plan-template.md ✅ updated (Constitution Check gates)
  - .specify/templates/tasks-template.md ✅ updated (path conventions)
  - .specify/templates/spec-template.md ✅ updated (security/constitution constraints)
  - .specify/templates/constitution-template.md ⚠ left generic (scaffold only)
  - AGENTS.md ✅ cross-link
- Deferred: None
-->

# DevOps Chatbot (bookish-octo-robot) Constitution

> Core principles and invariants that govern this platform's development and operation.

## Meta

- **Project**: DevOps Chatbot v2.0 (`bookish-octo-robot`) — Kubernetes troubleshooting assistant
- **Repository**: https://github.com/pandew-home/bookish-octo-robot
- **Baseline tag**: `faiss-202607`
- **Ratified**: 2026-03-29
- **Last Amended**: 2026-07-25
- **Version**: 2.0.0

## Purpose

This platform helps DevOps engineers diagnose Kubernetes issues using:

1. **Live cluster state** via authenticated Kubernetes API access (Kion temporary AWS creds and/or kubeconfig).
2. **K8sGPT Result CRDs** as continuous analyzer signals (weather widget + chat context).
3. **FAISS RAG** over a shared knowledge base of team solutions.
4. An **agentic chat backend** (tools + skills) that defaults to observe/diagnose and may execute mutating API calls **only after explicit human approval**.

Delivery is **Argo CD app-of-apps + Helm** (`argocd/`, `helm/`). Images ship as **git SHA** tags to GHCR. Flux is not part of this platform.

## Core Principles

### 1. Observe-Default, Approval-Gated Mutation (NON-NEGOTIABLE)

**Invariant**: Chat and automation MUST default to observe and diagnose. Mutating Kubernetes API operations MUST NOT execute without explicit, in-band human approval for that action.

**Enforcement**:

- `agentic_engine` / `agent_tools` MUST keep human-approval gates for mutating methods.
- `backend/prompts/system.md` MUST instruct the model to explain, then request confirmation before mutate.
- Production ServiceAccounts SHOULD remain least-privilege; write verbs MUST be intentional and documented when present.
- Features that auto-remediate without a human confirmation path are FORBIDDEN unless this constitution is amended (MAJOR).

**Rationale**: Engineers trust diagnostic tools only if they cannot silently change production. Controlled, approved mutation is a product capability—not free-fire cluster admin.

### 2. Live API First; K8sGPT as Supporting Signal

**Invariant**: Ground truth is live Kubernetes API state. K8sGPT Results MAY inform weather and chat but MUST be treated as potentially stale until verified.

**Enforcement**:

- Chat assessments MUST prefer live tool observations over Result CRD text alone.
- Weather and dashboards MAY summarize Results; chat MUST NOT present stale Findings as definitive without verification guidance.
- Result schema changes MUST update both reader code (`k8sgpt_reader`) and any dashboard assumptions.

**Rationale**: Operators can lag; wrong remediation from stale Results is worse than asking for a re-check.

### 3. Explainability

**Invariant**: Every AI recommendation MUST include why it was flagged, what evidence was observed, and what remediation means (not only a command).

**Enforcement**:

- System prompt response format (assessment / hypothesis / remediation) MUST be preserved unless intentionally redesigned with tests.
- Skills and tools MUST surface concrete resource names and errors—no placeholder names like `<pod>`.
- Prefer GitOps/IaC remediation advice for lasting fixes.

**Rationale**: Knowledge transfer beats black-box answers under incident pressure.

### 4. GitOps as Delivery Truth

**Invariant**: Steady-state cluster desired state for this product lives in git via **Argo CD + Helm**. Imperative deploy is emergency-only.

**Enforcement**:

- Application config changes go through `helm/` and/or `argocd/apps/*` on `main` (PR workflow).
- Chart `llm.createSecret` MUST remain false for GitOps; secrets are out-of-band.
- Production images MUST use **git SHA** tags (`ghcr.io/pandew-home/bookish-octo-robot:<sha>`); `latest` MUST NOT be the production pin.
- Flux resources MUST NOT be reintroduced without a constitution amendment and doc rewrite.
- `k8s/` raw manifests are reference/legacy—new features prefer Helm templates.

**Rationale**: Pull-based reconcile beats brittle runner-to-cluster deploys; SHA tags make rollbacks auditable.

### 5. Secrets and Session Integrity

**Invariant**: Credentials and LLM keys MUST never be committed. Sessions MUST support short-lived auth without leaking tokens to logs or client-side durable storage as the only path.

**Enforcement**:

- No API keys, kubeconfigs, or GHCR tokens in git.
- Credential store is in-memory with TTL; session binding via HttpOnly `session_id` cookie and/or `X-Session-Id` header.
- Logs MUST NOT include access keys, session tokens, or full kubeconfig content—session id prefixes only where needed.
- Optional single-cluster pin (`IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`) MUST verify access on credential submit when set.

**Rationale**: Temporary Kion creds and cookie sessions reduce blast radius; logging secrets is an incident.

### 6. Reliability Over Completeness

**Invariant**: Prefer accurate, actionable findings over noisy comprehensive coverage.

**Enforcement**:

- Weather and chat SHOULD de-emphasize low-confidence or unverified noise.
- Response quality and cluster-grounding guards (when present) MUST not be removed without replacement.
- False-positive patterns discovered in ops SHOULD be suppressed or documented.

**Rationale**: Alert fatigue trains engineers to ignore real issues.

### 7. DevOps-First UX

**Invariant**: Optimize for time-to-resolution: dense status, fast auth, clear cluster context, minimal ceremony for common tasks.

**Enforcement**:

- Auth, weather, and chat MUST remain usable without multi-page wizards for the happy path.
- Ingress host/path, `app.apiBaseUrl`, `app.publicUrl`, and CORS MUST stay aligned when URLs change.
- Keyboard-accessible controls for primary actions where practical.

**Rationale**: Incident response is desktop, high-pressure, and intolerant of UX friction.

### 8. Testability and Determinism

**Invariant**: Core logic MUST be testable without a production cluster; fixtures cover common failure modes.

**Enforcement**:

- Kubernetes access goes through mockable layers; unit tests use fixtures.
- Backend: `pytest`; frontend: Jest/RTL; optional Playwright e2e under `frontend/e2e/`.
- CI MUST run unit/contract tests without requiring live cluster credentials.
- K8sGPT Result fixtures for common failures remain available for reader/weather tests.

**Rationale**: Flaky cluster-only tests block delivery and hide regressions.

### 9. Observability of the Assistant

**Invariant**: Queries and analysis paths MUST be reconstructable enough to debug "what did the bot see?"

**Enforcement**:

- API logging includes session id (truncated), timestamp, and outcome class—not secrets.
- Conversation history retains cluster-scoped context where designed.
- Deployments expose `/api/health` (or equivalent) for smoke checks.

**Rationale**: Post-incident review needs assistant context, not only cluster events.

### 10. Environment-Scoped Privileges

**Invariant**: Dev/test may grant elevated access for deploy and validation. Production-facing clusters MUST enforce least privilege and approval-gated mutation product behavior.

**Enforcement**:

- Separate values/secrets per environment; never copy prod keys into git or local fixtures.
- Agents MAY deploy and test in designated non-prod clusters with human oversight.
- Labels or platform policy for `environment=production` override any "agent convenience" shortcuts.

**Rationale**: Agents need real clusters to verify; production must stay constrained.

## Architectural Decisions

### Approval-Gated Agentic Tools

**Status**: Accepted  
**Context**: Absolute read-only blocked useful remediation and testing of execute paths.  
**Consequences**: Dual control (product approval + RBAC); higher complexity than pure read-only; constitution v1 "never write" is superseded.

### Argo CD + Helm (not Flux)

**Status**: Accepted  
**Context**: Flux path removed; app-of-apps + charts under `argocd/` and `helm/`.  
**Consequences**: Image Updater can write SHA tags; Actions direct_deploy is emergency-only.

### FAISS Knowledge Base on PVC

**Status**: Accepted  
**Context**: Team solutions need semantic retrieval beside live diagnostics.  
**Consequences**: RWX PVC for multi-replica; seeding on startup; index not committed to git.

### Decoupled K8sGPT Operator

**Status**: Accepted  
**Context**: Operator/instance analyze in-cluster; chatbot consumes Results + live API.  
**Consequences**: Operator lifecycle managed via GitOps apps; chatbot not the sole analyzer.

### In-Memory Credentials + Session Cookie

**Status**: Accepted  
**Context**: Short-lived Kion sessions; multi-replica needs sticky sessions or future external store.  
**Consequences**: Default replicaCount often 1; horizontal scale requires session redesign.

## Non-Negotiable Rules

1. MUST NOT remove mutation approval gates without a MAJOR constitution amendment and security review.
2. MUST NOT commit secrets, kubeconfigs, or FAISS index binaries.
3. MUST NOT pin production chatbot image to floating `latest`.
4. MUST NOT reintroduce Flux as delivery without amending GitOps principle and docs.
5. MUST NOT log credentials or full session tokens.
6. MUST ground chat claims in live evidence or clearly mark unverified K8sGPT/KB signal.
7. MUST keep Helm/Argo ingress, API base URL, and CORS aligned when changing public URLs.
8. MUST run automated tests for behavioral changes in auth, chat tools, or Result parsing.

## Enforcement Mechanisms

| Principle | Code / Config | Verification |
|-----------|---------------|--------------|
| Approval-gated mutation | `agentic_engine`, `agent_tools`, system prompt | Unit/integration tests for blocked mutate without approval |
| Live API first | Chat agent tools, k8sgpt_reader usage | Tests + manual cluster smoke |
| Explainability | `prompts/system.md`, skills | Prompt/contract tests; review |
| GitOps | `argocd/`, `helm/`, Image Updater annotations | Argo sync health; no secret-in-chart |
| Secrets/session | credentials API, cookie flags | No secrets in git; auth tests |
| Reliability | weather calculator, quality guards | Fixture-based weather/chat tests |
| Testability | mocks, fixtures, CI | `pytest`, frontend tests in CI |
| Observability | logging middleware, health | Smoke `/api/health` |

## Exceptions

### Non-production elevated access

**Exception**: Dev/test clusters may allow write RBAC and agent-driven deploy for validation.  
**Constraint**: Does not apply to production-labeled environments.

### Emergency direct deploy

**Exception**: GitHub Actions `direct_deploy` (or manual helm/kubectl) may bypass pull-based flow during outages.  
**Constraint**: Document the change; return desired state to git promptly.

### Temporary debug namespaces

**Exception**: Isolated debug namespaces for chaos/load tests.  
**Constraint**: Time-bounded; not shared with production app namespaces.

## Review Process

This constitution is reviewed:

- **On every major feature**: Plan Constitution Check must pass or justify Complexity Tracking.
- **On security/incident**: Any approval-bypass or secret leak triggers immediate review.
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
| `helm/devops-chatbot` | Primary app chart |
| `backend/agentic_engine.py` | Agent loop |
| `backend/prompts/system.md` | System prompt |
| `backend/skills/` | Skill packs |
| `libs/devops-{k8s,kb,rag}` | Shared libraries |
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
