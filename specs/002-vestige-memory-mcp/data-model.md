# Data Model: Cluster-Local Agent Memory (Vestige MCP)

**Feature**: `002-vestige-memory-mcp`  
**Date**: 2026-07-25

Logical model as seen by the chatbot. Physical storage is owned by Vestige (SQLite + indexes under `VESTIGE_DATA_DIR`); we do not reimplement tables.

## Entities

### MemoryRecord (logical)

Institutional troubleshooting knowledge stored via Vestige ingest.

| Field | Type | Description |
|-------|------|-------------|
| id | string | Vestige memory id (opaque) |
| content | string | Natural-language durable fact/episode |
| created_at | datetime | When stored (if returned by status/graph APIs) |
| tags / metadata | map | Cluster name, severity, resource kinds, session id (prefix only) |
| salience | number | Optional; managed by Vestige lifecycle |
| status | enum | active, suppressed, superseded (as reported by Vestige) |

**Validation (before ingest)**:

- `content` non-empty after strip; max length e.g. 8–16k chars.
- Must pass scrubber (no raw secrets).
- Must pass durability policy (not greeting-only / not pure error noise).

### RecallHit

| Field | Type | Description |
|-------|------|-------------|
| id | string | Memory id |
| content | string | Snippet/full text returned by `recall` |
| score | number | Optional relevance |
| reason | string | Optional (e.g. contradiction, backfill link) |

### ChatTurnSnapshot

Built after a successful `/api/chat/query` for policy + ingest.

| Field | Type | Description |
|-------|------|-------------|
| user_query | string | Original query |
| assistant_response | string | Final response text |
| cluster_name | string? | Selected cluster if known |
| k8sgpt_summary | string? | Truncated findings |
| tool_evidence_summary | string? | Optional compact tool outcomes |
| conversation_id | string | For correlation (not secret) |
| user_id | string | **Conversation history only** — do **not** use for Vestige recall/ingest filters (memory is shared across users per cluster) |

### MemoryServiceHealth

| Field | Type | Description |
|-------|------|-------------|
| ready | bool | Process up + tools/list OK |
| degraded | bool | Last operation failed / timeout |
| detail | string | Safe error message |
| backend | string | `vestige` \| `noop` |

### LegacySolution (phase 2 import only)

Maps old FAISS/KB solution files → one MemoryRecord content blob.

| Field | Description |
|-------|-------------|
| title, description, tags, steps | Concatenated into ingest content |
| source | `legacy-faiss-import` |

## Relationships

```text
ChatTurnSnapshot --(policy)--> optional MemoryRecord (via smart_ingest)
Chat query --(recall)--> 0..N RecallHit --> injected into AgentEngine context
MemoryRecord --(Vestige graph)--> related MemoryRecords (internal to Vestige)
```

## State transitions (product-level)

| State | Trigger |
|-------|---------|
| no memory | Fresh PVC |
| primed | Successful recall (even if empty list) |
| degraded | MCP timeout/crash; chat continues |
| ingested | smart_ingest accepted |
| rejected_ingest | scrub fail, policy fail, or contradiction needing agent resolution (log + optional surface) |

## Durability policy (when to auto-save)

**Save when all hold**:

1. HTTP chat completed without hard 5xx from agent.  
2. Assistant response length above minimum (e.g. >200 chars) **or** contains structured remediation signals.  
3. Query not in deny list (e.g. `ping`, `hello`, pure auth errors).  
4. Scrubber passes.

**Do not save**:

- Rate-limited / unauthorized responses.  
- Empty/error-only agent failures.  
- Content that looks like raw kubeconfig or cloud keys after scrub attempt.

## Scoping

MVP: **shared team memory** per deployment namespace (one Vestige data dir).  
Memory is **institutional** — all users on the chatbot share findings for a cluster (like a shared ops runbook), not private per-user memory.

- Metadata **MUST** prefer `cluster=<name>` for recall/ingest filtering when known.  
- Metadata **MUST NOT** filter recall by `user_id` (do not partition institutional findings by who first asked).  
- Hard multi-tenant user isolation of memory is **out of scope**.  
- Chat **conversation history** remains per-user path on disk; that is separate from Vestige memory.
