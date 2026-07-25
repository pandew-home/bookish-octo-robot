# Research: Cluster-Local Agent Memory (Vestige MCP)

**Feature**: `002-vestige-memory-mcp`  
**Date**: 2026-07-25

## 1. Memory backend selection

**Decision**: Use **Vestige** (`https://github.com/samvallad33/vestige`) as the production memory backend behind a `MemoryPort` interface.

**Rationale**:

- Local-first SQLite storage fits “must save local to the cluster.”
- MCP-native tools (`recall`, `smart_ingest`, `session_start`, `backfill`, contradiction status) match “MCP server model” and beat plain FAISS similarity for troubleshooting.
- Single binary (~25MB) + Dockerfile pattern with `VESTIGE_DATA_DIR=/data`.
- Stakeholder fit review concluded Vestige is the preferred intelligence layer if AGPL and single-writer ops are accepted (accepted for this plan).

**Alternatives considered**:

| Option | Why not primary |
|--------|-----------------|
| Keep FAISS + auto-save | Does not meet “better memory” or MCP goals |
| Mem0 OSS + MCP | Strong ops/ecosystem; weaker causal/contradiction story vs Vestige for this product narrative |
| Qdrant/Chroma sidecar | Still vector RAG; more infra |
| Custom SQLite MCP | Full control but rebuilds Vestige’s value |

## 2. Process topology in Kubernetes

**Decision**: **Separate Deployment** running `vestige serve` (**HTTP MCP** on `/mcp`), PVC-backed, **replicaCount: 1**. Chatbot connects as MCP HTTP client.

**Rationale** (spike 2026-07-25):

- Vestige 2.2.1 includes first-class `serve` HTTP transport — no custom bridge required.
- Cleaner GitOps (independent health, resources, image bake for model cache).
- SQLite still single-writer → one Vestige replica.
- Stdio remains fine for local dev; not required for cluster MVP.

**Alternatives considered**:

| Option | Why not primary |
|--------|-----------------|
| Co-located stdio subprocess | Works but couples lifecycle/resources to chat pod |
| Multi-replica + external DB | Out of Vestige local-first model |
| Custom HTTP gateway over stdio | Unnecessary after `serve` |

## 3. Integration style (agent automatic memory)

**Decision**: **Hybrid**:

1. **Deterministic** pre-turn `recall` / session prime in `chat.py` (always attempt).  
2. **Deterministic** post-turn `smart_ingest` when durability policy passes (always attempt; not left solely to the LLM).  
3. Optional in-loop tools for `backfill` / extra `recall` if the model requests them.

**Rationale**: Spec requires automatic save/recall; relying only on tool-calling is flaky. Deterministic hooks guarantee product behavior; tools remain for advanced probes.

**Alternatives considered**:

- Protocol-only (prompt the model to call tools) — rejected as sole mechanism.  
- Retrieve-only with manual save — rejected by product goals.

## 4. FAISS / knowledge-base retirement

**Decision**: Full runtime removal of FAISS vector store and manual solution KB path at cutover (no dual-write). Optional offline import script is **phase 2**.

**Rationale**: Spec forbids dual-write; greenfield Vestige memory is acceptable for MVP; import can be best-effort later.

**Remove / stop using**:

- `VectorStore` / FAISS init in `rag_integration`
- `search_knowledge_base` pre-search + tool
- `KnowledgeBase` solution CRUD in request path
- `kb_seeder` automatic FAISS seed
- Frontend `SolutionSubmitDialog` + `solutionsApi`
- `POST /api/solutions` as user-facing write (410 or delete)

**Keep**:

- LLM client path (chat still needs a model)
- Conversation history store (session chat, not institutional memory)
- K8sGPT + live API tools

## 5. MCP client library

**Decision**: Use the official **Python MCP SDK** (stdio client session) if dependency size is acceptable; otherwise a minimal JSON-RPC stdio client scoped to tools/call + tools/list.

**Rationale**: Prefer maintained protocol compliance for tools/list and tools/call; limit surface to what Vestige exposes.

**Alternatives considered**: Shell out per call — too slow/fragile; raw sockets — no server socket on Vestige MVP path.

## 6. Secret handling

**Decision**: Pre-ingest scrubber strips AWS keys, bearer tokens, private keys, kubeconfig-looking blocks; refuse ingest if residual high-risk patterns remain.

**Rationale**: Constitution secrets hygiene; free-text chat may include pasted credentials.

## 7. Embedding model / air-gap

**Decision**: Production image **bakes or pre-stages** Vestige’s embedding model into the PVC/image so first pod start does not require GitHub/npm network. Document offline build steps in quickstart.

**Rationale**: Cluster may block egress; first-run 130MB download is a deploy hazard.

## 8. License

**Decision**: Proceed with AGPL-3.0 Vestige; add NOTICE/attribution; do not relicense project code as AGPL unless counsel requires—keep chatbot Apache/MIT/existing license; treat Vestige as separate process.

**Rationale**: User accepted Vestige fit; process boundary limits coupling; still require org awareness of network-service AGPL implications.

## 9. Testing strategy

**Decision**:

- Unit: `MemoryPort` fake; policy/scrub pure tests.  
- Contract: mock MCP server (stdio fixture) or recorded tool responses.  
- Integration (optional CI): real `vestige-mcp` binary if available on runner.  
- Frontend: assert Save-to-KB controls gone.

## 10. Access model: code-enforced, not prompt-enforced

**Decision**: Remove prompt guards that suppress recommendations or use verbal multi-step approval as auth. Keep prompt rule: **cluster I/O only via Python kube wrappers**. Permissions = **user creds + wrapper flags** (mutate default off).

**Rationale**: Operators report the model constantly fights recommendation bans; prompt-as-auth is unreliable. Hard enforcement belongs in wrappers; free-text advice is valuable even when execution is disabled.

**Alternatives considered**:

| Option | Why not |
|--------|---------|
| Keep dual chat approval + anti-recommend prompts | User pain; brittle; still not real RBAC |
| Prompt-only “observe-only” | Model ignores; still need code flags |
| Full OPA/policy engine | Out of scope for this feature |

**Spike/code touchpoints**: `system.md` approval lines; `require_human_approval` / `_is_mutation_approval_prompt` in `chat.py` / `agent_tools.py` — replace with flag checks on mutate methods.

## 11. Resolved clarifications

| Topic | Resolution |
|-------|------------|
| Vestige vs alternatives | Vestige primary (spike GO) |
| Multi-replica memory | Not in MVP (replica 1) |
| FAISS migration | Phase 2 optional script |
| Auto memory reliability | Deterministic hooks + optional tools |
| Topology | HTTP MCP Deployment + PVC |
| Recommendations | Allowed freely |
| Mutation auth | Wrapper flags + user RBAC only |
