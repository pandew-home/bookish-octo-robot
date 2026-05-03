# Prompt Flow Redesign — Backend Only

## Context

Simplify the chatbot prompt flow to use in-cluster auth and a single LLM call. Scope is **backend only** — no frontend or operator changes.

### Original Flow
```
User Query → Sanitize → Rate Limit → Auth → Cluster Select →
K8sGPT Reader → RAG Search → AgentEngine (tool loop) →
Response Parser → Save History → Return
```

### Implemented Flow
```
User Query → Rate Limit → K8sGPT Reader → RAG Search →
AgentEngine (single LLM call with K8sGPT + KB context) → Save History → Return
```

## Assumptions

- Backend only — no frontend/operator changes
- In-cluster auth via ServiceAccount (no per-user credentials)
- Product is READ-ONLY
- Single LLM call summarizes K8sGPT findings + KB articles

## Implemented Design

### 1. Simplified `backend/api/chat.py`

Removed from the chat path:
- `InputSanitizer` validation
- Credential validation (`session_id`)
- Cluster selection validation (`cluster_name`)
- `ResponseParser` parsing

Replaced with:
- In-cluster K8s client (singleton via `k8s_client.py`)
- Direct pass-through to `AgentEngine`

### 2. Created `backend/k8s_client.py`

Singleton in-cluster K8s client:
- `config.load_incluster_config()` on first access
- Falls back to `kubeconfig` for local development
- Exposes `core_v1`, `apps_v1`, `networking_v1`, `custom_objects` APIs

### 3. Simplified `backend/agentic_engine.py`

Replaced the multi-iteration tool-calling loop with a single LLM call:
- System prompt includes K8sGPT findings and KB article summaries
- No tool definitions passed to the LLM
- Response is a direct text summary with fix recommendations

### 4. Removed dead modules

Deleted (and their tests):
- `backend/enrichment_engine.py` — cluster context enrichment
- `backend/query_router.py` — query classification
- `backend/template_engine.py` — prompt template rendering
- `backend/k8s_tools.py` — K8s API tool definitions (unused after engine simplification)

### 5. Cleaned up `backend/rag_integration.py`

- Removed `process_query()` method (was the old RAG pipeline entry point)
- Removed `_format_cluster_context()` and `_format_k8sgpt_errors()` (dead code)
- Removed template engine initialization
- Kept `search_knowledge_base()` for KB article retrieval

## Acceptance Criteria

- [x] `POST /api/chat/query` works with just `query` + `user_id` (no session_id/cluster_name required)
- [x] No `InputSanitizer` or `ResponseParser` in the chat path
- [x] In-cluster K8s client used throughout (no user credentials)
- [x] Single LLM call with K8sGPT + KB context
- [x] Existing tests updated to match new flow
- [x] Dead code removed (enrichment_engine, query_router, template_engine, k8s_tools)

## Future Work

- Re-add K8s tool-calling loop if deeper investigation is needed
- Add input validation for obviously malicious queries (defense in depth)
- Add `max_tokens` passthrough from `ChatRequest` to LLM call
