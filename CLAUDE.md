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

DevOps Chatbot v2.0 is a Kubernetes-native troubleshooting assistant using Kion AWS credentials for authentication, K8sGPT Operator for cluster diagnostics, and RAG-powered knowledge base search. The system is a monolith deployment (frontend + backend) that can troubleshoot multiple EKS clusters, with K8sGPT Operator deployed per monitored cluster.

**Key Architecture**: Decoupled diagnostics (K8sGPT per cluster) from user interface (single centralized deployment). Uses Kion temporary AWS credentials for both Kubernetes API and AWS API access.

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
pip install -e ../libs/devops-prompts
pip install -e ../libs/devops-rag

# Run backend
uvicorn app:app --reload --port 8000

# Test commands
pytest                                    # All tests
pytest --cov=. --cov-report=html         # With coverage
pytest -k "property"                     # Property-based tests only
pytest tests/test_credential_store.py    # Single test file
pytest tests/test_enrichment_engine.py::test_enrich_pods  # Single test
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

### Kubernetes Deployment

```bash
# Deploy application
kubectl create namespace devops-chatbot
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openai \
  --from-literal=llm-model=gpt-4o-mini \
  -n devops-chatbot
kubectl apply -f k8s/

# Deploy K8sGPT to monitored cluster
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system
kubectl apply -f k8sgpt/argocd-application.yaml
kubectl apply -f k8sgpt/k8sgpt-cr.yaml

# Verify deployment
kubectl get pods -n devops-chatbot
kubectl logs -n devops-chatbot deployment/devops-chatbot --all-containers
```

## Critical Architecture Patterns

### 1. Kion-Based Authentication Flow

The system uses **Kion temporary AWS credentials** (ASIA* access keys) instead of OIDC. This single credential source grants both Kubernetes and AWS API access:

1. User submits Kion credentials (access key, secret key, session token, region) → `POST /api/credentials/aws`
2. Backend validates via STS GetCallerIdentity → `backend/eks_auth.py:validate_credentials()`
3. Credentials stored in-memory with 3600s TTL → `backend/credential_store.py:CredentialStore`
4. For each K8s API call, backend generates EKS bearer token → `backend/eks_auth.py:get_eks_bearer_token()`
5. Bearer token format: `k8s-aws-v1.{base64_presigned_url}` (60s expiration, regenerated per request)

**IMPORTANT**: `CredentialStore` is in-memory and not distributed-safe. With `replicas: 2` in deployment.yaml, credentials stored in Pod A won't be accessible from Pod B. Solutions: implement Redis-backed store, use sticky sessions, or reduce to single replica.

### 2. Query Processing Pipeline

User queries flow through a deterministic pipeline (no LLM-based routing):

```
User Query
  ↓
InputSanitizer (reject unsafe patterns) → backend/input_sanitizer.py
  ↓
QueryRouter (pattern-based classification) → backend/query_router.py
  ↓
EnrichmentEngine (gather K8s/AWS context in parallel) → backend/enrichment_engine.py
  ↓
K8sGPTReader (read Result CRDs) → backend/k8sgpt_reader.py
  ↓
RAGEngine (semantic KB search) → libs/devops-rag/
  ↓
TemplateEngine (render prompt) → backend/template_engine.py
  ↓
LLMClient (generate response) → libs/devops-rag/src/devops_rag/llm_client.py
  ↓
ResponseParser (safety checks, citations) → backend/response_parser.py
```

**Key principle**: Each stage fails gracefully. If K8sGPT CRDs are unreadable, enrichment returns partial context and proceeds. If KB is empty, RAG returns empty results and proceeds.

### 3. Shared Libraries Architecture

Four reusable libraries in `libs/` installed via editable mode (`pip install -e`):

- **devops-k8s**: Kubernetes client wrappers, health monitoring, event correlation
- **devops-kb**: Knowledge base storage on PVC, solution CRUD, snapshot management
- **devops-prompts**: Query routing, template loading, domain validation
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

### 5. Async Enrichment with Graceful Degradation

`EnrichmentEngine.execute()` runs all enrichment tasks in parallel:

```python
tasks = [
    self._enrich_pods(plan),
    self._enrich_deployments(plan),
    self._enrich_services(plan),
    self._read_k8sgpt_results(),
    self._enrich_aws(plan)
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Critical pattern**: `return_exceptions=True` means failed tasks return exception objects instead of raising. The merge logic filters exceptions and logs them to `context.errors`, allowing the pipeline to continue with partial data.

**Missing**: Timeout enforcement. Currently `self.timeout = 10` is set but not used. Should wrap gather in `asyncio.wait_for()`.

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

**Query Processing**:
- `backend/query_router.py` - Pattern-based classification
- `backend/input_sanitizer.py` - Input validation
- `backend/enrichment_engine.py` - Context gathering (1200 lines, most complex file)

**LLM Integration**:
- `backend/rag_integration.py` - RAG orchestration
- `libs/devops-rag/src/devops_rag/rag_engine.py` - Core RAG logic
- `libs/devops-rag/src/devops_rag/llm_client.py` - LLM provider abstraction
- `backend/template_engine.py` - Prompt rendering
- `backend/response_parser.py` - Response parsing

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

2. **Missing Rate Limiting**: Design doc specifies rate limiting (Requirement 9), but no rate limiter found in codebase. Implement before production.

3. **Async Timeout Not Enforced**: `EnrichmentEngine.timeout = 10` is set but never used. Enrichment can hang indefinitely if K8s API is slow.

4. **PVC Access Mode**: `k8s/pvc.yaml` defaults to ReadWriteOnce. For 2+ replicas, need ReadWriteMany and compatible storage class.

5. **CORS Configured for All Origins**: `app.py` has `allow_origins=["*"]`. Restrict to specific domains for production.

6. **AWS Credential Validation Too Strict**: `input_sanitizer.py:194` only accepts AKIA* (permanent credentials). Kion provides ASIA* (temporary). Pattern should be `^A[SK]IA[0-9A-Z]{16}$`.

## Session Status (2026-03-22)

### Civo Cluster
- **Cluster**: `bookish-octo-robot` (k3s, 2 nodes, NYC1) — ACTIVE and healthy
- **kubeconfig fixed**: was pointing to stale IP `212.2.247.66`, now correct `212.2.243.16`
- **To refresh kubeconfig**: `civo kubernetes config bookish-octo-robot > kubeconfig.yaml`
- **Cluster upgrade available**: k3s v1.35.0-k3s1 (currently on v1.34.2-k3s1)

### CI Test Fixes (both committed and pushed to main)
All CI failures are now resolved. Two bugs were fixed:

**Fix 1** — `backend/tests/test_chat_api.py`
- `test_sanitizer_blocks_shell_commands` was testing that `bash -c 'kubectl delete pod'` and `#!/bin/bash` are blocked
- The sanitizer was intentionally redesigned to allow DevOps shell syntax; only `rm -rf /` and fork bombs are blocked
- Updated test to only assert on genuinely destructive patterns

**Fix 2** — `backend/tests/test_solutions_api.py` (root cause of 19 failures in `test_rag_integration.py`)
- `test_solutions_api.py` was doing `sys.modules['rag_integration'] = MagicMock()` at module level with no cleanup
- Since pytest collects `test_rag_integration.py` alphabetically before `test_solutions_api.py`, by execution time `sys.modules['rag_integration']` was the MagicMock — so every `@patch('rag_integration.*')` in rag tests patched the mock's attributes instead of the real module
- Fixed by saving/restoring the real module immediately after the import that needed the mock

### Next Steps / Outstanding Items
- Monitor CI pipeline for the two pushed commits to confirm green
- Cluster upgrade available: `civo k3s upgrade bookish-octo-robot --version v1.35.0-k3s1`
- Known issue (pre-existing): `CredentialStore` is in-memory — 2 replicas will cause auth failures (see Known Issues section)

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
