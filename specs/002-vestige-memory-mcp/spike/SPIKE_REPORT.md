# Vestige Spike Report — Fit for DevOps Chatbot

**Date**: 2026-07-25  
**Version tested**: `vestige-mcp-server@2.2.1` (Windows x86_64 prebuilt)  
**Branch**: `002-vestige-memory-mcp`  
**Data dir**: `specs/002-vestige-memory-mcp/spike/data/`

## Goal

Prove Vestige is fit for purpose as the cluster-local MCP memory backend replacing FAISS for automatic troubleshooting recall/save.

## Environment

| Item | Value |
|------|--------|
| OS | Windows 11 (dev spike) |
| Install | `npm install vestige-mcp-server@latest` + postinstall binary download |
| Model cache | `FASTEMBED_CACHE_PATH=./model-cache` (~523 MB after first consolidate) |
| DB | `VESTIGE_DATA_DIR=./data` → `vestige.db` |
| HTTP MCP | `vestige serve --port 3928` → `http://127.0.0.1:3928/mcp` |

## Tests performed

### 1. Install & health

| Check | Result |
|-------|--------|
| Binary install | **Pass** — `vestige.exe` + `vestige-mcp.exe` |
| Empty health | **Pass** — Status EMPTY, 0 memories |
| First ingest without embeddings | **Pass** — stores with “Embeddings not available, falling back to regular ingest” |
| `vestige consolidate` | **Pass** — generated embeddings (1 then 7+ nodes); ~15s first, ~1s later |
| Embedding ready (long-running serve) | **Pass** — `memory_status.embeddingReady: true` |

### 2. DevOps scenario seeding + CLI recall

Seeded 7–9 institutional ops memories (CrashLoopBackOff+ConfigMap, HPA decision, Ingress 404, OOM/FAISS, LLM secret decision, PVC Pending, prod read-only SA, failure event).

| Query | Top recommendation | Fit |
|-------|-------------------|-----|
| crash looping / missing config | nginx CrashLoopBackOff + ConfigMap / `:latest` | **Pass** (correct) |
| ingress 404 | Traefik path prefix / `/chatbot` | **Pass** (correct) |
| OOM / FAISS | OOMKilled FAISS memory limit | **Pass** (correct) |

CLI `recall` returned synthesis + evidence with confidence 85–98%.

### 3. Backfill vs pure similarity (`backfill --contrast`)

| Observation | Result |
|-------------|--------|
| Similarity top hits for failure text | Lookalikes (e.g. OOM, PVC) — **not** the causal decision |
| Postdict / backfill | Surfaces other “decision” memories via tag/graph joins |
| Quality caveat | With same-day `ops` tags, backfill can promote **weakly related** decisions (e.g. OpenRouter model) as “causes” |

**Fit**: Feature is real and useful for demos; for production chatbot, treat `backfill` as **optional tool**, not automatic sole truth. Prefer structured metadata (cluster, app, resource) when ingesting.

### 4. HTTP MCP (critical for Kubernetes)

| Step | Result |
|------|--------|
| `POST /mcp` initialize | **Pass** — serverInfo vestige 2.2.1 |
| Session | Requires `mcp-session-id` response header on subsequent calls |
| Protocol | Requires `MCP-Protocol-Version: 2024-11-05` on follow-ups |
| Auth | Bearer token from `auth_token` file (path under `%APPDATA%\vestige\...` when using default auth path) |
| `tools/list` | **Pass** — 13 tools: `recall`, `smart_ingest`, `session_start`, `backfill`, `memory_status`, … |
| `tools/call` recall | **Pass** — hybrid+cognitive, top hit merged CrashLoop memories, semanticScore ~0.85 |
| `tools/call` smart_ingest | **Pass** — `decision: create`, `hasEmbedding: true`, success |
| Near-duplicate ingest | **Pass** — `decision: reinforce` (similarity ~0.97), not noisy duplicate |

**Implication for plan**: Prefer **separate Deployment + HTTP MCP** over co-located stdio subprocess. Aligns with multi-container GitOps and health probes. Update plan topology accordingly.

### 5. Contradiction / “pin digest” vs “always latest”

Ingesting “always use `:latest`” when pin-digest advice already exists returned **`reinforce`** of a prior similar “latest” memory, not a hard `claim_contradicts_memory` against pin-digest.

**Fit**: Dedup/reinforce works; **explicit contradiction detection is not guaranteed** for all opposite ops decisions unless phrased/stored as linked claims. Still better than FAISS append-only for near-duplicates.

## Fit scorecard (vs product needs)

| Requirement | Score | Notes |
|-------------|-------|--------|
| Better than FAISS similarity | **Strong** | Hybrid recall, merge, reinforce, optional backfill |
| Auto save / recall | **Strong** | Tools + CLI; chatbot must call them deterministically |
| Local / cluster storage | **Strong** | SQLite on disk; PVC maps cleanly |
| MCP model | **Strong** | stdio **and** HTTP serve |
| Remove Save-to-KB | **N/A product** | Spike confirms no dependency on FAISS APIs |
| K8s packaging | **Good** | HTTP mode unlocks Service + Deployment; bake model cache |
| Multi-replica writers | **Weak** | Still single SQLite writer — keep 1 replica memory service |
| Air-gap | **Medium** | Model cache ~500MB must be baked/pre-seeded |
| AGPL | **Policy** | Confirmed AGPL-3.0-only package license |
| Secret safety | **Not tested** | Still need scrubber in chatbot before ingest |

## Issues / risks found

1. **One-shot CLI** often lacks live embedding service → always run consolidate or use long-lived `serve`/`vestige-mcp` for production-quality gating.  
2. **HTTP client must send** `Authorization`, `mcp-session-id`, `MCP-Protocol-Version`.  
3. **Auth token file location** may not live under `--data-dir` (observed under `%APPDATA%\vestige\core\data\auth_token`) — configure `VESTIGE_AUTH_TOKEN` explicitly in K8s.  
4. **Backfill noise** if all memories share coarse tags — ingest schema must include cluster/app/resource.  
5. **Model cache size** (~0.5 GB) impacts image/PVC.  
6. **Process lifecycle**: `serve` exited when started via some Start-Process patterns; use proper supervisor (K8s restartPolicy).

## Go / No-Go

### **GO — Vestige is fit for purpose** for this refactor

With these implementation constraints:

1. Deploy Vestige as **HTTP MCP service** (`vestige serve`) + PVC + single replica.  
2. Chatbot uses **MCP client** with session + protocol headers (not FAISS).  
3. **Deterministic** pre-turn `recall` / `session_start` and post-turn `smart_ingest` (do not rely only on model tool choice).  
4. **Bake** embedding model cache into image or init container.  
5. Set **`VESTIGE_AUTH_TOKEN`** (and data dir) via Secret/env — do not scrape desktop paths.  
6. Keep **live K8s API authoritative**; memory is supporting context.  
7. Accept **AGPL** process boundary + **single-writer** topology.

## Recommended plan deltas

| Plan item | Change from spike |
|-----------|-------------------|
| Topology | Prefer **HTTP MCP Deployment** over stdio co-process |
| Client | Implement HTTP MCP session client (initialize → session id → tools/call) |
| Health | Probe `memory_status` or TCP `:3928` + readiness after embed ready |
| Ingest schema | Always include `cluster:`, problem/diagnosis/remediation fields |

## Artifacts in this folder

| Path | Purpose |
|------|---------|
| `node_modules/vestige-mcp-server` | Installed package (do not commit) |
| `data/vestige.db` | Spike DB (do not commit) |
| `model-cache/` | Embedding cache (do not commit) |
| `results/*.json` | MCP response samples |
| `SPIKE_REPORT.md` | This report |

## Reproduce quickly

```powershell
cd specs/002-vestige-memory-mcp/spike
npm install vestige-mcp-server@latest
node node_modules/vestige-mcp-server/scripts/postinstall.js
$env:FASTEMBED_CACHE_PATH = "$PWD\model-cache"
$v = ".\node_modules\vestige-mcp-server\bin\vestige.exe"
& $v --data-dir "$PWD\data" health
& $v --data-dir "$PWD\data" ingest "cluster: demo. problem: test"
& $v --data-dir "$PWD\data" consolidate
& $v --data-dir "$PWD\data" recall "test problem"
& $v --data-dir "$PWD\data" serve --port 3928
```
