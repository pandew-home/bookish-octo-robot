# DevOps Chatbot v2 — Revised Architecture

## Overview

The DevOps Chatbot v2 is a simplified, decoupled architecture that separates cluster diagnostics (K8sGPT Operator, per-cluster) from the user-facing application (React + FastAPI, deployed once in a common cluster). Users authenticate via Kion temporary AWS credentials, which grant both Kubernetes API and AWS API access to their authorized EKS clusters.

### Key Design Changes from v1

| Concern | v1 (Previous) | v2 (Revised) |
|---|---|---|
| Cluster diagnostics | K8sGPT MCP server pod per cluster | K8sGPT Operator per cluster (CRD-based) |
| MCP protocol | Required for K8sGPT and AWS integration | Eliminated entirely |
| AWS context | Separate AWS MCP server pod | Direct boto3 calls using user's Kion creds |
| Authentication | OIDC flow + JWT | Kion temp AWS creds → EKS bearer token |
| Deployment model | Multi-pod Helm chart per cluster | Operator per cluster + single app deployment |
| Frontend/Backend | In-cluster with nginx/supervisor | Single Deployment in common cluster |
| Inter-service networking | MCP pods, network policies, circuit breakers | None — operator is independent, app reads CRDs |

---

## Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────┐
│  EKS Cluster: Dev                                   │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing)                             │
├─────────────────────────────────────────────────────┤
│  EKS Cluster: Staging                               │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing)                             │
├─────────────────────────────────────────────────────┤
│  EKS Cluster: Prod                                  │
│   ├── K8sGPT Operator (read-only ServiceAccount)    │
│   │    └── Produces Result CRDs continuously        │
│   └── ArgoCD (existing)                             │
└──────────────┬──────────────────────────────────────┘
               │ K8s API + AWS API
               │ (user's Kion STS creds)
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
│  │   └── Chat interface                           │ │
│  │                                                │ │
│  │  FastAPI Backend                               │ │
│  │   ├── Credential Store (per-user, in-memory)   │ │
│  │   ├── EKS Token Generator (STS → bearer)       │ │
│  │   ├── Cluster Discovery (list EKS clusters)    │ │
│  │   ├── Query Router                             │ │
│  │   ├── Enrichment Engine                        │ │
│  │   ├── RAG Engine (FAISS + embeddings)          │ │
│  │   ├── Prompt Templates                         │ │
│  │   └── LLM Client                              │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ PVC ──────────────────────────────────────────┐ │
│  │  /data/kb/         → Knowledge base (shared)   │ │
│  │  /data/embeddings/ → FAISS index + cache       │ │
│  │  /data/solutions/  → User-submitted solutions  │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
               │
               ▼
        LLM Provider (Anthropic / OpenAI / Ollama)
```

---

## Authentication & Credential Flow

### Login Flow

```
1. User opens chatbot UI in browser
2. UI presents Kion credential form:
   - AWS Access Key ID
   - AWS Secret Access Key
   - AWS Session Token
   - Region (dropdown, default from config)
3. Frontend POSTs creds to backend: POST /api/credentials/aws
4. Backend validates creds via STS GetCallerIdentity
5. Backend stores creds in-memory with TTL (from Kion expiration)
6. Backend discovers clusters: EKS ListClusters with the creds
7. Frontend receives cluster list, shows dropdown
8. User selects a cluster → UI loads weather + chat for that cluster
```

### Credential Usage

```python
# User's Kion creds enable two auth paths:

# 1. Kubernetes API (pods, logs, events, CRDs, ArgoCD resources)
#    STS creds → presigned GetCallerIdentity URL → EKS bearer token
#    EKS validates token → maps to K8s identity via aws-auth/access entries
#    K8s RBAC enforces per-user permissions

# 2. AWS API (EKS cluster info, node groups — used infrequently)
#    STS creds → boto3 session directly
#    IAM policies enforce per-user permissions
```

### Cluster Discovery

```python
async def discover_clusters(aws_creds: dict, region: str) -> list[dict]:
    """List EKS clusters the user has access to."""
    session = boto3.Session(
        aws_access_key_id=aws_creds['access_key'],
        aws_secret_access_key=aws_creds['secret_key'],
        aws_session_token=aws_creds['session_token'],
        region_name=region
    )
    eks = session.client('eks')

    cluster_names = eks.list_clusters()['clusters']
    clusters = []
    for name in cluster_names:
        try:
            info = eks.describe_cluster(name=name)['cluster']
            clusters.append({
                'name': name,
                'endpoint': info['endpoint'],
                'version': info['version'],
                'status': info['status'],
                'region': region,
                'ca_data': info['certificateAuthority']['data'],
            })
        except Exception:
            pass  # user may not have describe access to all clusters

    return clusters
```

### EKS Bearer Token Generation

```python
import boto3
import base64
from botocore.signers import RequestSigner

def get_eks_bearer_token(aws_creds: dict, cluster_name: str, region: str) -> str:
    """Generate a K8s bearer token from STS creds (equivalent to aws eks get-token)."""
    session = boto3.Session(
        aws_access_key_id=aws_creds['access_key'],
        aws_secret_access_key=aws_creds['secret_key'],
        aws_session_token=aws_creds['session_token'],
        region_name=region
    )

    sts = session.client('sts', region_name=region)
    service_id = sts.meta.service_model.service_id

    signer = RequestSigner(service_id, region, 'sts', 'v4',
                           session.get_credentials(), session.events)

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/'
               f'?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }

    signed_url = signer.generate_presigned_url(
        params, region_name=region, expires_in=60, operation_name=''
    )

    return 'k8s-aws-v1.' + base64.urlsafe_b64encode(
        signed_url.encode('utf-8')
    ).decode('utf-8').rstrip('=')
```

### Full K8s Client Factory

```python
from kubernetes import client
import tempfile, base64, os

def get_k8s_clients(aws_creds: dict, cluster: dict) -> dict:
    """Create authenticated K8s API clients using Kion STS creds."""
    token = get_eks_bearer_token(aws_creds, cluster['name'], cluster['region'])

    config = client.Configuration()
    config.host = cluster['endpoint']
    config.api_key = {"authorization": f"Bearer {token}"}

    # Write CA cert to temp file
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
    }
```

---

## K8sGPT Operator (Per-Cluster)

### Deployment

Each target EKS cluster gets the K8sGPT operator deployed via ArgoCD:

```yaml
# argocd/k8sgpt-operator/application.yaml
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
    helm:
      values: |
        # operator values
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
    model: gpt-4o-mini          # cost-effective for continuous scanning
    backend: openai             # or amazonbedrock with IRSA
    secret:
      name: k8sgpt-ai-secret
      key: api-key
  noCache: false
  repository: ghcr.io/k8sgpt-ai/k8sgpt
  version: v0.4.1
  # filters:                   # optional: limit scan scope
  #   - Pod
  #   - Service
  #   - Ingress
  #   - Deployment
  #   - StatefulSet
  #   - PersistentVolumeClaim
  #   - Node
```

### RBAC (Read-Only)

The operator's ServiceAccount needs read access to cluster resources for scanning:

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
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

### Reading Results from the Chatbot Backend

```python
def get_k8sgpt_results(k8s_clients: dict) -> list[dict]:
    """Read K8sGPT Result CRDs from target cluster."""
    results = k8s_clients['custom'].list_namespaced_custom_object(
        group="core.k8sgpt.ai",
        version="v1alpha1",
        namespace="k8sgpt-operator-system",
        plural="results"
    )
    return results.get('items', [])
```

---

## Backend Components

### Query Router

Classifies user queries and determines what cluster data to collect. No LLM involved — deterministic pattern matching with optional lightweight classification.

```python
from dataclasses import dataclass, field
from enum import Enum

class QueryCategory(Enum):
    POD_ISSUE = "pod_issue"
    DEPLOYMENT_STATUS = "deployment_status"
    SERVICE_NETWORKING = "service_networking"
    NODE_HEALTH = "node_health"
    STORAGE = "storage"
    ARGOCD = "argocd"
    GENERAL_HEALTH = "general_health"
    KB_SEARCH = "kb_search"

@dataclass
class EnrichmentPlan:
    categories: list[QueryCategory] = field(default_factory=list)
    resource_names: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    include_k8sgpt_results: bool = True
    include_aws_context: bool = False    # minimized — only when explicit

class QueryRouter:
    def classify(self, query: str, k8sgpt_results: list) -> EnrichmentPlan:
        plan = EnrichmentPlan()

        # Pattern matching for resource types
        if mentions_pod(query):
            plan.categories.append(QueryCategory.POD_ISSUE)
        if mentions_deployment(query):
            plan.categories.append(QueryCategory.DEPLOYMENT_STATUS)
        if mentions_service_or_networking(query):
            plan.categories.append(QueryCategory.SERVICE_NETWORKING)
        if mentions_node(query):
            plan.categories.append(QueryCategory.NODE_HEALTH)
        if mentions_argocd(query):
            plan.categories.append(QueryCategory.ARGOCD)
        if mentions_storage(query):
            plan.categories.append(QueryCategory.STORAGE)

        # AWS context only when explicitly asked
        if mentions_aws_or_eks_infra(query):
            plan.include_aws_context = True

        # Extract resource names and namespaces from query
        plan.resource_names = extract_resource_names(query)
        plan.namespaces = extract_namespaces(query)

        # Cross-reference with active K8sGPT Results
        for result in k8sgpt_results:
            if result_matches_query(result, query):
                plan.categories.append(infer_category(result))

        # Default to general health if nothing matched
        if not plan.categories:
            plan.categories.append(QueryCategory.GENERAL_HEALTH)

        return plan
```

### Enrichment Engine

Executes the plan from the query router — makes targeted K8s API calls based on query classification.

```python
class EnrichmentEngine:
    async def execute(self, plan: EnrichmentPlan,
                      k8s: dict, aws_creds: dict = None) -> dict:
        context = {}

        # Always include K8sGPT Results
        if plan.include_k8sgpt_results:
            context['k8sgpt_results'] = get_k8sgpt_results(k8s)

        for category in plan.categories:
            if category == QueryCategory.POD_ISSUE:
                context['pods'] = await self._enrich_pods(
                    k8s, plan.resource_names, plan.namespaces)

            elif category == QueryCategory.DEPLOYMENT_STATUS:
                context['deployments'] = await self._enrich_deployments(
                    k8s, plan.resource_names, plan.namespaces)

            elif category == QueryCategory.SERVICE_NETWORKING:
                context['services'] = await self._enrich_services(
                    k8s, plan.resource_names, plan.namespaces)

            elif category == QueryCategory.NODE_HEALTH:
                context['nodes'] = await self._enrich_nodes(k8s)

            elif category == QueryCategory.ARGOCD:
                context['argo_apps'] = await self._enrich_argocd(
                    k8s, plan.resource_names, plan.namespaces)

            elif category == QueryCategory.GENERAL_HEALTH:
                context['health'] = await self._enrich_general_health(k8s)

        # AWS context only when plan says so (minimized)
        if plan.include_aws_context and aws_creds:
            context['aws'] = await self._enrich_aws(aws_creds)

        return context

    async def _enrich_pods(self, k8s, names, namespaces):
        results = {}
        for ns in namespaces or ['default']:
            for name in names:
                try:
                    pod = k8s['core'].read_namespaced_pod(name, ns)
                    events = k8s['core'].list_namespaced_event(
                        ns, field_selector=f"involvedObject.name={name}")
                    logs = None
                    try:
                        logs = k8s['core'].read_namespaced_pod_log(
                            name, ns, tail_lines=100, previous=True)
                    except Exception:
                        pass
                    results[f"{ns}/{name}"] = {
                        'status': pod.status.phase,
                        'conditions': [c.to_dict() for c in (pod.status.conditions or [])],
                        'restart_count': sum(
                            cs.restart_count for cs in (pod.status.container_statuses or [])),
                        'events': [e.to_dict() for e in events.items[-10:]],
                        'logs': logs,
                    }
                except Exception as e:
                    results[f"{ns}/{name}"] = {'error': str(e)}
        return results

    async def _enrich_argocd(self, k8s, names, namespaces):
        """Read ArgoCD Application CRDs from the cluster."""
        try:
            if names:
                apps = []
                for name in names:
                    app = k8s['custom'].get_namespaced_custom_object(
                        group="argoproj.io", version="v1alpha1",
                        namespace="argocd", plural="applications", name=name)
                    apps.append(app)
                return apps
            else:
                result = k8s['custom'].list_namespaced_custom_object(
                    group="argoproj.io", version="v1alpha1",
                    namespace="argocd", plural="applications")
                return result.get('items', [])
        except Exception as e:
            return {'error': str(e)}
```

### Prompt Templates

Structure the gathered context into well-crafted LLM prompts. Templates define how the LLM should reason and respond.

```yaml
# templates/base.yaml
system: |
  You are a Kubernetes troubleshooting assistant for EKS clusters.
  You have access to K8sGPT diagnostic results and live cluster data.

  Rules:
  - Explain root cause before suggesting fixes.
  - Reference specific K8sGPT findings when relevant.
  - Include Safety Notices for any destructive or irreversible recommendations.
  - Cite knowledge base sources when used.
  - Suggest ArgoCD-based fixes (sync, rollback) when applicable.
  - If data is insufficient, explain what additional access is needed.
  - Never fabricate resource names, events, or log entries.

  Output format:
  1. Diagnosis (what's wrong and why)
  2. Evidence (specific data points from cluster context)
  3. Recommended Fix (step-by-step)
  4. Safety Notice (if applicable — destructive or irreversible actions)
  5. Related KB Articles (if any matches)

# templates/pod_troubleshooting.yaml
context_template: |
  ## K8sGPT Diagnosis
  {{ k8sgpt_results | format_results }}

  ## Pod Status
  {{ pods | format_pod_status }}

  ## Recent Events
  {{ pods | format_events }}

  ## Container Logs (last 100 lines)
  {{ pods | format_logs }}

  ## Knowledge Base Matches
  {{ kb_results | format_kb }}

# templates/argocd.yaml
context_template: |
  ## K8sGPT Diagnosis
  {{ k8sgpt_results | format_results }}

  ## ArgoCD Applications
  {{ argo_apps | format_argo_status }}

  ## Related Deployments
  {{ deployments | format_deployment_status }}

  ## Knowledge Base Matches
  {{ kb_results | format_kb }}
```

### RAG Engine

Unchanged from v1 — semantic search over the shared knowledge base.

```python
class RAGEngine:
    def __init__(self, faiss_index_path: str, kb_path: str):
        self.index = load_faiss_index(faiss_index_path)
        self.kb = load_knowledge_base(kb_path)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve top-k relevant KB entries for the query."""
        embedding = self.embed(query)
        distances, indices = self.index.search(embedding, top_k)
        return [self.kb[i] for i in indices[0] if i < len(self.kb)]
```

### Chat Endpoint (Putting It All Together)

```python
@app.post("/api/chat")
async def chat(query: ChatQuery, user: User = Depends(get_authenticated_user)):
    # 1. Get user's K8s clients for selected cluster
    k8s = get_k8s_clients(user.aws_creds, user.selected_cluster)

    # 2. Read K8sGPT Results
    k8sgpt_results = get_k8sgpt_results(k8s)

    # 3. Classify query and build enrichment plan
    plan = query_router.classify(query.text, k8sgpt_results)

    # 4. Execute enrichment — targeted K8s API calls
    cluster_context = await enrichment_engine.execute(
        plan, k8s, user.aws_creds if plan.include_aws_context else None)

    # 5. RAG retrieval from shared knowledge base
    kb_results = rag_engine.retrieve(query.text)

    # 6. Build prompt using template
    prompt = template_engine.render(
        plan.categories,
        cluster_context=cluster_context,
        kb_results=kb_results,
        query=query.text,
        cluster_name=user.selected_cluster['name'],
    )

    # 7. Send to LLM
    response = await llm_client.complete(prompt)

    return ChatResponse(
        answer=response.text,
        sources=kb_results,
        k8sgpt_findings=relevant_results_summary(k8sgpt_results),
        cluster=user.selected_cluster['name'],
    )
```

---

## Frontend

### Login Screen

```
┌──────────────────────────────────────────┐
│          DevOps Chatbot Login            │
│                                          │
│  AWS Access Key ID:     [____________]   │
│  AWS Secret Access Key: [____________]   │
│  Session Token:         [____________]   │
│  Region:                [us-east-1  ▼]   │
│                                          │
│              [ Connect ]                 │
│                                          │
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
│  └── PVC: data-vol-3 — Pending (no matching SC)     │
│  [Ask About This] [View All Results]                 │
├──────────────────────────────────────────────────────┤
│                                                      │
│  User: Why is the logger pod failing?                │
│                                                      │
│  Bot: K8sGPT detected an ImagePullBackOff on         │
│  logger-5f4 in the monitoring namespace. The pod     │
│  events show the image registry.internal/logger:v2.1 │
│  is returning a 401 Unauthorized. This typically     │
│  means the image pull secret has expired.            │
│                                                      │
│  Recommended fix:                                    │
│  1. Check the pull secret: kubectl get secret...     │
│  2. Regenerate via ArgoCD sync if managed...         │
│                                                      │
│  📚 KB-023: Image Pull Secret Rotation              │
│                                                      │
│  [Save to KB] [Export Summary]                       │
├──────────────────────────────────────────────────────┤
│  [Type your question...                    ] [Send]  │
└──────────────────────────────────────────────────────┘
```

### UI State Management

- **Cluster selector**: switches all data sources (weather, chat, results) to selected cluster
- **Credential badge**: shows TTL countdown, color-coded (green/orange/red/gray)
- **Weather widget**: polls backend for K8sGPT Results summary on selected cluster
- **Chat**: contextual to selected cluster, maintains per-cluster history

---

## Deployment

### Chatbot App (Common Cluster)

Single Deployment + Service + Ingress + PVC:

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: devops-chatbot
  namespace: devops-tools
spec:
  replicas: 1
  selector:
    matchLabels:
      app: devops-chatbot
  template:
    metadata:
      labels:
        app: devops-chatbot
    spec:
      containers:
        - name: chatbot
          image: devops-chatbot:latest
          ports:
            - containerPort: 80
              name: http
          env:
            - name: LLM_PROVIDER
              value: "anthropic"
            - name: LLM_MODEL
              value: "claude-sonnet-4-20250514"
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: chatbot-secrets
                  key: llm-api-key
            - name: DEFAULT_REGION
              value: "us-east-1"
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 1000m
              memory: 2Gi
          livenessProbe:
            httpGet:
              path: /api/health
              port: 80
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/health
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 5
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: devops-chatbot-data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: devops-chatbot-data
  namespace: devops-tools
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: devops-chatbot
  namespace: devops-tools
spec:
  selector:
    app: devops-chatbot
  ports:
    - port: 80
      targetPort: 80
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: devops-chatbot
  namespace: devops-tools
  annotations:
    alb.ingress.kubernetes.io/scheme: internal
spec:
  rules:
    - host: chatbot.internal.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: devops-chatbot
                port:
                  number: 80
```

### Dockerfile (Simplified Single Container)

```dockerfile
# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + nginx
FROM python:3.11-slim
RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*

# Backend
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY libs/ ./libs/
RUN pip install -e ./libs/devops-rag \
    -e ./libs/devops-k8s \
    -e ./libs/devops-prompts \
    -e ./libs/devops-kb

# Frontend static files
COPY --from=frontend-build /app/frontend/build /var/www/html

# Nginx config
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Supervisor config
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 80
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

---

## Project Structure (Revised)

```
devops-chatbot/
├── README.md
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── LoginForm.tsx          # Kion credential input
│   │   │   ├── ClusterSelector.tsx    # Cluster dropdown
│   │   │   ├── CredentialBadge.tsx    # TTL countdown
│   │   │   ├── WeatherWidget.tsx      # Cluster health from Results
│   │   │   ├── ChatInterface.tsx      # Main chat UI
│   │   │   ├── ResultsPanel.tsx       # K8sGPT Results list
│   │   │   └── SolutionSubmit.tsx     # Submit fix to KB
│   │   ├── hooks/
│   │   │   ├── useCredentials.ts
│   │   │   ├── useCluster.ts
│   │   │   └── useChat.ts
│   │   └── theme/
│
├── backend/
│   ├── requirements.txt
│   ├── app.py                         # FastAPI main
│   ├── api/
│   │   ├── auth.py                    # Kion credential endpoints
│   │   ├── clusters.py                # Cluster discovery + selection
│   │   ├── chat.py                    # Chat endpoint
│   │   ├── weather.py                 # Health/weather from Results
│   │   ├── results.py                 # K8sGPT Results API
│   │   └── solutions.py               # KB solution submission
│   ├── core/
│   │   ├── credential_store.py        # In-memory cred store w/ TTL
│   │   ├── eks_auth.py                # STS → EKS bearer token
│   │   ├── k8s_client_factory.py      # Create K8s clients per user
│   │   ├── query_router.py            # Query classification
│   │   ├── enrichment_engine.py       # K8s/AWS data collection
│   │   └── template_engine.py         # Prompt template rendering
│   └── config.py
│
├── libs/                              # Shared libraries (unchanged)
│   ├── devops-rag/
│   ├── devops-k8s/
│   ├── devops-prompts/
│   └── devops-kb/
│
├── k8s/                               # Chatbot app manifests
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── pvc.yaml
│   └── secrets.yaml
│
├── k8sgpt/                            # Per-cluster operator config
│   ├── argocd-application.yaml
│   ├── k8sgpt-cr.yaml
│   └── rbac.yaml
│
├── docker/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── supervisord.conf
│
└── docs/
    └── architecture.md                # This document
```

---

## Future: Apply Fix (Phase 2)

The read-only diagnostic architecture is designed to support write operations later:

```
Diagnosis → Proposed Fix → User Approval → Execute → Verify
```

Requirements for Phase 2:
- LLM returns structured fix proposals (resource type, patch, safety level)
- Backend validates user RBAC before showing Apply button
- Confirmation dialog with affected resources and rollback plan
- Execution uses user's Kion creds (full audit trail)
- Post-fix verification re-runs enrichment to confirm resolution
- ArgoCD sync/rollback as preferred fix path where applicable

No architecture changes required — the enrichment engine, credential flow, and K8s client factory already support write operations.

---

## Comparison: v1 vs v2

| Metric | v1 | v2 |
|---|---|---|
| Pods per cluster | 3-4 (chatbot + MCP servers) | 1 (K8sGPT operator only) |
| Chatbot deployment | Per-cluster, complex Helm chart | Once, simple manifests |
| Helm templates | ~15 | ~5 |
| Inter-service networking | MCP protocol, network policies, circuit breakers | None |
| Auth complexity | OIDC + JWT + Kion credential exchange | Kion creds only |
| Knowledge base | Per-instance, isolated | Shared PVC, team-wide |
| Multi-cluster support | Separate deployments | One app, cluster selector |
| Time to add new cluster | Deploy full stack | Deploy K8sGPT operator + add to config |
