# Architecture

DevOps Chatbot v2.0 uses a decoupled architecture that separates cluster diagnostics from the user-facing application.

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│  Target EKS Clusters (Dev, Staging, Prod)          │
│   ├── K8sGPT Operator (per cluster)                 │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing)                             │
└──────────────┬──────────────────────────────────────┘
               │ K8s API + AWS API
               │ (user's Kion STS credentials)
               │
┌──────────────┴──────────────────────────────────────┐
│  Common/Management Cluster                          │
│                                                     │
│  ┌─ DevOps Chatbot Deployment ───────────────────┐ │
│  │  Frontend (React + nginx)                      │ │
│  │  Backend (FastAPI)                             │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ Shared PVC (/data) ───────────────────────────┐ │
│  │  Knowledge Base, FAISS Index, Solutions        │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
               │
               ▼
        LLM Provider (OpenAI/Anthropic/Ollama)
```

## Key Components

### Frontend (React + TypeScript)
- Single-page application with React 18
- TypeScript for type safety
- Custom hooks for state management
- Real-time health monitoring via weather widget
- Multi-cluster support with cluster selector
- Credential management with validation

### Backend (FastAPI + Python)
- RESTful API with FastAPI
- Async request handling with uvloop
- Credential management with TTL-based expiration
- EKS token generation for cluster access
- Query classification and routing
- Context enrichment engine
- RAG integration for knowledge base search
- K8sGPT Result CRD reading
- Conversation history per cluster
- Solution management

### Shared Libraries
- **devops-k8s**: Kubernetes API utilities
- **devops-kb**: Knowledge base management
- **devops-prompts**: Prompt templates
- **devops-rag**: RAG engine with FAISS

### K8sGPT Operator
- Deployed per monitored cluster
- Continuous cluster analysis
- Produces Result CRDs
- Configurable analyzers and filters
- Optional webhook integration

## Data Flow

### Authentication Flow
1. User enters Kion AWS credentials
2. Backend validates via STS GetCallerIdentity
3. Credentials stored in-memory with 3600s TTL
4. Session token returned to frontend

### Cluster Selection Flow
1. User selects cluster from dropdown
2. Backend generates EKS bearer token
3. Kubernetes API client configured
4. Cluster-specific conversation history loaded

### Health Monitoring Flow
1. Frontend polls weather endpoint every 60s
2. Backend reads K8sGPT Result CRDs
3. Weather calculator determines health status
4. Top issues returned to frontend
5. Weather widget displays status

### Chat Flow
1. User submits query
2. Query router classifies intent
3. Enrichment engine gathers context:
   - K8sGPT Result CRDs
   - Kubernetes API calls
   - AWS API calls
   - Knowledge base search
4. Template engine builds prompt
5. LLM generates response
6. Response parser extracts structured data
7. Response returned to frontend
8. Conversation history updated

### Solution Saving Flow
1. User clicks "Save to KB" on message
2. Frontend shows solution form
3. User fills in metadata
4. Backend saves to knowledge base
5. FAISS index updated
6. Solution immediately available for search

## Security Architecture

### Authentication
- Kion AWS credentials (temporary)
- STS validation
- In-memory storage with TTL

### Authorization
- Kubernetes RBAC
- Namespace-scoped permissions
- Least privilege access

### Network Security
- Network policies for pod-to-pod traffic
- Ingress rules for frontend/backend
- Egress rules for external APIs

### Container Security
- Non-root user (UID 1000)
- Read-only root filesystem
- No capabilities
- Seccomp and AppArmor profiles

## Scalability Considerations

### Horizontal Scaling
- Frontend: Stateless, can scale horizontally
- Backend: Stateless (except in-memory credentials), can scale horizontally
- Knowledge Base: Shared PVC, requires ReadWriteMany access mode

### Performance Optimization
- LLM response caching
- Conversation history limits
- Cost-efficient models (gpt-4o-mini)
- Targeted context enrichment
- FAISS for fast semantic search

### Resource Limits
- Frontend: 256Mi memory, 200m CPU
- Backend: 512Mi memory, 500m CPU
- Shared PVC: 10Gi storage

## High Availability

### Application HA
- Multiple replicas for frontend and backend
- Health checks and readiness probes
- Rolling updates with zero downtime

### Data HA
- Shared PVC with ReadWriteMany
- Regular backups recommended
- Disaster recovery procedures

### Dependency HA
- LLM provider fallback (optional)
- Graceful degradation without KB
- Continue operation if K8sGPT unavailable

## Monitoring and Observability

### Metrics
- Prometheus metrics endpoint
- Request latency and error rates
- LLM token usage
- Cache hit rates

### Logging
- Structured JSON logging
- Configurable log levels
- Request/response logging
- Error tracking

### Tracing
- Request ID propagation
- Distributed tracing support (optional)
- Performance profiling

## Cost Optimization

### LLM Costs
- Use cost-efficient models
- Response caching
- Conversation history limits
- Targeted context enrichment

### Infrastructure Costs
- Right-sized resource requests
- Horizontal pod autoscaling
- Spot instances for non-critical workloads

### Storage Costs
- Efficient FAISS indexing
- Conversation history pruning
- Knowledge base deduplication

## Future Enhancements

### Planned Features
- Multi-tenancy support
- Advanced RBAC integration
- Custom analyzer plugins
- Real-time collaboration
- Mobile app

### Integration Opportunities
- Slack/Teams notifications
- PagerDuty integration
- Jira ticket creation
- GitHub issue linking
- Grafana dashboards

## References

- [Design Document](../devops-chatbot-v2-design.md)
- [Architecture Document](../devops-chatbot-v2-architecture.md)
- [K8sGPT Documentation](https://docs.k8sgpt.ai/)
