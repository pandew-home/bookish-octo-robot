# Implementation Plan: Cluster-Local Agent Memory (Vestige MCP)

**Branch**: `002-vestige-memory-mcp` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/002-vestige-memory-mcp/spec.md`

## Summary

Two coordinated product changes on this branch:

**A. Vestige memory** — Replace in-process FAISS KB retrieve/save with a **Vestige MCP** layer that auto-recalls and auto-ingests troubleshooting memory (cluster PVC, no Save-to-KB UI, no dual-write).

**B. Code-enforced cluster access** — Strip system-prompt guards that fight **recommendations** or simulate auth via verbal approval. Keep only “use the Python kube API wrappers for cluster I/O.” **Execution** of mutations is gated by (1) user credentials and (2) wrapper flags (default mutate off). Free-text remediation advice is allowed.

**Approach**:

1. `MemoryPort` + `VestigeMcpMemory` (HTTP MCP service, single-writer PVC).  
2. Slim `backend/prompts/system.md` + remove chat-phrase approval as primary gate; centralize mutate allow/deny in Python kube wrappers / `agent_tools` using explicit flags.  
3. Remove FAISS + Save-to-KB UI.  
4. Constitution **v3.0.0** already amended for policy-gated mutation + free recommendations (implement against v3).

**Spike validated (2026-07-25)**: [spike/SPIKE_REPORT.md](./spike/SPIKE_REPORT.md) — **GO** for Vestige.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/React (frontend), Vestige MCP binary (Rust, prebuilt linux/x64)  
**Primary Dependencies**: FastAPI, existing `AgentEngine`/`agent_tools`, MCP Python client (`mcp` SDK or equivalent stdio JSON-RPC client), Vestige (`vestige-mcp` / `vestige-mcp-server`)  
**Storage**: Vestige SQLite (+ embeddings cache) on Kubernetes PVC (`/data/vestige`); no FAISS index; no external vector SaaS  
**Testing**: pytest (unit + contract with fake MemoryPort / mock MCP), frontend Jest (UI removal), optional Playwright smoke  
**Target Platform**: In-cluster Linux (Civo/k3s/EKS-class), Argo CD + Helm  
**Project Type**: Web application (FastAPI + React) + GitOps charts  
**Performance Goals**: Memory recall budget ≤2s p95 when healthy; chat degrades without memory within existing chat timeout; auto-ingest async/non-blocking after response  
**Constraints**: AGPL-3.0 Vestige accepted for this deployment; single-writer (no multi-replica concurrent SQLite writers); secrets scrubbed before ingest; live K8s API remains authoritative over memory text; offline-capable after embedding model present in image or init  
**Scale/Scope**: Single chatbot deployment / shared team memory per namespace; FAISS legacy import **out of MVP** (FR-014 follow-up only)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*  
*Source: `.specify/memory/constitution.md` (**v3.0.0**)*

| Gate | Pass criteria | Status |
|------|----------------|--------|
| Observe-default / policy-gated mutate | Mutate flags default off; no prompt dual-approval as auth; memory writes ≠ cluster mutations | **Pass** |
| Live API first | Memory supporting only; live tool evidence wins | **Pass** |
| Explainability | Clear assessment structure; recommendations allowed | **Pass** |
| GitOps delivery | Helm/Argo for chatbot + Vestige; no secrets in git | **Pass** |
| Image pin | SHA tags for chatbot/Vestige images | **Pass** |
| Secrets / session | Scrub before ingest; Secret values not returned under default policy | **Pass** |
| Testability | MemoryPort fakes + wrapper flag unit tests | **Pass** |
| Ingress/CORS | Save-to-KB removal only | **Pass** (N/A) |
| Wrappers-only | Agent cluster I/O only via Python kube wrappers | **Pass** |

Post-design re-check: **Pass** (constitution v3.0.0).

## Project Structure

### Documentation (this feature)

```text
specs/002-vestige-memory-mcp/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
│   ├── memory-port.md
│   ├── vestige-mcp-tools.md
│   ├── api-deprecations.md
│   └── access-model.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 via /speckit.tasks (not this command)
```

### Source Code (repository root)

```text
backend/
├── memory/                      # NEW
│   ├── __init__.py
│   ├── port.py                  # MemoryPort protocol + types
│   ├── scrub.py                 # secret/redaction heuristics
│   ├── policy.py                # durable-turn heuristics (what to auto-save)
│   ├── vestige_mcp.py           # HTTP MCP client (session + tools/call)
│   └── noop.py                  # degraded / tests
├── kube_policy/                 # NEW — authorize + redact chokepoint
│   ├── policy.py
│   ├── authorize.py
│   └── redact.py
├── agent_tools.py               # memory tools; mutate only via kube_policy
├── agentic_engine.py            # MemoryPort hooks; memory_summary (not kb_summary)
├── api/chat.py                  # no FAISS; post-turn ingest; no phrase auth
├── api/solutions.py             # 410 / remove write paths
├── prompts/system.md            # wrappers-only; free recommendations
├── rag_integration.py           # LLM-only (strip VectorStore/KB)
└── tests/
    ├── test_memory_port.py
    ├── test_vestige_mcp_client.py
    ├── test_memory_policy.py
    ├── test_chat_memory_degraded.py
    └── test_kube_wrapper_flags.py

frontend/src/
├── components/ChatInterface.tsx     # remove SolutionSubmitDialog wiring
├── components/SolutionSubmitDialog* # delete
├── services/api.ts                  # remove solutionsApi
└── types/solution.ts                # delete or shrink if unused

helm/
├── devops-chatbot/                  # kubeApi defaults + MEMORY_* / VESTIGE_* env
│   values.yaml / templates/*
└── vestige-memory/                  # preferred: separate chart for serve + PVC

argocd/apps/
├── 50-devops-chatbot.yaml
└── (optional) vestige-memory Application

docs/
├── architecture.md, development.md, usage.md, deployment.md, security.md
AGENTS.md
```

**Structure Decision**: **Production topology = separate Vestige Deployment** (`vestige serve` HTTP MCP on ClusterIP) + PVC, single replica writer. Chatbot is HTTP MCP client (`MemoryPort`). Stdio co-process is **dev-only fallback**, not the plan default. Frontend loses Save-to-KB. GitOps = Argo + Helm.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|------------|-------------------------------------|
| MemoryPort abstraction | Testability + future swap | Direct Vestige calls couple AGPL binary to all tests |
| HTTP MCP separate Deployment | Spike-proven; clean health/resources/GitOps | Stdio-only couples lifecycle to chat pod |
| Single replica Vestige writer | SQLite durability | Multi-writer HA not in Vestige local model |
| AGPL Vestige binary | Best product fit (user decision + spike GO) | Mem0/FAISS weaker on product goals |

## Architecture

```text
Browser  →  FastAPI /api/chat/query
                 │
                 ├─ kube_policy.authorize → user-cred K8s API tools + K8sGPT
                 ├─ AgentEngine
                 │     ├─ MemoryPort.recall / session_start → memory_summary
                 │     └─ LLM (no FAISS)
                 │
                 └─ after success: MemoryPort.ingest (scrubbed)
                              │
                              ▼
              Service vestige-memory:3928  (HTTP MCP /mcp)
                              │
                              ▼
                    PVC /data/vestige (SQLite + model cache)
```

### Runtime topology (MVP)

| Component | Placement |
|-----------|-----------|
| Vestige | **Separate Deployment** running `vestige serve --port 3928` (HTTP MCP at `/mcp`) |
| Service | ClusterIP `vestige-memory:3928` |
| Auth | Env `VESTIGE_AUTH_TOKEN` from K8s Secret (not desktop auth_token paths) |
| Data | PVC `/data/vestige` → `VESTIGE_DATA_DIR` |
| Embeddings | Bake `FASTEMBED_CACHE_PATH` into image or seed PVC (~0.5GB observed) |
| Chatbot | MCP HTTP client: `initialize` → `mcp-session-id` + `MCP-Protocol-Version` |
| Replicas | Vestige `replicaCount: 1`; chatbot scaling independent of Vestige process |
| Dev fallback | Optional stdio subprocess — not production default |

**Client requirements (spike-proven)**:

- `Authorization: Bearer <token>`
- `MCP-Protocol-Version: 2024-11-05`
- `mcp-session-id: <from initialize response>`

### Agent memory protocol (automatic)

1. **On chat request (before agent loop)**: `session_start` / `recall` with query + cluster name metadata → inject into system/user context as **`memory_summary`** (do not use `kb_summary` naming for new code).  
2. **During loop**: MVP is **prime-only** for memory (automatic recall). Optional in-loop `recall`/`backfill` tools are post-MVP; do not block US1 on them.  
3. **After successful response**: durable-turn policy → scrub → `smart_ingest` with structured text (problem, evidence, remediation, verification, cluster tag).  
4. **On MCP failure**: log warning; set `metadata.memory_degraded=true`; continue chat.  
5. **Kube denials**: tool returns `{blocked, reason, request}`; agent surfaces failure in response text (and may set metadata such as `kube_denied`).

### Access model (code-enforced)

| Layer | Role |
|-------|------|
| System prompt | Minimal: persona, format, live evidence first, **only use Python kube wrappers** for cluster I/O. **No** anti-recommendation / dual verbal approval as security. |
| Helm `kubeApi` defaults | See `helm/devops-chatbot/values.yaml` + [contracts/access-model.md](./contracts/access-model.md) |
| Wrapper policy | Mutate **off**; methods **GET** only; exec/portforward/proxy/SA writes denied; **Secrets identify-only** (no `data`/`stringData` to agent) |
| User credentials | Real Kubernetes RBAC for whatever the wrapper is allowed to attempt |
| Chat phrase detection | **Remove** as primary authorization |

Recommendations in free text are **never** blocked by flags; only **wrapper execution** (and secret **values**) are.

**Secrets default**: allow list + metadata + key **names**; never return secret **values**; never mutate Secrets unless values explicitly open both global mutate and `secrets.allowMutate`.

### Removal map (FAISS / Save-to-KB)

| Area | Action |
|------|--------|
| `rag.search_knowledge_base` pre-call in `chat.py` | Replace with MemoryPort.recall |
| `kb_search_func` / `search_knowledge_base` tool | Replace with memory tools or drop if prime is enough |
| `VectorStore` / FAISS init | Remove from runtime path |
| `KnowledgeBase` solution CRUD + seeder | Remove runtime; **FR-014 legacy import is out of MVP** (no implement task until follow-up) |
| `POST /api/solutions` + frontend dialog | Remove UI; API 410 Gone or delete |
| Docs claiming FAISS PVC KB | Update to Vestige PVC |

## Implementation phases (for `/speckit.tasks`)

1. **Scaffold MemoryPort + noop + tests**  
2. **Vestige HTTP MCP client + health**  
3. **Wire chat prime + auto-ingest + scrub/policy**  
4. **Wrapper flags + strip prompt approval gates + slim system.md**  
5. **Remove FAISS/KB/UI/API**  
6. **Helm/Argo/Dockerfile/model bake for Vestige**  
7. **Constitution + docs + AGENTS**  
8. **CI green + manual cluster smoke**

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| AGPL compliance | Document in NOTICE; legal already accepted for this project direction |
| SQLite multi-writer | Force replicaCount 1; document HPA off |
| Model download air-gap | Bake model in image / offline init |
| Agent skips ingest | Automatic post-turn ingest in chat.py (not only model tool choice) |
| Process crash | Supervisor restart vestige-mcp; degrade chat |
| Secret leakage into memory | scrub.py + unit tests on patterns |

## Generated artifacts

| Artifact | Path |
|----------|------|
| Research | [research.md](./research.md) |
| Data model | [data-model.md](./data-model.md) |
| Contracts | [contracts/](./contracts/) |
| Quickstart | [quickstart.md](./quickstart.md) |

**Next command**: `/speckit.tasks` to produce `tasks.md`.
