# CLAUDE.md

# DevOps Context

## Stack
K8s/EKS, Helm, ArgoCD, Python, AWS, Vault, Kyverno

## Standards
- Python: PEP 8, type hints, black/ruff
- YAML: 2-space, limits/requests, security contexts
- Helm: values.yaml for config, semver

## Security
- Vault for secrets (never hardcode)
- Kyverno enforcement
- runAsNonRoot, readOnlyRootFilesystem

## Response Style
- Brief answers only
- Show diffs, not full files
- Skip explaining: K8s basics, Python syntax, Git/ArgoCD workflows
- Verbose only for: security impacts, breaking changes, complex Helm logic

## Project Overview

DevOps Chatbot v2.0 is a Kubernetes-native troubleshooting assistant using Kion AWS credentials (and/or kubeconfig) for authentication, K8sGPT Operator for diagnostics, FAISS RAG for the knowledge base, and an agentic FastAPI chat backend. Delivery is **Argo CD app-of-apps + Helm** (`argocd/`, `helm/`). Flux is retired.

**Key Architecture**: Decoupled diagnostics (K8sGPT) from the UI/API monolith. Optional single-cluster pin via `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME`. Session: HttpOnly cookie + `X-Session-Id`. Mutations require human approval in chat.

**Agent rules:** see root [AGENTS.md](AGENTS.md). **Docs index:** [docs/README.md](docs/README.md). **Baseline tag:** `faiss-202607`.

## Build and Development Commands

### Backend Development

```bash
# Setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install shared libraries in editable mode (REQUIRED for development)
pip install -e ../libs/devops-k8s
pip install -e ../libs/devops-kb
pip install -e ../libs/devops-rag

# Run backend
uvicorn app:app --reload --port 8000

# Test commands
pytest                                    # All tests
pytest --cov=. --cov-report=html         # With coverage
pytest -k "property"                     # Property-based tests only
pytest tests/test_credential_store.py    # Single test file
pytest tests/test_agentic_engine.py  # Single test file
```

### Frontend Development

```bash
# Setup
cd frontend
npm install

# Run frontend (auto-proxies /api to localhost:8000)
npm start

# Test commands
npm test                                        # All tests (interactive watch)
npm test -- --coverage                          # With coverage
npm test -- src/components/LoginForm.test.tsx  # Single test file
npm test -- --no-watch                          # CI mode (single run)
```

### Docker Build

```bash
# Multi-stage production build
DOCKER_BUILDKIT=1 docker build -t devops-chatbot:v2.0 .

# Build frontend only (stage 1)
docker build --target frontend-builder -t frontend-build .

# Build backend only (stage 2)
docker build --target backend-builder -t backend-build .
```

### Kubernetes Deployment (GitOps preferred)

```bash
# Secrets out-of-band
kubectl create namespace devops-chatbot --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openrouter \
  --from-literal=llm-model=mistralai/devstral-2512 \
  -n devops-chatbot

# Argo CD bootstrap (once)
kubectl apply -n argocd -f argocd/projects/bookish-octo-robot.yaml
kubectl apply -n argocd -f argocd/bootstrap/root-app.yaml

# Verify
kubectl get applications -n argocd
kubectl get pods -n devops-chatbot
```

See docs/argocd-gitops.md and docs/deployment.md. Raw `k8s/` manifests are legacy/reference.

## Critical Architecture Patterns

### 1. Kion-Based Authentication Flow

The system uses **Kion temporary AWS credentials** (ASIA* access keys) instead of OIDC. This single credential source grants both Kubernetes and AWS API access:

1. User submits Kion credentials (access key, secret key, session token, region) → `POST /api/credentials/aws`
2. Backend validates via STS GetCallerIdentity → `backend/eks_auth.py:validate_credentials()`
3. Optional target-cluster access check when `IN_CLUSTER_EKS_CLUSTER_NAME` / `EKS_CLUSTER_NAME` is set
4. Credentials stored in-memory with 3600s TTL → `backend/credential_store.py:CredentialStore`
5. Session id returned in JSON and set as HttpOnly cookie `session_id` (header `X-Session-Id` still accepted)
6. For each K8s API call, backend generates EKS bearer token → `backend/eks_auth.py:get_eks_bearer_token()`
7. Bearer token format: `k8s-aws-v1.{base64_presigned_url}` (60s expiration, regenerated per request)

**IMPORTANT**: `CredentialStore` is in-memory and not distributed-safe. With `replicas: 2` in deployment.yaml, credentials stored in Pod A won't be accessible from Pod B. Solutions: implement Redis-backed store, use sticky sessions, or reduce to single replica.

### 2. Query Processing Pipeline

User queries flow through an agentic pipeline:

```
User Query
  ↓
Rate Limiter (20 req/min per user) → backend/middleware/rate_limiter.py
  ↓
K8s Client (in-cluster) → backend/k8s_client.py
  ↓
K8sGPTReader (read Result CRDs) → backend/k8sgpt_reader.py
  ↓
RAGEngine (initial KB search, top-5) → libs/devops-rag/
  ↓
AgentEngine (bounded tool-calling loop) → backend/agentic_engine.py
  ├─ System prompt (editable) → backend/prompts/system.md
  ├─ Tool specs + dispatch → backend/agent_tools.py
  └─ Skill discovery → backend/skills.py / backend/skills/<name>/SKILL.md
  ↓
LLMClient (generate response) → libs/devops-rag/src/devops_rag/llm_client.py
```

**Key principle**: The agent loop is bounded by hard stop conditions (no_progress, dedupe_loop, blocked_loop, context_budget_exhausted). Tools fail gracefully — each returns an error dict rather than raising, allowing the loop to continue with partial data. Input validation is delegated to the LLM system prompt and RBAC.

### 3. Shared Libraries Architecture

Three reusable libraries in `libs/` installed via editable mode (`pip install -e`):

- **devops-k8s**: Kubernetes client wrappers, health monitoring, event correlation
- **devops-kb**: Knowledge base storage on PVC, solution CRUD, snapshot management
- **devops-rag**: RAG engine with FAISS, LLM client abstraction (OpenAI/Anthropic/Ollama), embeddings

When modifying libraries: changes are immediately reflected in backend (editable install). No reinstall needed unless changing `pyproject.toml`.

### 4. K8sGPT Integration Pattern

K8sGPT runs **in each monitored cluster** (not in chatbot deployment) and produces Result CRDs:

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: pod-nginx-crashloop-abc123
  namespace: default
spec:
  kind: Pod
  name: nginx
  error: CrashLoopBackOff
  details: "Container exited with code 1"
```

Chatbot reads these CRDs via CustomObjectsApi using per-user bearer tokens. Results drive:
- Weather widget calculation (severity → Sunny/Cloudy/Stormy)
- Query enrichment (auto-include relevant findings)
- Chat responses (prominently highlight K8sGPT insights)

### 5. Agentic Tool-Calling Loop

`AgentEngine.run()` runs a bounded tool-calling loop with hard stop conditions:

```python
# Stop conditions — do not remove or relax without human review
MAX_NO_PROGRESS_ROUNDS = 2    # no new evidence produced
MAX_DEDUP_ONLY_ROUNDS = 2     # only duplicate tool calls
MAX_BLOCKED_ONLY_ROUNDS = 2   # only approval-required calls
MAX_CONTEXT_TOKENS = 12000    # context budget exhausted
```

Tool calls execute in parallel (up to `MAX_PARALLEL_TOOL_CALLS = 3`). A dedupe cache keyed on `tool_name:sorted_args_json` prevents redundant API calls within a single request. When context approaches the token budget, older tool results are compacted into an `EVIDENCE_SUMMARY` block (`_enforce_message_budget`).

### 6. Multi-Cluster State Management

Each cluster has isolated state:
- **Conversation history**: Stored at `/data/conversations/{user_id}/{cluster_name}/`
- **K8s clients**: Regenerated per cluster switch
- **Cached data**: Cleared on cluster switch

When user switches clusters via `POST /api/clusters/select`:
1. Generate new EKS bearer token for new cluster
2. Create new K8s API clients
3. Switch conversation history path
4. Clear weather cache

## Testing Strategy

### Property-Based Tests (Hypothesis/fast-check)

Used for universal correctness properties across all inputs. Located in files with `property` in test names.

**Example**: `test_credential_storage_round_trip` validates that `store(session_id, creds)` followed by `get(session_id)` returns equivalent credentials for ANY generated credentials.

Run property tests: `pytest -k "property"` (backend) or filter by test name (frontend).

### Unit Tests

Test specific scenarios, edge cases, error conditions. Cover:
- Specific credential formats (AWS AKIA vs ASIA patterns)
- Edge cases (empty KB, no K8sGPT results, expired credentials)
- Error conditions (RBAC 403, API timeouts, invalid inputs)

### Integration/E2E Tests

Located in `backend/test_e2e_integration.py` and similar. Test complete workflows:
- Login → cluster discovery → selection → query → response
- Credential expiration → re-auth flow
- Solution submission → KB retrieval

## Environment Variables

Required for backend startup (validated by `startup_validator.py`):

```bash
# Required
LLM_API_KEY=sk-...           # OpenAI/Anthropic/OpenRouter key
DEFAULT_REGION=us-east-1     # AWS region for Kion credentials

# Optional (with defaults)
LLM_PROVIDER=openai          # openai | anthropic | ollama
LLM_MODEL=gpt-4o-mini        # Cost-efficient model
KB_SEEDING_ENABLED=true      # Auto-seed KB on startup
```

**CRITICAL SECURITY**: Never commit `.env` file. It should be in `.gitignore` and contain only local development credentials. Production uses Kubernetes Secrets (`k8s/secrets.yaml`).

## Common Patterns and Conventions

### Error Handling

All API endpoints follow this pattern:

```python
try:
    # Operation
    result = await some_operation()
    return result
except HTTPException:
    raise  # Re-raise FastAPI exceptions
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise handle_generic_error(e, "operation context", "User-friendly message")
```

The `handle_generic_error()` (from `utils/error_handler.py`) logs with stack trace and returns HTTPException with sanitized message.

### Async K8s API Calls

Kubernetes client is synchronous, so use `asyncio.to_thread()` for non-blocking:

```python
async def get_pods(namespace: str):
    pods = await asyncio.to_thread(
        core_v1.list_namespaced_pod,
        namespace=namespace
    )
    return pods
```

### Credential Retrieval in Endpoints

Use dependency injection pattern:

```python
from api.credentials import get_credentials_for_session

@router.get("/example")
async def example(session_id: str = Depends(get_session_id)):
    creds = get_credentials_for_session(session_id)  # Raises 401 if missing/expired
    # Use creds...
```

## File Organization by Concern

**Authentication/Authorization**:
- `backend/credential_store.py` - In-memory credential storage
- `backend/eks_auth.py` - STS validation, EKS token generation
- `backend/api/credentials.py` - Auth endpoints
- `backend/middleware/auth_middleware.py` - Session validation

**Cluster Operations**:
- `backend/cluster_manager.py` - Cluster discovery, K8s client factory
- `backend/api/clusters.py` - Cluster endpoints
- `backend/k8sgpt_reader.py` - Read K8sGPT Result CRDs
- `backend/weather_calculator.py` - Health state calculation

**Query Processing / Agentic Loop**:
- `backend/agentic_engine.py` - Bounded tool-calling loop, context compaction
- `backend/agent_tools.py` - Tool specs (OpenAI function format) and dispatch; `AgentContext` dataclass
- `backend/skills.py` - Skill discovery from `backend/skills/<name>/SKILL.md`
- `backend/prompts/system.md` - Editable system prompt (override via `SYSTEM_PROMPT_PATH` env var)

**LLM Integration**:
- `backend/rag_integration.py` - LLM client + KB init, reads config from env vars
- `libs/devops-rag/src/devops_rag/rag_engine.py` - Core RAG logic
- `libs/devops-rag/src/devops_rag/llm_client.py` - LLM provider abstraction (OpenAI/Anthropic/Ollama)

**Knowledge Base**:
- `backend/solution_manager.py` - Solution CRUD
- `libs/devops-kb/` - KB storage library
- `backend/conversation_history.py` - Chat history management

**Observability**:
- `backend/utils/error_handler.py` - Error logging, AWS/LLM call logging
- `backend/utils/metrics.py` - Prometheus metrics
- `backend/startup_validator.py` - Startup health checks

**Frontend Architecture**:
- `frontend/src/components/` - React components (LoginForm, ClusterSelector, ChatInterface, WeatherWidget, etc.)
- `frontend/src/hooks/` - Custom hooks (useCredentials, useCluster, useChat, useWeather)
- `frontend/src/types/` - TypeScript type definitions
- `frontend/src/utils/` - Utilities (API client, validators)

## Known Issues and Limitations

1. **Distributed Deployment Issue**: CredentialStore is in-memory. Running 2+ replicas causes authentication failures when requests land on different pods. Use Redis or enforce single replica.

2. **Missing Rate Limiting**: Rate limiter exists in `backend/middleware/rate_limiter.py` and is wired into the chat endpoint (20 req/min), but is not applied to other endpoints.

3. **PVC Access Mode**: `k8s/pvc.yaml` defaults to ReadWriteOnce. For 2+ replicas, need ReadWriteMany and compatible storage class.

4. **CORS Configured for All Origins**: `app.py` has `allow_origins=["*"]`. Restrict to specific domains for production.

5. **Input Validation Delegated to LLM**: `input_sanitizer.py` was removed. Input validation now relies on the system prompt guardrails and Kubernetes RBAC. The LLM is instructed not to execute destructive operations without explicit approval, but there is no hard-coded pattern matching at the HTTP layer.

## Session Status (2026-05-03)

### Civo Cluster
- **Cluster**: `bookish-octo-robot` (k3s, 2 nodes, NYC1) — ACTIVE and healthy
- **To refresh kubeconfig**: `civo kubernetes config bookish-octo-robot > kubeconfig.yaml`
- **Cluster upgrade available**: k3s v1.35.0-k3s1 (currently on v1.34.2-k3s1)

### Branch: `improve-api-docs-error-handling`
Major refactor pending merge:
- Decomposed monolithic agentic engine into `agentic_engine.py` / `agent_tools.py` / `skills.py`
- System prompt externalized to `backend/prompts/system.md`
- Removed `input_sanitizer.py`, `response_parser.py`, `enrichment_engine.py`, `template_engine.py`, `query_router.py`, and `libs/devops-prompts/`
- RBAC error handling improved: catches `kubernetes.client.exceptions.ApiException` with `e.status == 403`
- Resource limits added to all Alloy/Prometheus/Grafana components
- Prometheus retention reduced from 15d to 2d (Civo storage constraint)

## Reference Documentation

- **Architecture**: `docs/architecture.md` - System design overview
- **Design Document**: `.kiro/specs/devops-chatbot-v2/design.md` - Detailed technical design with 50 correctness properties
- **Requirements**: `.kiro/specs/devops-chatbot-v2/requirements.md` - 17 functional requirements with acceptance criteria
- **Implementation Plan**: `.kiro/specs/devops-chatbot-v2/tasks.md` - Task breakdown (39 completed tasks)
- **Security**: `docs/security.md` - Security features and best practices
- **Development**: `docs/development.md` - Local setup instructions

## API Endpoint Reference

**Authentication**: POST/GET/DELETE `/api/credentials/aws`
**Clusters**: GET `/api/clusters`, POST `/api/clusters/select`
**Chat**: POST `/api/chat`, GET `/api/chat/history`, POST `/api/chat/export`
**Weather**: GET `/api/weather`, GET `/api/weather/details`
**Results**: GET `/api/results`, GET `/api/results/{id}`
**Solutions**: POST `/api/solutions`, GET `/api/solutions`, GET `/api/kb/search`
**Health**: GET `/api/health` (liveness), GET `/api/health/ready` (readiness)
**API Docs**: http://localhost:8000/api/docs (Swagger UI)

## Active Technologies
- Python 3.11+ (backend), TypeScript/React (frontend), Vestige MCP binary (Rust, prebuilt linux/x64) + FastAPI, existing `AgentEngine`/`agent_tools`, MCP Python client (`mcp` SDK or equivalent stdio JSON-RPC client), Vestige (`vestige-mcp` / `vestige-mcp-server`) (002-vestige-memory-mcp)
- Vestige SQLite (+ embeddings cache) on Kubernetes PVC (`/data/vestige`); no FAISS index; no external vector SaaS (002-vestige-memory-mcp)

## Recent Changes
- 002-vestige-memory-mcp: Added Python 3.11+ (backend), TypeScript/React (frontend), Vestige MCP binary (Rust, prebuilt linux/x64) + FastAPI, existing `AgentEngine`/`agent_tools`, MCP Python client (`mcp` SDK or equivalent stdio JSON-RPC client), Vestige (`vestige-mcp` / `vestige-mcp-server`)
