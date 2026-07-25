# Contract: Vestige MCP tools used by chatbot

**Server**: `vestige-mcp` (stdio)  
**Reference**: https://github.com/samvallad33/vestige  

MVP maps a subset of the 13 tools:

| Vestige tool | MemoryPort method | When used |
|--------------|-------------------|-----------|
| `session_start` | `session_start` | Start of chat request (optional combine with recall) |
| `recall` | `recall` | Pre-turn prime; optional in-loop tool |
| `smart_ingest` | `ingest` | Post-turn auto-save |
| `backfill` | `backfill` | Optional agent tool when diagnosing “why did this break” |
| `memory_status` | `health` | Readiness / diagnostics |

Other tools (`graph`, `maintain`, `dedup`, `suppress`, `codebase`, `intention`, `source_sync`, `memory`) are **out of MVP** unless needed for ops scripts.

## Process env

| Env | Purpose |
|-----|---------|
| `VESTIGE_DATA_DIR` | PVC path, e.g. `/data/vestige` |
| `VESTIGE_BIN` | Path to binary if not on PATH |
| `MEMORY_BACKEND` | `vestige` \| `noop` |
| `MEMORY_RECALL_TIMEOUT_MS` | Default 2000 |
| `MEMORY_INGEST_TIMEOUT_MS` | Default 5000 |

## Lifecycle

1. On app startup (or first use): spawn `vestige-mcp` with stdio pipes.  
2. MCP initialize + `tools/list` once.  
3. Reuse session for all chat requests (serialize tool calls with a lock).  
4. On crash: restart process; mark degraded until healthy.  
5. On shutdown: terminate child cleanly.

## Ingest content template (suggested)

```text
cluster: {cluster_name}
problem: {user_query}
diagnosis: {summary_from_response}
remediation: {remediation_bullets}
verification: {verification_if_any}
source: devops-chatbot-auto
```

## Transport

stdio only for MVP. No assumption of remote HTTP MCP.
