# Tasks: Vestige Memory + Code-Enforced Cluster Access

**Input**: Design documents from `/specs/002-vestige-memory-mcp/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md, spike/SPIKE_REPORT.md  

**Tests**: Included — required by FR-012, FR-023, FR-026, SC-009–SC-013.

**Organization**: Phases by user story so each story is independently testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable (different files, no incomplete blockers)
- **[USn]**: User story label (US1–US5)

## Path Conventions

- Backend: `backend/`, `backend/api/`, `backend/tests/`, `backend/prompts/`
- Frontend: `frontend/src/`
- GitOps: `helm/`, `argocd/apps/`
- Docs: `docs/`, `AGENTS.md`, `.specify/memory/constitution.md`

---

## Phase 1: Setup

**Purpose**: Branch hygiene and package scaffolding only.

- [x] T001 Confirm branch `002-vestige-memory-mcp` and feature docs under `specs/002-vestige-memory-mcp/`
- [x] T002 [P] Create package skeleton `backend/memory/__init__.py` and `backend/kube_policy/__init__.py`
- [x] T003 [P] Add spike ignore hygiene already at `specs/002-vestige-memory-mcp/spike/.gitignore` (verify node_modules/data not staged)

---

## Phase 2: Foundational (blocking)

**Purpose**: Shared ports/policy every story depends on. **No user story work until this phase is complete.**

**Checkpoint**: `MemoryPort` + `NoopMemory` importable; `KubeApiPolicy` loads defaults from env; table-driven authorize tests pass for defaults.

- [x] T004 Implement `MemoryPort`, `RecallHit`, `IngestResult`, `MemoryHealth` in `backend/memory/port.py` per `specs/002-vestige-memory-mcp/contracts/memory-port.md`
- [x] T005 [P] Implement `NoopMemory` in `backend/memory/noop.py` (empty recall, no-op ingest, degraded/ready flags)
- [x] T006 [P] Implement secret/scrub helpers in `backend/memory/scrub.py` for auto-ingest text
- [x] T007 Implement durable-turn heuristics in `backend/memory/policy.py` per `specs/002-vestige-memory-mcp/data-model.md`
- [x] T008 Implement `get_memory_port()` factory in `backend/memory/__init__.py` (`MEMORY_BACKEND=noop|vestige`)
- [x] T009 Implement `KubeApiPolicy` dataclass + `load_policy_from_env()` in `backend/kube_policy/policy.py` matching Helm `kubeApi` defaults in `helm/devops-chatbot/values.yaml`
- [x] T010 Implement `authorize(request) -> Allow|Deny` ordered checks in `backend/kube_policy/authorize.py` per `specs/002-vestige-memory-mcp/contracts/access-model.md` and `spec.md` evaluation order
- [x] T011 [P] Implement Secret identify/redact in `backend/kube_policy/redact.py` (strip `data`/`stringData` values; optional `dataKeys`)
- [x] T012 [P] Unit tests for policy load + authorize matrix in `backend/tests/test_kube_wrapper_flags.py` (GET allow, mutate deny, secrets identify vs data, exec deny)
- [x] T013 [P] Unit tests for MemoryPort noop + scrub + durable policy in `backend/tests/test_memory_port.py` and `backend/tests/test_memory_policy.py`

---

## Phase 3: User Story 1 — Automatic recall (P1) 🎯 MVP core

**Goal**: Chat primes with Vestige (or noop) memories without KB UI.  
**Independent test**: Seed memory / mock port with known incident; ask related question; response context includes prior lesson; memory down → chat still works.

- [x] T014 [US1] Implement Vestige HTTP MCP client in `backend/memory/vestige_mcp.py` (initialize, `mcp-session-id`, `MCP-Protocol-Version`, Bearer token, tools/call for `recall` / `session_start` / `memory_status`) per `specs/002-vestige-memory-mcp/contracts/vestige-mcp-tools.md` and spike notes
- [x] T015 [US1] Map `recall` / `session_start` results into `list[RecallHit]` in `backend/memory/vestige_mcp.py`
- [x] T016 [US1] Wire pre-turn memory prime in `backend/api/chat.py`: replace `rag.search_knowledge_base` with `MemoryPort.recall` / `session_start`; pass hits into `AgentEngine` as memory summary (not FAISS)
- [x] T017 [US1] Update `backend/agentic_engine.py` to inject **`memory_summary`** (not `kb_summary`) from recall hits into the system prompt placeholders
- [x] T018 [US1] Remove `search_knowledge_base` tool from `backend/agent_tools.py` for MVP (**prime-only** memory; no in-loop memory tool required for US1)
- [x] T019 [P] [US1] Tests for degraded memory path in `backend/tests/test_chat_memory_degraded.py` (noop/unavailable does not 500 chat)
- [x] T020 [P] [US1] Contract/unit tests for Vestige client request shaping in `backend/tests/test_vestige_mcp_client.py` (mock HTTP; session headers)

**Checkpoint**: Chat works with `MEMORY_BACKEND=noop`; with mock/live Vestige, recall hits appear in agent context.

---

## Phase 4: User Story 2 — Automatic save (P1)

**Goal**: Durable turns auto-ingest to Vestige without Save-to-KB.  
**Independent test**: Complete durable turn → new session recall surfaces it; ephemeral turns not stored.

- [x] T021 [US2] Implement post-turn auto-ingest in `backend/api/chat.py`: after successful agent response, `policy.is_durable` → `scrub` → `MemoryPort.ingest` (non-blocking failure → `metadata.memory_ingested=false`)
- [x] T022 [US2] Map ingest to Vestige `smart_ingest` in `backend/memory/vestige_mcp.py` with structured content template from `contracts/vestige-mcp-tools.md`
- [x] T023 [US2] Add `ChatResponse.metadata` fields (`memory_degraded`, `memory_hits`, `memory_ingested`, `memory_ingest_status`) in `backend/api/chat.py` per `contracts/api-deprecations.md`
- [x] T024 [P] [US2] Tests for durable vs ephemeral ingest decisions in `backend/tests/test_memory_policy.py`
- [x] T025 [P] [US2] Tests that scrub rejects high-risk secrets before ingest in `backend/tests/test_memory_port.py`

**Checkpoint**: Auto-save path covered by tests; optional local Vestige smoke per `quickstart.md`.

---

## Phase 5: User Story 3 — Free recommendations + code-enforced access (P1)

**Goal**: Prompt no longer fights recommendations; mutations gated only by `kubeApi` policy + user creds.  
**Independent test**: “How do I fix X?” yields remediation text with mutate off; mutate tool call blocked; secrets identify-only.  
**Prerequisite**: Constitution **v3.0.0** is already on branch (policy-gated mutation). Do not reintroduce chat dual-approval.

- [x] T026 [US3] Slim `backend/prompts/system.md`: remove dual-approval / anti-recommend guards; keep wrappers-only + live evidence first + response structure (aligned with constitution v3)
- [x] T027 [US3] Remove phrase-based auth as primary gate: delete/stop using `_is_mutation_approval_prompt` authorization path in `backend/api/chat.py`; stop driving mutate via `require_human_approval` chat phrases
- [x] T028 [US3] Wire `authorize` + `redact` into `_tool_k8s_api_request` in `backend/agent_tools.py`; remove observe-only/approval branches as security (replace with policy); surface RBAC failures in tool result + assistant text / optional `metadata.kube_denied`
- [x] T029 [US3] Load policy into agent context / module singleton from env at app startup in `backend/kube_policy/policy.py`
- [x] T030 [US3] Ensure structured deny payloads `{blocked, reason, request}` in `backend/agent_tools.py` match `contracts/access-model.md`
- [x] T031 [P] [US3] Expand `backend/tests/test_kube_wrapper_flags.py` for secrets identify vs data, default methods GET-only, exec deny, mutate-on method allowlist
- [x] T032 [P] [US3] Add regression test that system prompt file no longer contains dual-approval / ban-recommendations language in `backend/tests/test_system_prompt_guards.py`

**Checkpoint**: SC-009–SC-013 style unit tests green for access model.

---

## Phase 6: User Story 4 — Remove Save-to-KB UI (P2)

**Goal**: No manual KB save surface.  
**Independent test**: UI has no Save-to-KB; solutions write API gone or 410.

- [x] T033 [US4] Remove `SolutionSubmitDialog` usage and save handlers from `frontend/src/components/ChatInterface.tsx`
- [x] T034 [P] [US4] Delete `frontend/src/components/SolutionSubmitDialog.tsx` and `frontend/src/components/SolutionSubmitDialog.test.tsx`
- [x] T035 [P] [US4] Remove `solutionsApi` submit (and dead list UI usage) from `frontend/src/services/api.ts`; clean `frontend/src/types/solution.ts` if unused
- [x] T036 [US4] Delete solutions/KB API routes entirely (never in production; no 410 stub required)
- [x] T037 [P] [US4] Update any frontend tests referencing Save-to-KB in `frontend/src/`

**Checkpoint**: Primary chat UI has zero Save-to-KB entry points.

---

## Phase 7: User Story 5 — In-cluster memory ops (P2)

**Goal**: Vestige + kubeApi policy deployable via Helm/Argo, data on PVC.  
**Independent test**: Chart templates render; env present; single-replica Vestige; docs describe backup.

- [x] T038 [US5] Confirm/extend `kubeApi` defaults already in `helm/devops-chatbot/values.yaml`; wire env vars into `helm/devops-chatbot/templates/deployment.yaml`
- [x] T039 [US5] Colocate Vestige MCP binary in chatbot image (Dockerfile + supervisord); data on shared PVC `/data/vestige` (separate `helm/vestige-memory` retired)
- [x] T040 [US5] Wire chatbot env `MEMORY_BACKEND`, `VESTIGE_HTTP_URL`, `VESTIGE_DATA_DIR`, `FASTEMBED_CACHE_PATH` in `helm/devops-chatbot/templates/deployment.yaml` and values (loopback)
- [x] T041 [US5] Remove separate Argo Application for vestige-memory (colocated; no `60-vestige-memory.yaml`)
- [x] T042 [P] [US5] Document deploy/backup/wipe in `docs/deployment.md` and ops bits in `specs/002-vestige-memory-mcp/quickstart.md`
- [x] T043 [P] [US5] Remove FAISS runtime init from `backend/rag_integration.py`; stop dual-write paths; remove `backend/kb_seeder.py` / `solution_manager.py` from runtime
- [ ] T044 [P] [US5] SC-003 PVC-backed recall after pod restart — **manual/release** (unit factory/env contracts only in `test_memory_persistence.py`; see release-validation.md)

**Checkpoint**: `helm template` succeeds; local/quickstart path still works with noop/Vestige.

---

## Phase 8: Polish & cross-cutting

- [x] T045 [P] Confirm `.specify/memory/constitution.md` is **v3.0.0** (policy-gated mutation); no further amend required unless drift
- [x] T046 [P] Update `AGENTS.md`, `docs/architecture.md`, `docs/usage.md`, `docs/security.md` for Vestige memory + kubeApi defaults + free recommendations
- [x] T047 [P] Update `AGENTS.md` agent context for MemoryPort / kube policy if not already current
- [x] T048 Remove dead FAISS/KB imports and fix broken tests under `backend/tests/`
- [x] T049 Run `backend` pytest subset for memory + kube policy + chat; run frontend unit tests for ChatInterface
- [ ] T050 Manual smoke per `specs/002-vestige-memory-mcp/quickstart.md` (optional live Vestige)
- [ ] T051 Release/manual validation checklist for SC-001, SC-002, SC-003, SC-008 (human-graded / soak); record results under `specs/002-vestige-memory-mcp/checklists/release-validation.md` when executed
- [x] T052 FR-014 legacy FAISS import — **not applicable** (never production; FAISS stack deleted)

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational (MemoryPort + KubeApiPolicy)
    ↓
    ├─→ Phase 3 US1 Recall ──→ Phase 4 US2 Auto-save
    ├─→ Phase 5 US3 Access model (can parallel with US1 after T009–T011)
    └─→ Phase 6 US4 UI removal (independent after chat still works)
            ↓
    Phase 7 US5 GitOps / FAISS removal (needs US1–US2 client + US3 env names)
            ↓
    Phase 8 Polish
```

**Story order recommendation**: Foundational → US1 → US2 → US3 (or US3 // US1 after policy module) → US4 → US5 → Polish.

**MVP**: Phase 2 + US1 (recall with noop/mock) demonstrates architecture; add US2 + US3 for product-complete core; US4/US5 for cutover.

---

## Parallel examples

```text
# After T004–T008 exist:
T009 + T005 already done → T012 and T013 in parallel

# After Foundational:
T014 Vestige client || T026 system.md slim || T033 start UI removal prep

# US4 parallel:
T034 || T035 || T036
```

---

## Implementation strategy

1. **MVP**: Foundational + US1 with `MEMORY_BACKEND=noop`, then mock Vestige HTTP.  
2. **Product core**: US2 auto-save + US3 policy gate + prompt cleanup.  
3. **Cutover**: US4 UI/API + US5 Helm + FAISS removal + docs.  
4. **Do not** dual-write FAISS after T043.  
5. **Do not** reintroduce chat-phrase mutation unlock after T027–T028 (constitution v3).

---

## Task count summary

| Phase | Story | Tasks |
|-------|--------|-------|
| 1 Setup | — | T001–T003 (3) |
| 2 Foundational | — | T004–T013 (10) |
| 3 | US1 Recall | T014–T020 (7) |
| 4 | US2 Auto-save | T021–T025 (5) |
| 5 | US3 Access | T026–T032 (7) |
| 6 | US4 Save-to-KB removal | T033–T037 (5) |
| 7 | US5 Cluster memory | T038–T044 (7) |
| 8 Polish | — | T045–T052 (8) |
| **Total** | | **52** |

**Format validation**: All tasks use `- [ ]`, sequential IDs, story labels on US phases only, file paths in descriptions.
