# Deployment Guide

This guide covers deploying DevOps Chatbot v2.0 to Kubernetes clusters.

## Docker Image

The application uses an optimized multi-stage Docker build:
- **Target Size:** <500MB (~365MB actual)
- **Build Time:** ~4 minutes with BuildKit
- **Performance:** uvloop + httptools for 2-4x faster request handling

### Build the Image

```bash
# Standard build
docker build -t devops-chatbot:v2.0 .

# With BuildKit (recommended - faster)
DOCKER_BUILDKIT=1 docker build -t devops-chatbot:v2.0 .

# Verify size
docker images devops-chatbot:v2.0
```

For detailed optimization information, see [Docker Build Optimization](../docker/BUILD_OPTIMIZATION.md).

## Kubernetes Deployment

### 1. Create Namespace

```bash
kubectl create namespace devops-chatbot
```

### 2. Create Secrets

```bash
# Create secret with LLM configuration
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  --from-literal=llm-provider=openai \
  --from-literal=llm-model=gpt-4o-mini \
  -n devops-chatbot

# Or apply the secrets.yaml after editing
# Edit k8s/secrets.yaml with your values first
kubectl apply -f k8s/secrets.yaml
```

### 3. Deploy Application

```bash
# Apply all manifests
kubectl apply -f k8s/

# Verify deployment
kubectl get pods -n devops-chatbot
kubectl get svc -n devops-chatbot
```

### 4. Access the Application

```bash
# Port forward for local access
kubectl port-forward -n devops-chatbot svc/devops-chatbot 30080:30080

# Access at http://localhost:30080
```

For production deployment with ingress, see [k8s/ingress.yaml](../k8s/ingress.yaml).

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for LLM provider | `sk-...` |
| `DEFAULT_REGION` | Default AWS region | `us-east-1` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider (openai, anthropic, ollama) | `openai` |
| `LLM_MODEL` | Model to use | `gpt-4o-mini` |
| `KB_SEEDING_ENABLED` | Enable knowledge base seeding on startup | `true` |
| `KB_FORCE_RESEED` | Force re-seeding even if KB exists | `false` |
| `AI_API_BASE` | Custom API endpoint (for OpenRouter, Ollama) | - |
| `DEBUG` | Enable debug logging | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `PORT` | Backend port | `8000` |
| `CORS_ORIGINS` | CORS allowed origins | `*` |

See [.env](../.env) for a complete example.

## Pre-Deployment Checklist

Before deploying to production, ensure you've completed the [Security Checklist](security.md#pre-deployment-checklist).

## Troubleshooting

### Credential Issues

**Problem**: "Invalid credentials" error

**Solution**:
1. Verify Kion credentials are current (not expired)
2. Check AWS region is correct
3. Ensure credentials have EKS and STS permissions

### Cluster Discovery Fails

**Problem**: No clusters appear in dropdown

**Solution**:
1. Verify credentials have `eks:ListClusters` permission
2. Check DEFAULT_REGION matches cluster region
3. Review backend logs for API errors

### K8sGPT Results Not Showing

**Problem**: Weather widget shows "No data"

**Solution**:
1. Verify K8sGPT Operator is deployed to target cluster
2. Check Result CRDs exist: `kubectl get results -A`
3. Verify credentials have permission to read CRDs
4. Check backend logs for RBAC errors

### Knowledge Base Not Working

**Problem**: No KB results in chat responses

**Solution**:
1. Verify PVC is mounted at `/data`
2. Check KB seeding completed: Look for "KB seeding complete" in logs
3. Verify FAISS index exists: `ls /data/faiss_index`
4. Enable KB seeding: Set `KB_SEEDING_ENABLED=true`

### High LLM Costs

**Problem**: Unexpected API costs

**Solution**:
1. Use cost-efficient models: `gpt-4o-mini`, `claude-3-haiku`
2. Enable caching (already implemented)
3. Reduce conversation history limit
4. Monitor token usage in logs
