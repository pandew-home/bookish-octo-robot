# Quickstart: Vestige memory (dev + cluster)

**Feature**: `002-vestige-memory-mcp`

## Local development

### Prerequisites

- Python venv for backend (existing project setup)
- Node not required for Vestige if you install the binary via npm once:
  ```bash
  npm install -g vestige-mcp-server@latest
  which vestige-mcp
  ```
- Or download prebuilt `vestige-mcp` for your OS from upstream releases.

### Run backend with Vestige

```bash
cd backend
source venv/bin/activate   # Windows: venv\Scripts\activate

export MEMORY_BACKEND=vestige
export VESTIGE_DATA_DIR="$PWD/../.local/vestige-data"
export VESTIGE_BIN=vestige-mcp   # or full path
mkdir -p "$VESTIGE_DATA_DIR"

# First run may download embedding model (~130MB) — needs network once
uvicorn app:app --reload --port 8000
```

Degraded mode (no Vestige):

```bash
export MEMORY_BACKEND=noop
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm start
```

Confirm: no Save-to-KB dialog in chat UI.

### Smoke test (local)

1. Authenticate (kubeconfig or mock as you usually do).  
2. Ask a durable troubleshooting question; complete an answer.  
3. Ask a related question in a new conversation; expect prior lesson influence.  
4. Stop `vestige-mcp` (kill child) and confirm chat still answers with `memory_degraded`.

### Tests

```bash
cd backend
pytest tests/test_memory_port.py tests/test_memory_policy.py tests/test_chat_memory_degraded.py -q
```

## Cluster (outline)

1. PVC for `/data/vestige` (can share existing data PVC with subPath).  
2. Image includes `vestige-mcp` + baked embedding model (preferred).  
3. Env on chatbot Deployment:
   - `MEMORY_BACKEND=vestige`
   - `VESTIGE_DATA_DIR=/data/vestige`
   - `VESTIGE_BIN=/usr/local/bin/vestige-mcp`
4. `replicaCount: 1`  
5. Argo CD sync; check logs for MCP initialize success.  
6. Functional chat smoke against ingress.

### Backup

Backup the PVC directory (SQLite + model cache). Restore by replacing volume contents while pod stopped.

### Air-gap

Build pipeline step: run Vestige once online to populate model cache, copy into image or init container Config/emptyDir seed.

## Related

- [plan.md](./plan.md)  
- [contracts/memory-port.md](./contracts/memory-port.md)  
- [contracts/vestige-mcp-tools.md](./contracts/vestige-mcp-tools.md)  
