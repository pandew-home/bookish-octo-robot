# Design Document: DevOps Chatbot v2.0

## Overview

DevOps Chatbot v2.0 is a Kubernetes-native troubleshooting assistant that provides real-time cluster health monitoring, RAG-powered chat, and a shared team knowledge base. The architecture decouples cluster diagnostics (K8sGPT Operator per cluster) from the user-facing application (React + FastAPI deployed once in a common management cluster).

Users authenticate via Kion temporary AWS credentials, which grant both Kubernetes API and AWS API access to authorized EKS clusters. The K8sGPT Operator runs independently in each target cluster, continuously producing diagnostic Result CRDs. The chatbot reads those results and enriches them with targeted K8s API calls driven by a deterministic query router.

### Key Architectural Principles

1. **Separation of Concerns**: Diagnostics (operator) separate from user interface (app)
2. **Simplified Authentication**: Single credential source (Kion) for both K8s and AWS APIs
3. **Deterministic Routing**: Pattern-based query classification, no LLM-driven API decisions
4. **Cost Optimization**: Caching, small models, targeted API calls
5. **Multi-Cluster Support**: Single app deployment serves all clusters via cluster selector
6. **Shared Knowledge**: Team-wide knowledge base on shared PVC

## Architecture

### System Components

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
        LLM Provider (Anthropic/OpenAI/Ollama)
```

### Authentication Flow

1. User submits Kion AWS credentials (access key, secret key, session token, region)
2. Backend validates via STS GetCallerIdentity
3. Backend stores credentials in-memory with TTL
4. Backend discovers clusters via EKS ListClusters
5. User selects target cluster
6. Backend generates EKS bearer token from STS credentials
7. Backend creates Kubernetes API clients for selected cluster

### Query Processing Flow

1. User submits query through React UI
2. Input Sanitizer validates and rejects unsafe patterns
3. Rate Limiter checks per-user quota
4. Query Router classifies query using deterministic pattern matching
5. Enrichment Engine reads K8sGPT Result CRDs from target cluster
6. Enrichment Engine makes targeted K8s API calls based on classification
7. RAG Engine retrieves relevant knowledge base entries via FAISS
8. Prompt Template Engine renders structured prompt with all context
9. LLM generates response with diagnosis and recommendations
10. Response returned with citations, safety notices, K8sGPT findings
11. Conversation saved to history

### Weather/Health Monitoring Flow

1. Frontend polls weather endpoint every 60 seconds
2. Backend reads K8sGPT Result CRDs from selected cluster
3. Backend makes lightweight K8s API calls (node count, pod summary)
4. Backend calculates weather state based on result severity and count
5. Backend returns top issues, cluster info, tool versions
6. Frontend updates weather widget without flickering

## Components and Interfaces

### Backend Components

#### 1. Credential Store

In-memory storage for per-user AWS credentials with TTL-based expiration.

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
    def store(session_id: str, creds: StoredCredentials) -> None
    def get(session_id: str) -> Optional[StoredCredentials]
    def cleanup_expired() -> None
    def remove(session_id: str) -> None
```

**Thread Safety**: Uses threading.Lock for concurrent access
**Expiration**: Automatic cleanup of expired credentials
**Capacity**: Evicts oldest expired credentials when full

#### 2. EKS Token Generator

Generates Kubernetes bearer tokens from STS credentials (equivalent to `aws eks get-token`).

```python
def get_eks_bearer_token(
    creds: StoredCredentials,
    cluster_name: str
) -> str
```

**Implementation**: Uses boto3 RequestSigner to create presigned GetCallerIdentity URL
**Token Format**: `k8s-aws-v1.{base64_encoded_signed_url}`
**Expiration**: 60 seconds (short-lived, regenerated per request)

#### 3. Cluster Discovery

Discovers EKS clusters accessible with user's credentials.

```python
async def discover_clusters(
    creds: StoredCredentials
) -> list[dict]
```

**Returns**: List of cluster metadata (name, endpoint, version, status, region, CA data)
**Caching**: Results cached for 300 seconds to minimize API calls
**Error Handling**: Gracefully handles clusters user cannot describe

#### 4. K8s Client Factory

Creates authenticated Kubernetes API clients for target cluster.

```python
def get_k8s_clients(
    creds: StoredCredentials,
    cluster: dict
) -> dict[str, Any]
```

**Returns**: Dictionary with CoreV1Api, AppsV1Api, CustomObjectsApi, NetworkingV1Api, RbacAuthorizationV1Api
**Authentication**: Uses EKS bearer token
**CA Certificate**: Writes cluster CA to temporary file for SSL verification

#### 5. Query Router

Classifies user queries using deterministic pattern matching.

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
    categories: list[QueryCategory]
    resource_names: list[str]
    namespaces: list[str]
    include_k8sgpt_results: bool = True
    include_aws_context: bool = False
    time_range: Optional[timedelta] = None

class QueryRouter:
    def classify(
        query: str,
        k8sgpt_results: list
    ) -> EnrichmentPlan
```

**Pattern Matching**: Keyword-based classification with priority ordering
**Resource Extraction**: Extracts pod names, namespaces, deployment names from query text
**Time Range Detection**: Parses temporal expressions ("last hour", "today", "recently")
**AWS Context**: Only included when explicitly mentioned in query

**Category Keywords**:
- Pod Issue: "not working", "broken", "failing", "crashloop", "oom", "pending", "evicted", "imagepullbackoff", "restart", "terminated"
- Deployment: "deployment", "rollout", "helm", "chart", "replicas", "scaling", "hpa", "rollback"
- Service/Networking: "network", "dns", "connectivity", "timeout", "ingress", "load balancer", "502", "503", "504"
- Node Health: "node", "notready", "capacity", "drain", "cordon", "taint", "kubelet"
- Storage: "pvc", "volume", "storage", "persistent", "disk", "mount"
- ArgoCD: "argocd", "sync", "out of sync", "degraded", "prune", "gitops"
- Security: "rbac", "policy", "vault", "secret", "permission", "certificate", "tls", "iam"

**Priority Order** (when multiple match): Networking → Deployment → ArgoCD → Pod Issue → Security → Storage → Node Health → General

#### 6. Enrichment Engine

Executes targeted K8s and AWS API calls based on query classification.

```python
class EnrichmentEngine:
    async def execute(
        plan: EnrichmentPlan,
        k8s: dict,
        aws_creds: Optional[StoredCredentials] = None
    ) -> dict
    
    async def _enrich_pods(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_deployments(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_services(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_nodes(k8s: dict) -> dict
    
    async def _enrich_storage(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_argocd(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_security(
        k8s: dict,
        plan: EnrichmentPlan
    ) -> dict
    
    async def _enrich_general_health(k8s: dict) -> dict
    
    async def _enrich_aws(
        aws_creds: StoredCredentials
    ) -> dict
```

**Pod Enrichment**: Retrieves pod status, conditions, restart counts, events, logs (last 100 lines)
**Deployment Enrichment**: Retrieves deployment status, replica counts, rollout status, recent events
**Service Enrichment**: Retrieves service endpoints, ingress rules, network policies
**Node Enrichment**: Retrieves node conditions, capacity, allocatable resources, taints
**Storage Enrichment**: Retrieves PVC status, storage class, volume details
**ArgoCD Enrichment**: Reads ArgoCD Application CRDs, sync status, health status
**Security Enrichment**: Retrieves RBAC roles, service accounts, secrets metadata (not values)
**AWS Enrichment**: Limited to 3 API calls per query (EC2 DescribeInstances, ELB DescribeLoadBalancers)

**Error Handling**: RBAC 403 errors return "Permission denied" detail, other errors logged and noted in response

#### 7. RAG Engine

Performs semantic search over shared knowledge base using FAISS.

```python
class RAGEngine:
    def __init__(
        faiss_index_path: str,
        kb_path: str
    )
    
    def retrieve(
        query: str,
        top_k: int = 5
    ) -> list[dict]
    
    def embed(query: str) -> np.ndarray
```

**Embedding Model**: sentence-transformers (small model for cost efficiency)
**Index**: FAISS vector store on shared PVC
**Retrieval**: Top 5 results with similarity scores above 0.7
**Caching**: Embeddings cached for 3600 seconds

#### 8. Prompt Template Engine

Renders structured prompts from templates and context.

```python
class TemplateEngine:
    def render(
        categories: list[QueryCategory],
        cluster_context: dict,
        kb_results: list[dict],
        query: str,
        cluster_name: str
    ) -> str
```

**Templates**: YAML-based with Jinja2 syntax
**System Prompt**: Defines reasoning rules, output format, safety requirements
**Context Templates**: Category-specific formatting for cluster data
**Hot Reload**: Templates loaded from ConfigMap, reloadable without restart

**Base Template Structure**:
```yaml
system: |
  You are a Kubernetes troubleshooting assistant for EKS clusters.
  Rules:
  - Explain root cause before suggesting fixes
  - Reference K8sGPT findings when relevant
  - Include Safety Notices for destructive/irreversible recommendations
  - Cite knowledge base sources when used
  - Suggest ArgoCD-based fixes (sync, rollback) when applicable
  - Never fabricate resource names, events, or log entries
  
  Output format:
  1. Assessment (2-3 sentences)
  2. Evidence (data points from cluster context)
  3. Recommended Fix (step-by-step, prefer IaC/GitOps)
  4. Safety Notice (if applicable)
  5. Verification (commands to confirm fix)
  6. Related KB Articles (if any)
```

#### 9. Input Sanitizer

Validates and sanitizes user inputs to prevent code injection.

```python
class InputSanitizer:
    def validate_query(query: str) -> tuple[bool, Optional[str]]
    def sanitize_for_logging(text: str) -> str
```

**Blocked Patterns**:
- Shebang (`#!/bin/bash`)
- Shell commands (`bash`, `kubectl`, `docker`, `helm`)
- Code execution functions (`eval`, `exec`, `system`, `subprocess`)
- Command substitution (`$(...)`, `` `...` ``)
- Module imports (`import`, `require`)
- Dockerfile commands

**Length Limits**: 1-2000 characters
**Helpful Feedback**: Returns rephrase suggestions for blocked queries

#### 10. Rate Limiter

Controls API usage per user.

```python
class RateLimiter:
    def check_limit(
        user_id: str,
        endpoint: str
    ) -> tuple[bool, Optional[int]]
```

**Limits**:
- Chat: 20 requests/minute
- Solutions: 5 requests/minute
- Default: 30 requests/minute

**Environment Adjustments**:
- Dev: 10x more lenient
- Prod: 2x more strict

**Response Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

#### 11. Conversation History Manager

Manages per-user conversation history with summarization.

```python
class ConversationHistoryManager:
    def save_message(
        user_id: str,
        cluster: str,
        message: ChatMessage
    ) -> None
    
    def get_history(
        user_id: str,
        cluster: str,
        limit: int = 5
    ) -> list[ChatMessage]
    
    def summarize_conversation(
        user_id: str,
        cluster: str
    ) -> str
    
    def export_conversation(
        user_id: str,
        cluster: str
    ) -> str
```

**Storage**: `/data/conversations/{user_id}/` on shared PVC
**Per-Cluster**: Separate histories for each target cluster
**Limits**: Max 50 messages per user per cluster
**Summarization**: Auto-summarize every 7 messages to manage context window
**Persistence**: 24 hours after session ends
**Export**: Markdown format with problem, investigation, root cause, solution, verification

#### 12. Knowledge Base Seeder

Initializes knowledge base with foundation patterns on first startup.

```python
class KBSeeder:
    def seed_if_needed() -> None
    def seed_foundation_patterns() -> None
```

**Idempotent**: Safe to run multiple times
**Controlled**: `KB_SEEDING_ENABLED` and `KB_FORCE_RESEED` environment variables
**Foundation Patterns**: Auto-generated troubleshooting frameworks for common issues

#### 13. Startup Validator

Validates configuration and dependencies on backend startup.

```python
class StartupValidator:
    def validate() -> tuple[bool, list[str]]
```

**Critical Checks**:
- LLM_API_KEY environment variable set
- DEFAULT_REGION environment variable set
- PVC mounted at /data and writable
- Prompt templates loadable and valid
- FAISS index exists or can be created

**Failure Behavior**: Logs detailed errors and exits with non-zero code

#### 14. LLM Client

Interfaces with LLM providers (Anthropic, OpenAI, Ollama).

```python
class LLMClient:
    async def complete(
        prompt: str,
        max_tokens: int = 4096
    ) -> LLMResponse
```

**Providers**: Configurable via LLM_PROVIDER environment variable
**Models**: GPT-3.5-turbo or Claude Sonnet for cost efficiency
**Token Limits**: 4096 tokens max context window
**Retry Logic**: Exponential backoff for transient failures
**Logging**: Token counts and latency for cost tracking

### Frontend Components

#### 1. LoginForm

Kion credential input form.

```typescript
interface LoginFormProps {
  onLogin: (credentials: KionCredentials) => Promise<void>;
}

interface KionCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
  region: string;
}
```

**Fields**: Access Key ID, Secret Access Key, Session Token, Region (dropdown)
**Validation**: Format validation before submission
**Help Text**: Link to Kion console for credential retrieval

#### 2. ClusterSelector

Dropdown for selecting target EKS cluster.

```typescript
interface ClusterSelectorProps {
  clusters: ClusterInfo[];
  selectedCluster: string | null;
  onSelectCluster: (clusterName: string) => void;
}

interface ClusterInfo {
  name: string;
  endpoint: string;
  version: string;
  status: string;
  region: string;
}
```

**Display**: Cluster name with region and version
**Theming**: Color-coded by environment (dev/staging/prod)
**State**: Switches all data sources (weather, chat, results) to selected cluster

#### 3. CredentialBadge

Displays credential status with TTL countdown.

```typescript
interface CredentialBadgeProps {
  status: CredentialStatus;
  expiresAt: Date | null;
}

type CredentialStatus = 
  | "no_credentials"
  | "active"
  | "expiring_soon"
  | "expired";
```

**Colors**:
- No credentials: Gray
- Active (>10 min): Green
- Expiring soon (<10 min): Orange
- Expired: Red

**Countdown**: Per-second update via useCredentialStatus hook
**Polling**: Checks backend status every 30 seconds

#### 4. WeatherWidget

Displays cluster health status derived from K8sGPT Results.

```typescript
interface WeatherWidgetProps {
  weather: WeatherState;
  onRefresh: () => void;
  onViewDetails: () => void;
}

interface WeatherState {
  state: "sunny" | "partly-cloudy" | "cloudy" | "rainy" | "stormy";
  clusterName: string;
  clusterVersion: string;
  k8sgptResultCount: number;
  topIssues?: K8sGPTResultSummary[];
  clusterTools: ClusterToolInfo[];
  timestamp: string;
}
```

**Weather States**:
- Sunny ☀️: 0 critical issues
- Partly Cloudy ⛅: 1-2 low-severity results
- Cloudy ☁️: 3-5 results or 1 medium
- Rainy 🌧️: 5-10 results or multiple medium
- Stormy ⛈️: 10+ results or any high-severity

**Top Issues**: Shows top 3 issues when ≥ Cloudy
**Quick Actions**: "View Pods", "Check Events", "Ask About This" buttons
**Polling**: Auto-refresh every 60 seconds
**Preservation**: Maintains previous data during refresh to prevent flicker

#### 5. ChatInterface

Main chat UI with message history and input.

```typescript
interface ChatInterfaceProps {
  messages: ChatMessage[];
  onSendMessage: (query: string) => Promise<void>;
  onSaveToKB: (messageId: string) => void;
  onExportSummary: () => void;
  onClearChat: () => void;
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
```

**Features**:
- Message history with citations
- Copy buttons for commands and code blocks
- Safety warning display for destructive recommendations
- "Save to KB" button on assistant messages (opens SolutionSubmitDialog with conversation context)
- Export summary and clear chat actions
- Conversation export includes problem, investigation, root cause, solution, verification steps

#### 6. ResultsPanel

Displays K8sGPT Result CRDs with quick actions.

```typescript
interface ResultsPanelProps {
  results: K8sGPTResult[];
  onAskAbout: (result: K8sGPTResult) => void;
}

interface K8sGPTResult {
  name: string;
  kind: string;
  namespace: string;
  severity: "low" | "medium" | "high";
  problem: string;
  solution: string;
  analyzer: string;
  timestamp: string;
}
```

**Display**: Severity indicators, problem summary, analyzer name
**Actions**: "Ask About This" button to start chat about specific result
**Filtering**: Filter by severity, namespace, kind

#### 7. SolutionSubmitDialog

Dialog for submitting solutions to knowledge base. Users can save successful troubleshooting conversations to the shared knowledge base for team benefit.

```typescript
interface SolutionSubmitDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (solution: Solution) => Promise<void>;
  initialContent?: string;
  conversationId?: string;
}

interface Solution {
  title: string;
  description: string;
  tags: string[];
  runbookUrl?: string;
  automationScript?: string;
  estimatedFixTime?: number;
  sourceConversation?: string;
}
```

**Trigger**: "Save to KB" button on assistant messages in chat interface
**Pre-fill**: When triggered from chat, dialog pre-fills with conversation context
**Fields**: Title, description, tags, optional runbook URL, automation script, fix time estimate
**Validation**: Required fields, tag format, URL format
**Feedback**: Success/error messages after submission
**Team Benefit**: Saved solutions immediately available to all users via RAG search

### API Endpoints

```typescript
// Authentication
POST   /api/credentials/aws
GET    /api/credentials/aws/status
DELETE /api/credentials/aws

// Cluster Management
GET    /api/clusters
POST   /api/clusters/select

// Chat
POST   /api/chat
GET    /api/chat/history
POST   /api/chat/export

// Weather/Health
GET    /api/weather
GET    /api/weather/details

// K8sGPT Results
GET    /api/results
GET    /api/results/{id}

// Knowledge Base
GET    /api/kb/search
POST   /api/solutions
GET    /api/solutions

// Health Checks
GET    /api/health
GET    /api/health/ready
```

## Data Models

### Stored Credentials

```python
@dataclass
class StoredCredentials:
    access_key: str          # AWS access key ID
    secret_key: str          # AWS secret access key
    session_token: str       # AWS session token
    region: str              # AWS region
    user_arn: str            # IAM user/role ARN from GetCallerIdentity
    account_id: str          # AWS account ID
    expires_at: datetime     # Credential expiration timestamp
    created_at: datetime     # When credentials were stored
```

### Cluster Info

```python
@dataclass
class ClusterInfo:
    name: str                # EKS cluster name
    endpoint: str            # K8s API endpoint URL
    version: str             # K8s version (e.g., "1.28")
    status: str              # Cluster status (ACTIVE, CREATING, etc.)
    region: str              # AWS region
    ca_data: str             # Base64-encoded CA certificate
```

### Enrichment Plan

```python
@dataclass
class EnrichmentPlan:
    categories: list[QueryCategory]      # Query classifications
    resource_names: list[str]            # Extracted resource names
    namespaces: list[str]                # Extracted namespaces
    include_k8sgpt_results: bool = True  # Include K8sGPT Results
    include_aws_context: bool = False    # Include AWS API calls
    time_range: Optional[timedelta] = None  # Time range for events/logs
```

### Chat Message

```python
@dataclass
class ChatMessage:
    id: str                              # Unique message ID
    role: str                            # "user" or "assistant"
    content: str                         # Message text
    citations: list[Citation]            # KB article citations
    k8sgpt_findings: list[str]           # K8sGPT Result summaries
    safety_notice: Optional[str]         # Safety warning if present
    timestamp: datetime                  # Message timestamp
    saved_to_kb: bool = False            # Whether saved to KB
    cluster: str                         # Target cluster name
```

### Weather State

```python
@dataclass
class WeatherState:
    state: str                           # "sunny", "partly-cloudy", "cloudy", "rainy", "stormy"
    cluster_name: str                    # Target cluster name
    cluster_version: str                 # K8s version
    k8sgpt_result_count: int             # Total Result CRD count
    top_issues: list[K8sGPTResultSummary]  # Top 3-5 issues
    cluster_tools: list[ClusterToolInfo]   # Installed tool versions
    timestamp: datetime                  # Calculation timestamp
```

### K8sGPT Result

```python
@dataclass
class K8sGPTResult:
    name: str                            # Result CRD name
    kind: str                            # Resource kind (Pod, Deployment, etc.)
    namespace: str                       # Resource namespace
    severity: str                        # "low", "medium", "high"
    problem: str                         # Problem description
    solution: str                        # Suggested solution
    analyzer: str                        # K8sGPT analyzer name
    timestamp: datetime                  # Result creation time
    details: dict                        # Additional metadata
```

### Solution

```python
@dataclass
class Solution:
    id: str                              # Unique solution ID
    title: str                           # Solution title
    description: str                     # Detailed description
    tags: list[str]                      # Searchable tags
    runbook_url: Optional[str]           # Link to runbook
    automation_script: Optional[str]     # Automation code
    estimated_fix_time: Optional[int]    # Minutes to fix
    created_by: str                      # User who submitted
    created_at: datetime                 # Submission timestamp
    usage_count: int = 0                 # Times retrieved
    success_count: int = 0               # Times marked successful
```

### Conversation Context

```python
@dataclass
class ConversationContext:
    summary: str                         # LLM-generated summary
    recent_messages: list[ChatMessage]   # Last 5 messages
    total_messages: int                  # Total message count
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Credential Validation Consistency

*For any* set of AWS credentials (access key, secret key, session token, region), validating them via STS GetCallerIdentity should either succeed and return user identity information, or fail and return a descriptive error message without attempting storage.

**Validates: Requirements 1.1, 1.4**

### Property 2: Credential Storage Round Trip

*For any* valid AWS credentials, after storing them in the Credential_Store with a session ID, retrieving them with the same session ID should return equivalent credentials with an expiration time of 3600 seconds from storage time.

**Validates: Requirements 1.2**

### Property 3: Credential Isolation

*For any* two different users with different session IDs, storing credentials for one user should not affect the credentials retrievable for the other user.

**Validates: Requirements 1.5**

### Property 4: Cluster Discovery Uses User Credentials

*For any* authenticated user, discovering clusters should use that user's stored AWS credentials for the EKS ListClusters API call.

**Validates: Requirements 2.1**

### Property 5: Cluster Metadata Completeness

*For any* discovered cluster, the returned cluster information should include name, region, endpoint, version, status, and CA certificate data.

**Validates: Requirements 2.2**

### Property 6: Bearer Token Generation

*For any* valid credentials and cluster selection, generating an EKS bearer token should produce a token in the format `k8s-aws-v1.{base64_encoded_signed_url}`.

**Validates: Requirements 2.3**

### Property 7: K8s Client Configuration

*For any* generated bearer token and cluster info, configuring a Kubernetes API client should result in a client with the correct endpoint, bearer token authentication, and CA certificate.

**Validates: Requirements 2.4**

### Property 8: Cache Consistency

*For any* cacheable operation (cluster discovery, embeddings, API results), calling the operation twice within the cache TTL should return the same result without making a second external API call.

**Validates: Requirements 2.6, 6.5, 9.4, 9.5**

### Property 9: Weather State Classification

*For any* set of K8sGPT Result CRDs, the weather state should be classified as: Sunny (0 critical), Partly Cloudy (1-2 low severity), Cloudy (3-5 results or 1 medium), Rainy (5-10 results or multiple medium), or Stormy (10+ results or any high severity).

**Validates: Requirements 3.2, 3.3**

### Property 10: Top Issues Sorting

*For any* set of K8sGPT Result CRDs with more than 5 issues, the weather response should return exactly the top 5 issues sorted by severity (high → medium → low).

**Validates: Requirements 3.4**

### Property 11: Weather Metadata Completeness

*For any* weather calculation, the response should include cluster name, region, node count, K8sGPT version, and result count.

**Validates: Requirements 3.5**

### Property 12: Query Classification Determinism

*For any* query string, classifying it multiple times should always produce the same EnrichmentPlan with the same categories, resource names, and namespaces.

**Validates: Requirements 4.1**

### Property 13: Multi-Pattern Priority

*For any* query matching multiple category patterns, the classification should select the category with the highest priority according to the defined priority order.

**Validates: Requirements 4.3**

### Property 14: Unsafe Query Rejection

*For any* query containing unsafe patterns (shell commands, code execution functions, credential access attempts), the input sanitizer should reject it and return a safety warning.

**Validates: Requirements 4.4, 8.2, 8.3, 8.4**

### Property 15: CRD Reading on Enrichment

*For any* query classification that includes K8sGPT results, the enrichment engine should read Result CRDs from the target cluster.

**Validates: Requirements 3.1, 5.1, 12.1**

### Property 16: AWS API Call Limiting

*For any* query, the enrichment engine should make no more than 3 AWS API calls regardless of the query classification or complexity.

**Validates: Requirements 5.6, 9.3**

### Property 17: RAG Retrieval Filtering

*For any* query, the RAG engine should retrieve at most 5 knowledge base entries, and all retrieved entries should have similarity scores above 0.7.

**Validates: Requirements 6.3**

### Property 18: KB Citation Inclusion

*For any* knowledge base entries retrieved by the RAG engine, the final response should include citations for those entries.

**Validates: Requirements 6.4, 7.5**

### Property 19: Prompt Context Completeness

*For any* enriched query, the rendered prompt should include query classification, K8sGPT findings (if any), K8s API data, AWS context (if requested), and KB entries (if any).

**Validates: Requirements 7.2**

### Property 20: Token Limit Enforcement

*For any* rendered prompt, the token count should not exceed 4096 tokens before sending to the LLM.

**Validates: Requirements 7.3, 9.7**

### Property 21: Response Safety Detection

*For any* LLM response containing unsafe commands (delete, remove, destroy, drop), the system should add safety warnings to the response.

**Validates: Requirements 7.8**

### Property 22: Query Length Validation

*For any* submitted query, if the length is less than 1 character or greater than 2000 characters, the system should reject it with a validation error.

**Validates: Requirements 8.1**

### Property 23: Input Sanitization

*For any* user input that is logged or stored, the sanitized version should not contain sensitive patterns (credentials, secrets, tokens).

**Validates: Requirements 8.5**

### Property 24: Credential Format Validation

*For any* submitted AWS credentials, if they don't match the expected format (access key pattern, secret key pattern, session token pattern), the system should reject them before attempting STS validation.

**Validates: Requirements 8.6**

### Property 25: Rate Limit Enforcement

*For any* user, submitting more than 20 chat queries within a 60-second window should result in the 21st query being rejected with a 429 status code.

**Validates: Requirements 9.1**

### Property 26: Conversation History Retrieval

*For any* user with existing conversation history, submitting a new query should retrieve the last 5 messages from their history for the current cluster.

**Validates: Requirements 10.1**

### Property 27: Conversation History Storage

*For any* completed query-response interaction, both the query and response should be stored in the user's conversation history for the current cluster.

**Validates: Requirements 10.2**

### Property 28: Conversation History Isolation

*For any* two different users, one user's conversation history should not appear when retrieving the other user's history.

**Validates: Requirements 10.3**

### Property 29: Conversation History Limit

*For any* user with more than 50 messages in their conversation history, the oldest messages should be removed to maintain the 50-message limit.

**Validates: Requirements 10.4**

### Property 30: Solution Validation

*For any* submitted solution, if it's missing required fields (title, description, or tags), the system should reject it with a validation error.

**Validates: Requirements 11.1**

### Property 31: Solution Storage and Indexing

*For any* valid solution, after storing it in the Knowledge Base, it should be immediately searchable via FAISS semantic search.

**Validates: Requirements 11.2, 11.3, 11.4**

### Property 32: Shared Knowledge Base

*For any* solution added by one user, it should be retrievable by all other users in subsequent queries.

**Validates: Requirements 11.5**

### Property 33: Result Filtering by Relevance

*For any* query and set of K8sGPT Result CRDs, only results relevant to the query (matching resource names, namespaces, or categories) should be included in the LLM prompt.

**Validates: Requirements 12.2**

### Property 34: Critical Issue Highlighting

*For any* K8sGPT Result CRD with high severity, the response should format it with prominent highlighting (bold, color, or special markers).

**Validates: Requirements 12.4**

### Property 35: Result Metadata Inclusion

*For any* K8sGPT Result CRD included in a response, the response should contain the analyzer name, severity level, and timestamp.

**Validates: Requirements 12.5**

### Property 36: Cluster Switch Token Regeneration

*For any* user switching from one target cluster to another, a new EKS bearer token should be generated for the new cluster.

**Validates: Requirements 13.1**

### Property 37: Cluster Switch Client Reconfiguration

*For any* cluster switch, the Kubernetes API client should be reconfigured to point to the new cluster's endpoint with the new bearer token.

**Validates: Requirements 13.2**

### Property 38: Per-Cluster History Isolation

*For any* user with conversation history on multiple clusters, switching clusters should switch to the conversation history for the selected cluster.

**Validates: Requirements 13.3**

### Property 39: Cluster Switch Cache Invalidation

*For any* cluster switch, cached cluster-specific data (weather, results, enrichment) should be cleared.

**Validates: Requirements 13.4**

### Property 40: Remote CRD Authentication

*For any* request to read Result CRDs from a remote cluster, the system should use the user's per-session bearer token for authentication.

**Validates: Requirements 15.6**

### Property 41: Startup Validation Failure

*For any* missing required environment variable (LLM_API_KEY, DEFAULT_REGION), the backend startup should fail with a non-zero exit code and detailed error message.

**Validates: Requirements 16.1, 16.5**

### Property 42: PVC Validation

*For any* backend startup, if the Knowledge Base PVC is not mounted or not writable, the startup should fail with a non-zero exit code.

**Validates: Requirements 16.2, 16.5**

### Property 43: Template Validation

*For any* backend startup, if prompt templates cannot be loaded or have invalid structure, the startup should fail with a non-zero exit code.

**Validates: Requirements 16.3, 16.5**

### Property 44: FAISS Index Initialization

*For any* backend startup, if the FAISS index doesn't exist, it should be created; if it exists, it should be loaded successfully.

**Validates: Requirements 16.4**

### Property 45: Readiness After Validation

*For any* backend startup, the /ready endpoint should return 503 until all startup validation completes successfully, then return 200.

**Validates: Requirements 16.7**

### Property 46: Error Logging Completeness

*For any* error encountered by any component, the log entry should include severity level, timestamp, user ID (if available), and stack trace.

**Validates: Requirements 17.1**

### Property 47: User-Friendly Error Messages

*For any* user query that fails, the error response should contain a user-friendly message without internal details (stack traces, internal paths, credentials).

**Validates: Requirements 17.2**

### Property 48: API Call Logging

*For any* AWS API call or LLM API call, a log entry should be created with duration, response status, and (for LLM) token counts.

**Validates: Requirements 17.3, 17.4**

### Property 49: Credential Store Eviction

*For any* credential store at capacity, attempting to store new credentials should evict the oldest expired credentials first.

**Validates: Requirements 17.6**

### Property 50: Kubernetes API Retry with Backoff

*For any* Kubernetes API connection failure, the system should retry the request with exponentially increasing delays between attempts.

**Validates: Requirements 17.7**

## Error Handling

### Credential Expiration

When credentials expire:
1. Credential Store returns None on retrieval
2. API endpoints return 401 Unauthorized
3. Frontend displays expiration notice
4. User prompted to re-authenticate
5. Graceful degradation: K8sGPT Results still viewable if fallback service account exists

### Cluster Discovery Failures

When cluster discovery fails:
1. Log error with AWS API response
2. Return empty cluster list with error message
3. Allow user to re-enter credentials
4. Suggest checking IAM permissions

### K8sGPT Result CRD Read Failures

When Result CRD reads fail:
1. Log RBAC error or connection error
2. Return weather state as "Unknown" with diagnostic info
3. Chat continues with KB and general knowledge
4. Response notes: "Unable to read K8sGPT results - check RBAC permissions"

### Enrichment Failures

When enrichment API calls fail:
1. Log specific API error (403 RBAC, 404 Not Found, timeout)
2. Proceed with available context
3. Note failure in response: "Unable to retrieve pod logs - permission denied"
4. LLM works with partial context

### RAG Engine Failures

When FAISS search fails:
1. Log error with stack trace
2. Proceed without KB context
3. Note in response: "Knowledge base unavailable"
4. LLM generates response from cluster context only

### LLM API Failures

When LLM API calls fail:
1. Log error with provider, model, token count
2. Retry with exponential backoff (3 attempts)
3. If all retries fail, return error to user
4. Suggest checking LLM API key and quota

### Rate Limit Exceeded

When rate limits are exceeded:
1. Return 429 Too Many Requests
2. Include Retry-After header with seconds
3. Include X-RateLimit-Reset header with timestamp
4. User-friendly message: "Rate limit exceeded. Please wait {seconds} seconds."

### Input Validation Failures

When input validation fails:
1. Return 400 Bad Request
2. Specific error message (length, unsafe pattern, format)
3. Helpful suggestion: "Try rephrasing without shell commands"
4. No logging of invalid input (security)

### Startup Validation Failures

When startup validation fails:
1. Log detailed error for each failed check
2. Exit with non-zero code (prevents pod from becoming ready)
3. Kubernetes restarts pod
4. /ready endpoint returns 503 until validation passes

## Testing Strategy

### Dual Testing Approach

The system requires both unit testing and property-based testing for comprehensive coverage:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Specific credential formats (valid AWS key patterns)
- Edge cases (empty knowledge base, no K8sGPT results, expired credentials)
- Error conditions (RBAC failures, API timeouts, invalid inputs)
- Integration points (K8s client creation, LLM API calls)
- UI component rendering and interactions

**Property Tests**: Verify universal properties across all inputs
- Credential validation for any credential structure
- Query classification for any query string
- Weather calculation for any set of results
- Rate limiting for any request pattern
- Caching behavior for any cacheable operation
- Input sanitization for any user input

Together, unit tests catch concrete bugs in specific scenarios, while property tests verify general correctness across the input space.

### Property-Based Testing Configuration

**Library Selection**: Use Hypothesis (Python) for backend, fast-check (TypeScript) for frontend

**Test Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each property test must reference its design document property
- Tag format: `# Feature: devops-chatbot-v2, Property {number}: {property_text}`

**Example Property Test Structure**:

```python
from hypothesis import given, strategies as st
import pytest

@given(
    access_key=st.text(min_size=16, max_size=128),
    secret_key=st.text(min_size=16, max_size=128),
    session_token=st.text(min_size=16, max_size=512),
    region=st.sampled_from(['us-east-1', 'us-west-2', 'eu-west-1'])
)
@pytest.mark.property_test
def test_credential_storage_round_trip(access_key, secret_key, session_token, region):
    """
    Feature: devops-chatbot-v2, Property 2: Credential Storage Round Trip
    
    For any valid AWS credentials, after storing them in the Credential_Store
    with a session ID, retrieving them with the same session ID should return
    equivalent credentials with an expiration time of 3600 seconds from storage time.
    """
    # Test implementation
    pass
```

### Unit Test Focus Areas

**Backend Unit Tests**:
- Credential Store: TTL expiration, eviction policy, thread safety
- Query Router: Specific keyword matching, priority ordering
- Enrichment Engine: Category-specific API calls, error handling
- Input Sanitizer: Specific unsafe patterns, SQL injection, shell injection
- Rate Limiter: Exact threshold behavior, header formatting
- Template Engine: Template rendering, variable substitution
- Startup Validator: Each validation check independently

**Frontend Unit Tests**:
- LoginForm: Credential format validation, submission handling
- ClusterSelector: Cluster list rendering, selection handling
- CredentialBadge: Status color mapping, countdown display
- WeatherWidget: Weather state icon mapping, issue display
- ChatInterface: Message rendering, citation display, safety warnings
- ResultsPanel: Result filtering, severity indicators

**Integration Tests**:
- End-to-end chat flow: Login → cluster selection → query → response
- Credential expiration flow: Active → expiring → expired → re-auth
- Cluster switching flow: Select cluster → weather updates → history switches
- Solution submission flow: Submit → embed → index → retrieve

### Test Data Generators

**Hypothesis Strategies**:
```python
# Credential generators
valid_aws_credentials = st.builds(
    StoredCredentials,
    access_key=st.text(min_size=16, max_size=128, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
    secret_key=st.text(min_size=40, max_size=40, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'P'))),
    session_token=st.text(min_size=100, max_size=512),
    region=st.sampled_from(['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1']),
    user_arn=st.text(min_size=20, max_size=100),
    account_id=st.text(min_size=12, max_size=12, alphabet=st.characters(whitelist_categories=('Nd',))),
    expires_at=st.datetimes(min_value=datetime.now(), max_value=datetime.now() + timedelta(hours=12)),
    created_at=st.datetimes(min_value=datetime.now() - timedelta(hours=1), max_value=datetime.now())
)

# Query generators
safe_queries = st.text(min_size=1, max_size=2000, alphabet=st.characters(blacklist_characters='$`'))
unsafe_queries = st.one_of(
    st.text().filter(lambda s: 'eval(' in s or 'exec(' in s),
    st.text().filter(lambda s: '$(...)' in s or '`...`' in s),
    st.text().filter(lambda s: 'kubectl' in s or 'bash' in s)
)

# K8sGPT Result generators
k8sgpt_results = st.lists(
    st.builds(
        K8sGPTResult,
        name=st.text(min_size=1, max_size=50),
        kind=st.sampled_from(['Pod', 'Deployment', 'Service', 'PVC', 'Node']),
        namespace=st.sampled_from(['default', 'kube-system', 'monitoring', 'app']),
        severity=st.sampled_from(['low', 'medium', 'high']),
        problem=st.text(min_size=10, max_size=200),
        solution=st.text(min_size=10, max_size=200),
        analyzer=st.sampled_from(['PodAnalyzer', 'ServiceAnalyzer', 'NodeAnalyzer']),
        timestamp=st.datetimes()
    ),
    min_size=0,
    max_size=20
)
```

### Coverage Goals

- **Backend**: 80% line coverage, 90% branch coverage for core components
- **Frontend**: 70% line coverage for components, 80% for hooks and utilities
- **Property Tests**: All 50 correctness properties implemented
- **Integration Tests**: All critical user flows covered

### Continuous Integration

- Run unit tests on every commit
- Run property tests (100 iterations) on every PR
- Run integration tests on merge to main
- Generate coverage reports and fail if below thresholds
- Run property tests with 1000 iterations nightly for deeper coverage

