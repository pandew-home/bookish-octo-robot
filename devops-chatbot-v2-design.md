# DevOps Chatbot v2 — Design & Architecture

## Overview

The DevOps Chatbot is a Kubernetes-native assistant for DevOps engineers, providing real-time cluster health monitoring, RAG-powered troubleshooting chat, and a shared team knowledge base. v2 is a fresh implementation that decouples cluster diagnostics (K8sGPT Operator, per-cluster) from the user-facing application (React + FastAPI, deployed once in a common management cluster).

Users authenticate via Kion temporary AWS credentials, which grant both full Kubernetes API and AWS API access to their authorized EKS clusters. The K8sGPT Operator runs independently in each target cluster, continuously producing diagnostic Result CRDs. The chatbot reads those results and enriches them with targeted K8s API calls driven by a deterministic query router — no MCP protocol, no agent tool-calling, no LLM-driven API decisions.

### Core Capabilities

- Real-time cluster health ("weather") derived from K8sGPT Result CRDs
- RAG-powered chat for troubleshooting with semantic search over a shared knowledge base
- Deterministic query routing with targeted K8s/AWS API enrichment
- Safety, validation, and RBAC checks to prevent destructive actions
- Cost optimization via caching, small models, and context window management
- ArgoCD-aware recommendations via in-cluster CRD reads
- AWS/EKS context enrichment via direct boto3 calls (minimized, on-demand only)
- Multi-cluster support via cluster selector with per-user Kion credentials

### Key Design Changes from v1

| Concern | v1 | v2 |
|---|---|---|
| Cluster diagnostics | K8sGPT MCP server pod per cluster | K8sGPT Operator per cluster (CRD-based) |
| MCP protocol | Required for K8sGPT and AWS integration | Eliminated entirely |
| AWS context | Separate AWS MCP server pod | Direct boto3 calls with user's Kion creds (on-demand) |
| Authentication | OIDC flow + JWT + Kion credential exchange | Kion temp AWS creds only (STS → EKS bearer token) |
| Deployment model | Multi-pod Helm chart per cluster | Operator per cluster + single app deployment in common cluster |
| Frontend/Backend | In-cluster with nginx/supervisor, per-cluster | Single Deployment in common cluster, serves all clusters |
| Inter-service networking | MCP pods, network policies, circuit breakers | None — operator is independent, app reads CRDs remotely |
| Knowledge base | Per-cluster, isolated | Shared PVC, team-wide |
| Multi-cluster | Separate deployments per cluster | One app, cluster selector dropdown |
| ArgoCD integration | Via MCP or direct API | Read ArgoCD Application CRDs via K8s API |

---

## Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────┐
│  EKS Cluster: Dev                                   │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing, read via K8s CRD API)      │
├─────────────────────────────────────────────────────┤
│  EKS Cluster: Staging                               │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing, read via K8s CRD API)      │
├─────────────────────────────────────────────────────┤
│  EKS Cluster: Prod                                  │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing, read via K8s CRD API)      │
└──────────────┬──────────────────────────────────────┘
               │ K8s API + AWS API
               │ (user's Kion STS creds per-session)
               │
┌──────────────┴──────────────────────────────────────┐
│  Common/Management Cluster — DevOps Chatbot App     │
│                                                     │
│  ┌─ Single Deployment ────────────────────────────┐ │
│  │  React Frontend (nginx)                        │ │
│  │   ├── Login: Kion AWS credential fields        │ │
│  │   ├── Cluster selector dropdown                │ │
│  │   ├── Credential status badge + TTL countdown  │ │
│  │   ├── Weather widget (selected cluster)        │ │
│  │   ├── Chat interface with citations            │ │
│  │   ├── Solution submission dialog               │ │
│  │   └── Safety warning banners + confirmation    │ │
│  │                                                │ │
│  │  FastAPI Backend                               │ │
│  │   ├── Credential Store (per-user, in-memory)   │ │
│  │   ├── EKS Token Generator (STS → bearer)       │ │
│  │   ├── Cluster Discovery (EKS ListClusters)     │ │
│  │   ├── Query Router (deterministic)             │ │
│  │   ├── Enrichment Engine (targeted K8s/AWS)     │ │
│  │   ├── RAG Engine (FAISS + embeddings)          │ │
│  │   ├── Prompt Template Engine                   │ │
│  │   ├── Input Sanitizer                          │ │
│  │   ├── Rate Limiter                             │ │
│  │   ├── Conversation History Manager             │ │
│  │   ├── KB Seeder                                │ │
│  │   ├── Startup Validator                        │ │
│  │   └── LLM Client                              │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ PVC (/data) ─────────────────────────────────┐ │
│  │  /data/kb/           → Knowledge base (shared) │ │
│  │  /data/embeddings/   → FAISS index + cache     │ │
│  │  /data/solutions/    → User-submitted solutions│ │
│  │  /data/conversations/→ Per-user chat history   │ │
│  │  /data/templates/    → Custom prompt templates │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
               │
               ▼
        LLM Provider (Anthropic / OpenAI / Ollama)
```

### Request Flow

**Login & Cluster Selection:**
1. User opens chatbot UI → Login screen with Kion credential fields
2. Frontend POSTs creds to `POST /api/credentials/aws`
3. Backend validates via STS GetCallerIdentity, stores with TTL
4. Backend discovers clusters via EKS ListClusters
5. Frontend shows cluster dropdown, user selects target cluster
6. UI loads weather widget + chat for selected cluster

**Chat Query Flow:**
1. User submits query through React UI
2. Backend validates input (sanitizer rejects code execution attempts)
3. Backend checks rate limits
4. Query Router classifies query → builds EnrichmentPlan
5. Enrichment Engine reads K8sGPT Result CRDs from target cluster
6. Enrichment Engine makes targeted K8s API calls based on plan (pods, logs, events, ArgoCD apps, etc.)
7. If plan includes AWS context: boto3 calls for EKS/node group info (rare)
8. RAG Engine retrieves top-k KB matches via FAISS
9. Prompt Template Engine renders structured prompt with all context
10. LLM generates response with diagnosis, evidence, fix recommendations
11. Response returned with citations, safety notices, K8sGPT findings summary
12. Conversation saved to history

**Weather/Health Flow:**
1. Frontend polls `GET /api/weather` every 60 seconds for selected cluster
2. Backend reads K8sGPT Result CRDs + lightweight K8s API calls (node count, pod summary)
3. Calculates weather state (Sunny → Stormy) from result severity/count
4. Returns top issues, cluster info, tool versions
5. Frontend preserves previous data during refresh (no flicker)

---

## Authentication & Credential Flow

### Kion Credential Exchange

Kion provides temporary AWS STS credentials (access key, secret key, session token). These credentials authenticate to both AWS APIs (via boto3) and the Kubernetes API (via EKS bearer token generation).

```python
@dataclass
class StoredCredentials:
    access_key: str
    secret_key: str
    session_token: str
    region: str
    user_arn: str
    account_id: str
    expires_at: datetime
    created_at: datetime

class CredentialStore:
    """Thread-safe in-memory credential store with TTL-based expiration."""
    def __init__(self):
        self._store: dict[str, StoredCredentials] = {}
        self._lock = threading.Lock()

    def store(self, session_id: str, creds: StoredCredentials):
        with self._lock:
            self._store[session_id] = creds

    def get(self, session_id: str) -> Optional[StoredCredentials]:
        with self._lock:
            creds = self._store.get(session_id)
            if creds and creds.expires_at > datetime.utcnow():
                return creds
            elif creds:
                del self._store[session_id]
            return None

    def cleanup_expired(self):
        with self._lock:
            now = datetime.utcnow()
            expired = [k for k, v in self._store.items() if v.expires_at <= now]
            for k in expired:
                del self._store[k]
```

### EKS Bearer Token Generation

```python
def get_eks_bearer_token(creds: StoredCredentials, cluster_name: str) -> str:
    """Generate K8s bearer token from STS creds (equivalent to aws eks get-token)."""
    session = boto3.Session(
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.session_token,
        region_name=creds.region
    )
    sts = session.client('sts', region_name=creds.region)
    service_id = sts.meta.service_model.service_id
    signer = RequestSigner(service_id, creds.region, 'sts', 'v4',
                           session.get_credentials(), session.events)
    params = {
        'method': 'GET',
        'url': f'https://sts.{creds.region}.amazonaws.com/'
               f'?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }
    signed_url = signer.generate_presigned_url(
        params, region_name=creds.region, expires_in=60, operation_name='')
    return 'k8s-aws-v1.' + base64.urlsafe_b64encode(
        signed_url.encode('utf-8')).decode('utf-8').rstrip('=')
```

### Cluster Discovery

```python
async def discover_clusters(creds: StoredCredentials) -> list[dict]:
    session = boto3.Session(
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.session_token,
        region_name=creds.region
    )
    eks = session.client('eks')
    cluster_names = eks.list_clusters()['clusters']
    clusters = []
    for name in cluster_names:
        try:
            info = eks.describe_cluster(name=name)['cluster']
            clusters.append({
                'name': name, 'endpoint': info['endpoint'],
                'version': info['version'], 'status': info['status'],
                'region': creds.region,
                'ca_data': info['certificateAuthority']['data'],
            })
        except Exception:
            pass
    return clusters
```

### K8s Client Factory

```python
def get_k8s_clients(creds: StoredCredentials, cluster: dict) -> dict:
    token = get_eks_bearer_token(creds, cluster['name'])
    config = client.Configuration()
    config.host = cluster['endpoint']
    config.api_key = {"authorization": f"Bearer {token}"}
    ca_data = base64.b64decode(cluster['ca_data'])
    ca_file = tempfile.NamedTemporaryFile(delete=False, suffix='.crt')
    ca_file.write(ca_data)
    ca_file.close()
    config.ssl_ca_cert = ca_file.name
    api_client = client.ApiClient(config)
    return {
        'core': client.CoreV1Api(api_client),
        'apps': client.AppsV1Api(api_client),
        'custom': client.CustomObjectsApi(api_client),
        'networking': client.NetworkingV1Api(api_client),
        'rbac': client.RbacAuthorizationV1Api(api_client),
    }
```

### Credential Status (Reused from v1)

| State | Color | Condition |
|---|---|---|
| No credentials | Gray | No Kion creds submitted |
| Active | Green | Valid creds, >10 min remaining |
| Expiring soon | Orange | Valid creds, <10 min remaining |
| Expired | Red | Creds past TTL |

Frontend polls `GET /api/credentials/aws/status` every 30s. `useCredentialStatus` hook provides per-second countdown.

### Graceful Degradation

When credentials expire: K8sGPT Results and KB/RAG answers remain available if a fallback service account exists. Live cluster deep dives unavailable. UI shows status change, prompts re-authentication. Chat adapts: "I can see K8sGPT detected an issue, but I need fresh credentials to pull logs."

---

## K8sGPT Operator (Per-Cluster)

### Deployment via ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: k8sgpt-operator
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://charts.k8sgpt.ai/
    chart: k8sgpt-operator
    targetRevision: "*"
  destination:
    server: https://kubernetes.default.svc
    namespace: k8sgpt-operator-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### K8sGPT Custom Resource

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: K8sGPT
metadata:
  name: k8sgpt-cluster
  namespace: k8sgpt-operator-system
spec:
  ai:
    enabled: true
    model: gpt-4o-mini
    backend: amazonbedrock    # or openai — use IRSA for Bedrock
    secret:
      name: k8sgpt-ai-secret
      key: api-key
  noCache: false
  repository: ghcr.io/k8sgpt-ai/k8sgpt
  version: v0.4.1
```

### Operator RBAC (Read-Only)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k8sgpt-reader
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "nodes", "namespaces", "events",
                "configmaps", "persistentvolumeclaims", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["core.k8sgpt.ai"]
    resources: ["results", "k8sgpts"]
    verbs: ["*"]
```

### Reading Results

```python
def get_k8sgpt_results(k8s_clients: dict) -> list[dict]:
    results = k8s_clients['custom'].list_namespaced_custom_object(
        group="core.k8sgpt.ai", version="v1alpha1",
        namespace="k8sgpt-operator-system", plural="results")
    return results.get('items', [])
```

---

## Backend Components

### Query Router

Deterministic pattern matching — no LLM involved in routing.

```python
class QueryCategory(Enum):
    POD_ISSUE = "pod_issue"
    DEPLOYMENT_STATUS = "deployment_status"
    SERVICE_NETWORKING = "service_networking"
    NODE_HEALTH = "node_health"
    STORAGE = "storage"
    ARGOCD = "argocd"
    SECURITY = "security"
    GENERAL_HEALTH = "general_health"
    KB_SEARCH = "kb_search"

@dataclass
class EnrichmentPlan:
    categories: list[QueryCategory] = field(default_factory=list)
    resource_names: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    include_k8sgpt_results: bool = True
    include_aws_context: bool = False
    time_range: Optional[timedelta] = None
```

**Query Type Keywords** (carried forward from v1 template system):

| Category | Keywords |
|---|---|
| Pod Issue | "not working", "broken", "failing", "crashloop", "oom", "pending", "evicted", "imagepullbackoff", "backoff", "restart", "terminated", "killed", "unhealthy" |
| Deployment | "deployment", "rollout", "helm", "chart", "values", "image tag", "replicas", "scaling", "hpa", "rollback", "canary", "blue-green" |
| Service/Networking | "network", "dns", "coredns", "connectivity", "timeout", "ingress", "service mesh", "load balancer", "502", "503", "504", "endpoint", "cilium", "calico" |
| Node Health | "node", "notready", "capacity", "drain", "cordon", "taint", "kubelet" |
| Storage | "pvc", "volume", "storage", "persistent", "disk", "mount", "storageclass" |
| ArgoCD | "argocd", "sync", "out of sync", "degraded", "prune", "auto-sync", "gitops", "flux" |
| Security | "rbac", "policy", "kyverno", "vault", "secret", "permission", "serviceaccount", "certificate", "tls", "iam" |
| General | Fallback when no keywords match |

**Priority** (when multiple match): Networking → Deployment → ArgoCD → Pod Issue → Security → Storage → Node Health → General

**Time Range Detection**: "last hour" → 1h, "past 6 hours" → 6h, "today" → 24h, "recently" → 6h, "just now" → 1h

### Enrichment Engine

Executes targeted K8s API and optional AWS calls based on query classification.

```python
class EnrichmentEngine:
    async def execute(self, plan, k8s, aws_creds=None) -> dict:
        context = {}
        if plan.include_k8sgpt_results:
            context['k8sgpt_results'] = get_k8sgpt_results(k8s)
        for category in plan.categories:
            if category == QueryCategory.POD_ISSUE:
                context['pods'] = await self._enrich_pods(k8s, plan)
            elif category == QueryCategory.DEPLOYMENT_STATUS:
                context['deployments'] = await self._enrich_deployments(k8s, plan)
            elif category == QueryCategory.SERVICE_NETWORKING:
                context['services'] = await self._enrich_services(k8s, plan)
            elif category == QueryCategory.NODE_HEALTH:
                context['nodes'] = await self._enrich_nodes(k8s)
            elif category == QueryCategory.STORAGE:
                context['storage'] = await self._enrich_storage(k8s, plan)
            elif category == QueryCategory.ARGOCD:
                context['argo_apps'] = await self._enrich_argocd(k8s, plan)
            elif category == QueryCategory.SECURITY:
                context['security'] = await self._enrich_security(k8s, plan)
            elif category == QueryCategory.GENERAL_HEALTH:
                context['health'] = await self._enrich_general_health(k8s)
        if plan.include_aws_context and aws_creds:
            context['aws'] = await self._enrich_aws(aws_creds)
        return context
```

RBAC errors handled gracefully — 403 responses return "Permission denied" detail rather than crashing.

### Prompt Template System (Carried Forward from v1)

Templates structure context into LLM prompts. They define reasoning rules and output format.

**Base Template:**
```yaml
system: |
  You are a Kubernetes troubleshooting assistant for EKS clusters.
  Rules:
  - Explain root cause before suggesting fixes.
  - Reference K8sGPT findings when relevant.
  - Include Safety Notices for destructive/irreversible recommendations.
  - Cite knowledge base sources when used.
  - Suggest ArgoCD-based fixes (sync, rollback) when applicable.
  - Never fabricate resource names, events, or log entries.
  - Evaluate all recommendations for destructiveness.
  Output format:
  1. Assessment (2-3 sentences)
  2. Evidence (data points from cluster context)
  3. Recommended Fix (step-by-step, prefer IaC/GitOps)
  4. Safety Notice (if applicable)
  5. Verification (commands to confirm fix)
  6. Related KB Articles (if any)
```

**Template Types** (all from v1): Troubleshooting, Analysis, Deployment, GitOps, Security, Networking, General — each with specialized rules, constraints, and output formats. Customizable via ConfigMap. Hot-reloadable.

### Input Sanitizer (Reused from v1)

Blocks: shebang, shell commands (bash, kubectl, docker, helm), code execution functions (eval, exec, system, subprocess), command substitution, module imports, Dockerfile commands. Allows conversational queries. Returns helpful rephrase suggestions. Frontend mirrors patterns for immediate feedback.

### RAG Engine (Reused from v1)

FAISS vector store, sentence-transformers embeddings, top 3-5 retrieval, embedding cache on PVC. Optional response cache for repeated queries.

### Knowledge Base (Reused from v1, Shared PVC)

- **Foundation Patterns (Tier 1)**: Auto-generated troubleshooting frameworks
- **Solutions (Tier 2)**: User-submitted fixes with problem, steps, tags, runbook URL, automation script, fix time estimate, usage/success tracking
- **Cluster Snapshots**: Resource states, events, metrics
- **Vector Index**: FAISS across all content
- **Query Analytics**: Recurring issue detection

KB Seeding on first startup: idempotent, error-tolerant, controlled by `KB_SEEDING_ENABLED` / `KB_FORCE_RESEED`.

### Cost Controls (Reused from v1)

Embedding cache, response cache, gpt-4o-mini for K8sGPT scanning, configurable chat model, context window limits (top 3-5 KB results), conversation summarization every 7 messages, optional Ollama, token/cost tracking.

### Conversation History (Reused from v1)

Per-user at `/data/conversations/{user_id}/`, max 10 conversations, auto-summarize every 7 messages, export as markdown, save to KB as solution.

### Rate Limiter (Reused from v1)

10 req/min for chat, 5 req/min for solutions, 30 req/min default. Dev 10x lenient, prod 2x strict. Rate limit headers on all responses.

### Startup Validator (Adapted)

**Critical**: LLM_API_KEY, DEFAULT_REGION. **Optional**: KB_SEEDING_ENABLED, custom templates. **Removed**: OIDC, JWT_SECRET, AWS_MCP_SERVER_URL.

---

## Safety & Validation (Carried Forward from v1)

### AI Response Safety

- Templates require LLM to evaluate recommendations for destructiveness
- Safety Notice section in output format
- Frontend `detectDestructiveResponse()` parses for destructive keywords
- Warning banners with affected resources, safer alternatives
- Non-blocking — user can proceed

### RBAC Verification

Uses SelfSubjectAccessReview with user's Kion creds. Returns `{ allowed, reason }`. Integrated into future Phase 2 apply-fix flow.

### Destructive Action Confirmation (Phase 2)

Cluster banner, affected resource chips, action description, safer alternatives via async chat, RBAC check before Apply button, CloudTrail audit trail.

---

## Frontend

### Tech Stack (from v1)

React 18+, MUI v5+, TypeScript, Axios, dark mode default.

### Theming by Cluster Environment

```typescript
const themes = {
  dev:     { primary: '#64B5F6', secondary: '#81C784' },
  staging: { primary: '#FFB74D', secondary: '#FFD54F' },
  prod:    { primary: '#81C784', secondary: '#A5D6A7' },
};
```

### Login Screen

```
┌──────────────────────────────────────────┐
│          DevOps Chatbot Login            │
│  AWS Access Key ID:     [____________]   │
│  AWS Secret Access Key: [____________]   │
│  Session Token:         [____________]   │
│  Region:                [us-east-1  ▼]   │
│              [ Connect ]                 │
│  ℹ Get credentials from Kion console    │
└──────────────────────────────────────────┘
```

### Main Interface

```
┌──────────────────────────────────────────────────────┐
│  DevOps Chatbot    [eks-prod ▼]    🟢 Creds: 47m    │
├──────────────────────────────────────────────────────┤
│  ☀️ Sunny — 2 minor issues                          │
│  ├── Pod: logger-5f4 — ImagePullBackOff             │
│  │   [View Pods] [Check Events] [Ask About This]   │
│  └── PVC: data-vol-3 — Pending                      │
│      [View Pods] [Check Events] [Ask About This]   │
│  [View Details]                                      │
├──────────────────────────────────────────────────────┤
│  User: Why is the logger pod failing?                │
│                                                      │
│  Bot: K8sGPT detected an ImagePullBackOff on         │
│  logger-5f4 in monitoring namespace. Events show     │
│  registry.internal/logger:v2.1 returning 401...      │
│                                                      │
│  📚 KB-023: Image Pull Secret Rotation              │
│  [Save to KB]                                        │
├──────────────────────────────────────────────────────┤
│  [Type your question...                    ] [Send]  │
├──────────────────────────────────────────────────────┤
│  [📥 Export Summary]  [🗑️ Clear Chat]                │
└──────────────────────────────────────────────────────┘
```

### Components

| Component | Status | Notes |
|---|---|---|
| LoginForm | New | Kion credential input, replaces OIDC |
| ClusterSelector | New | Dropdown of discovered EKS clusters |
| CredentialBadge | Reused | TTL countdown, color-coded |
| WeatherWidget | Adapted | Data source changed to K8sGPT Results |
| WeatherDetailsDialog | Reused | Cluster info, tools, metrics |
| ChatInterface | Reused | Citations, copy buttons, save to KB |
| MessageItem | Reused | Safety warning display |
| ResultsPanel | New | K8sGPT Results list with quick actions |
| SolutionSubmitDialog | Reused | Submit fix to shared KB |
| DestructiveActionDialog | Reused | Safety confirmation (Phase 2) |
| ActionsBar | Reused | Export Summary + Clear Chat |

### Weather States

| State | Icon | Condition |
|---|---|---|
| Sunny | ☀️ | No K8sGPT Results |
| Partly Cloudy | ⛅ | 1-2 low-severity Results |
| Cloudy | ☁️ | 3-5 Results or 1 medium |
| Rainy | 🌧️ | 5-10 Results or multiple medium |
| Stormy | ⛈️ | 10+ Results or any high-severity |

Top 3 issues shown when ≥ Cloudy, with quick actions. Issue priority: Pod failures → Resource pressure → ArgoCD out of sync → Node issues → PVC issues → Cert expiring.

### Interfaces

```typescript
interface WeatherState {
  state: "sunny" | "partly-cloudy" | "cloudy" | "rainy" | "stormy";
  clusterName: string;
  clusterVersion: string;
  k8sgptResultCount: number;
  topIssues?: K8sGPTResultSummary[];
  clusterTools: ClusterToolInfo[];
  timestamp: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  k8sgptFindings?: string[];
  safetyNotice?: string;
  timestamp: string;
  savedToKB?: boolean;
  cluster: string;
}

interface ConversationContext {
  summary: string;
  recentMessages: ChatMessage[];
  totalMessages: number;
}
```

### Export Summary Format

```markdown
# DevOps Troubleshooting Summary
**Exported:** {timestamp}
**Cluster:** {cluster_name}

## Problem
{LLM-generated summary}

## Investigation
{Steps taken}

## Root Cause
{Analysis}

## Solution
{Applied fix}

## Verification
{Confirmation steps}
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/credentials/aws` | Submit Kion STS credentials |
| GET | `/api/credentials/aws/status` | Credential status + TTL |
| DELETE | `/api/credentials/aws` | Clear credentials |
| GET | `/api/clusters` | List accessible EKS clusters |
| POST | `/api/clusters/select` | Set active cluster |
| POST | `/api/chat` | Submit query, get response |
| GET | `/api/chat/history` | Conversation history |
| POST | `/api/chat/export` | LLM summary of conversation |
| GET | `/api/weather` | Cluster health for selected cluster |
| GET | `/api/weather/details` | Detailed breakdown |
| GET | `/api/results` | K8sGPT Results for selected cluster |
| GET | `/api/results/{id}` | Specific Result with enrichment |
| GET | `/api/kb/search` | Semantic search |
| POST | `/api/solutions` | Submit solution to KB |
| GET | `/api/solutions` | List solutions |
| GET | `/api/health` | Liveness check |
| GET | `/api/health/ready` | Readiness check |

---

## Deployment

### Chatbot App Manifests

Single Deployment + Service + Ingress + PVC in common cluster. Pod security: non-root UID 1000, read-only root filesystem, dropped all capabilities, seccomp. Resources: 500m/1Gi request, 1000m/2Gi limit. PVC: 10Gi ReadWriteOnce. Ingress: internal ALB.

### Security Hardening (from v1)

- Non-root UID 1000, read-only root filesystem, dropped capabilities, seccomp
- CORS with environment-based whitelist
- Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- Rate limiting on all endpoints
- Audit logging for credential operations
- Sensitive data never in logs

### Dockerfile

Multi-stage: Node 20 builds frontend → Python 3.11-slim with nginx + supervisor serves both. Shared libs installed in editable mode. Runs as UID 1000.

---

## Project Structure

```
devops-chatbot/
├── frontend/
│   ├── src/
│   │   ├── components/        # LoginForm, ClusterSelector, CredentialBadge,
│   │   │                      # WeatherWidget, ChatInterface, MessageItem,
│   │   │                      # ResultsPanel, SolutionSubmitDialog,
│   │   │                      # DestructiveActionDialog, ActionsBar
│   │   ├── hooks/             # useCredentials, useCluster, useChat, useWeather
│   │   ├── utils/             # input-validator, destructive-response-detector
│   │   └── theme/
├── backend/
│   ├── app.py
│   ├── api/                   # credentials, clusters, chat, weather,
│   │                          # results, solutions, health
│   ├── core/                  # credential_store, eks_auth, k8s_client_factory,
│   │                          # query_router, enrichment_engine, template_engine,
│   │                          # input_sanitizer, rate_limiter, conversation_history,
│   │                          # kb_seeder, startup_validator
│   └── config.py
├── libs/                      # devops-rag, devops-k8s, devops-prompts, devops-kb
├── k8s/                       # deployment, service, ingress, pvc, secrets
├── k8sgpt/                    # argocd-application, k8sgpt-cr, rbac (per-cluster)
├── docker/                    # Dockerfile, nginx.conf, supervisord.conf
├── templates/                 # base, troubleshooting, deployment, networking,
│                              # security, gitops, analysis, general (YAML)
└── docs/
```

---

## Shared Library Reuse

| Library | Role | v2 Changes |
|---|---|---|
| `devops-rag` | RAG engine, FAISS, embedding cache, LLM client | None |
| `devops-k8s` | K8s API helpers, health monitor | Adapt for per-user client instances |
| `devops-prompts` | Templates, query routing, safety rules | Router refactored; templates unchanged |
| `devops-kb` | KB management, solution storage | None — mounts to shared PVC |

---

## Non-Functional Requirements (from v1)

**Performance**: Chat <2s simple queries, Result reads <500ms, weather <1500ms, KB up to 1000 solutions.
**Reliability**: PVC persistence, graceful credential expiry, weather data preservation, independent operator.
**Security**: Non-root, read-only fs, user-scoped creds, rate limiting, input sanitization, CORS, security headers.
**Usability**: <5 min learning curve, clear errors, one-click copy, auto-detected templates.

## Success Metrics (from v1)

Solutions found in <30s, 80% query relevance, 50+ KB solutions in first month, 3+ daily users, new cluster = deploy operator only.

## Dependencies

Python 3.11+, Node.js/npm, EKS clusters + K8sGPT operator, Kion, LLM API (Anthropic/OpenAI/Ollama), FAISS + sentence-transformers, ArgoCD.

---

## Future: Apply Fix (Phase 2)

Structured fix proposals → RBAC check → confirmation dialog → execute with Kion creds → verify → CloudTrail audit. ArgoCD sync/rollback preferred. No architecture changes needed.

## Out of Scope

Advanced LLM fine-tuning, ticketing integration, real-time streaming beyond polling, user management (Kion handles identity), automated KB backup, LLM agent tool-calling (deterministic router by design).
