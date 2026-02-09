# DevOps Chatbot v2.0 - Design Review & Docker-Desktop Deployment

## Design Review Summary

### ✅ Strengths

| Area | Assessment |
|------|------------|
| **Architecture** | Well-decoupled design - K8sGPT diagnostics separate from chatbot UI. Clear separation of concerns with API, middleware, utils, and test directories |
| **Code Organization** | Backend follows modular structure with dedicated packages for auth, cluster operations, query processing, RAG integration, and observability |
| **Shared Libraries** | Excellent pattern with `libs/` containing reusable components (devops-k8s, devops-kb, devops-prompts, devops-rag) |
| **Type Safety** | TypeScript frontend with dedicated type definitions; Python backend uses type hints and Pydantic models |
| **Testing** | Comprehensive strategy with unit, integration, E2E, and property-based tests (Hypothesis) |
| **Docker Optimization** | Multi-stage build achieving <500MB target with proper layer caching and cleanup |
| **Security** | Non-root user, read-only filesystem compatibility, Kyverno policies, security headers in nginx |
| **Documentation** | Excellent CLAUDE.md, architecture docs, and development guides |

### ⚠️ Areas for Improvement

| Issue | Severity | Location | Recommendation |
|-------|----------|----------|----------------|
| **In-Memory Credentials** | High | `backend/credential_store.py` | Not distributed-safe. Use Redis-backed store or single replica |
| **Missing Rate Limiting** | Medium | `backend/app.py` | Design specifies rate limiting but not implemented |
| **Async Timeout Not Enforced** | Medium | `backend/enrichment_engine.py` | `timeout = 10` set but never used |
| **CORS All Origins** | Medium | `backend/app.py` | `allow_origins=["*"]` - restrict for production |
| **AWS Credential Validation** | Low | `backend/input_sanitizer.py` | Only accepts AKIA* (permanent), not ASIA* (temporary) |
| **PVC Access Mode** | Low | `k8s/pvc.yaml` | ReadWriteOnce - incompatible with multi-replica |

### 🔧 Maintenance Observations

1. **Dependencies**: Python packages use pinned versions with `==` for reproducibility
2. **Error Handling**: Centralized error handler in `backend/utils/error_handler.py`
3. **Observability**: Prometheus metrics endpoint, structured logging, startup validation
4. **API Documentation**: FastAPI auto-generates Swagger docs at `/api/docs`

---

## Docker-Desktop / Podman Local Deployment

### Option 1: Docker Compose (Docker or Podman)

#### Docker
```bash
# Build and start
docker-compose up --build

# Access at http://localhost:8080
```

#### Podman
```bash
# Using podman-compose
podman-compose up --build

# Or using docker-compose with Podman backend
COMPOSE_DOCKER_CLI_BUILD=1 docker-compose up --build
```

### Option 2: Kubernetes (Podman Desktop or kubectl)

#### Podman Desktop
1. Install **Kubernetes** extension in Podman Desktop
2. Settings → Kubernetes → Enable Kubernetes
3. Deploy using the generated manifest:
   ```bash
   kubectl apply -f kubernetes-podman.yaml
   ```

#### Direct kubectl
```bash
# Update LLM_API_KEY in kubernetes-podman.yaml
kubectl apply -f kubernetes-podman.yaml

# Port forward to access
kubectl port-forward -n devops-chatbot svc/devops-chatbot 8080:80
```

#### Generate from Container
```bash
# Build image first
podman build -t devops-chatbot:latest .

# Generate K8s manifest
podman generate kube devops-chatbot > my-manifest.yaml

# Deploy
kubectl apply -f my-manifest.yaml
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_API_KEY` | Yes | OpenAI/Anthropic/OpenRouter API key |
| `DEFAULT_REGION` | Yes | AWS region (e.g., `us-east-1`) |
| `LLM_PROVIDER` | No | `openai` (default), `anthropic`, `ollama` |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `KB_SEEDING_ENABLED` | No | Auto-seed knowledge base (default: `true`) |

### Architecture

```
┌─────────────────────────────────────────────────┐
│ Docker Desktop / Podman Desktop / K8s Context   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ devops-chatbot (container/pod)         │   │
│  │  ┌─────────┐  ┌─────────────────────┐   │   │
│  │  │ nginx   │  │ uvicorn (FastAPI)   │   │   │
│  │  │ :80     │  │ :8000               │   │   │
│  │  └────┬────┘  └─────────────────────┘   │   │
│  │       │                                 │   │
│  │  ┌────┴─────────────────────────────┐   │   │
│  │  │ Shared Volume (/data)            │   │   │
│  │  │ - Knowledge Base                 │   │   │
│  │  │ - FAISS Index                    │   │   │
│  │  │ - Conversation History           │   │   │
│  │  └──────────────────────────────────┘   │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  External Dependencies:                         │
│  - LLM Provider (OpenAI/Anthropic/Ollama)      │
│  - EKS Clusters (via kubeconfig)               │
│  - K8sGPT Operator (per cluster)               │
└─────────────────────────────────────────────────┘
```

### Ports

| Port | Service | Description |
|------|---------|-------------|
| 8080 | nginx | Frontend + API reverse proxy |
| 8000 | uvicorn | Backend (internal) |

### Volume Mounts

| Mount | Purpose |
|-------|---------|
| `./data:/data` | Knowledge base, FAISS index, conversation history |

### Health Checks

- **Endpoint**: `http://localhost:8080/api/health`
- **Interval**: 30s
- **Timeout**: 3s
- **Retries**: 3
- **Start Period**: 40s

### Troubleshooting

```bash
# Docker/Podman Compose logs
docker-compose logs -f
podman-compose logs -f

# Kubernetes logs
kubectl logs -n devops-chatbot -l app=devops-chatbot -f

# Restart services
docker-compose restart
kubectl rollout restart deployment/devops-chatbot -n devops-chatbot

# Rebuild after dependency changes
docker-compose up --build --force-recreate
kubectl rollout restart deployment/devops-chatbot -n devops-chatbot
```

### Production vs Local

| Feature | Docker/Podman Compose | Kubernetes |
|---------|----------------------|------------|
| Replicas | 1 | 2+ (configurable) |
| Credentials | In-memory | Redis (recommended) |
| Storage | hostPath volume | ReadWriteMany PVC |
| Logging | stdout/stderr | Centralized (Loki/ELK) |
| Secrets | env vars | Kubernetes Secrets |

### Files

| File | Purpose |
|------|---------|
| `docker-compose.yaml` | Container orchestration (Docker/Podman) |
| `kubernetes-podman.yaml` | Kubernetes manifests (kubectl/Podman Desktop) |
| `.env.example` | Environment variables template |
| `data/` | Volume mount directory |
