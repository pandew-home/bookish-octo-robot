# Enrichment Engine Implementation Plan

## Overview

The Enrichment Engine is the core component that gathers relevant context from Kubernetes and AWS APIs based on the query classification. It's the bridge between "what the user asked" and "what data the LLM needs to answer."

## Architecture

```
Query → QueryRouter → EnrichmentPlan → EnrichmentEngine → EnrichedContext → LLM
                          ↓
                    Categories:
                    - POD_ISSUE
                    - DEPLOYMENT_STATUS
                    - SERVICE_NETWORKING
                    - NODE_HEALTH
                    - STORAGE
                    - ARGOCD
                    - SECURITY
                    - GENERAL_HEALTH
```

## Design Principles

### 1. **Targeted API Calls**
- Only call APIs relevant to the query category
- Avoid "fetch everything" approach
- Use resource names from query when available
- Respect the 3-call limit for AWS APIs

### 2. **Graceful Degradation**
- If one enrichment fails, continue with others
- Return partial context rather than failing completely
- Log failures but don't block the response
- Include error notes in the enriched context

### 3. **Performance**
- Parallel API calls where possible (asyncio)
- Timeout protection (10 seconds max per enrichment)
- Minimal data retrieval (only what's needed)
- Smart filtering based on time range

### 4. **Error Handling**
- RBAC 403 → "Permission denied" with helpful message
- 404 → "Resource not found" with context
- Timeout → "Cluster slow to respond" with partial data
- All errors use centralized error_handler

## Component Structure

```python
class EnrichmentEngine:
    """
    Main enrichment engine that coordinates all enrichment operations.
    """
    
    def __init__(self, k8s_clients: dict, aws_creds: Optional[StoredCredentials]):
        self.k8s = k8s_clients
        self.aws_creds = aws_creds
        self.timeout = 10  # seconds
    
    async def execute(self, plan: EnrichmentPlan) -> EnrichedContext:
        """
        Execute enrichment plan and gather all relevant context.
        
        Returns EnrichedContext with:
        - k8sgpt_results: List of K8sGPT Result CRDs
        - pod_data: Pod status, events, logs
        - deployment_data: Deployment status, replicas, events
        - service_data: Service endpoints, ingress rules
        - node_data: Node conditions, capacity
        - storage_data: PVC status, volumes
        - argocd_data: Application CRDs, sync status
        - security_data: RBAC roles, service accounts
        - aws_data: EC2, ELB data (limited to 3 calls)
        - errors: List of enrichment errors encountered
        """
```

## Enrichment Categories

### 1. Pod Enrichment (`_enrich_pods`)

**What to Retrieve:**
- Pod status (phase, conditions, restart count)
- Container statuses (ready, state, last termination)
- Recent events (last 50, filtered by time range)
- Container logs (last 100 lines, or time-filtered)
- Resource usage (if metrics-server available)

**API Calls:**
```python
# If specific pod names provided
for pod_name in plan.resource_names:
    pod = core_v1.read_namespaced_pod(pod_name, namespace)
    events = core_v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={pod_name}")
    logs = core_v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=100)

# If no specific pods, get all pods in namespace
pods = core_v1.list_namespaced_pod(namespace, limit=20)
```

**Error Handling:**
- 403 RBAC → "You don't have permission to view pods in this namespace"
- 404 → "Pod '{pod_name}' not found. It may have been deleted."
- Timeout → "Cluster is slow to respond. Showing partial pod data."

**Output Structure:**
```python
{
    "pods": [
        {
            "name": "my-app-12345-abcde",
            "namespace": "production",
            "phase": "CrashLoopBackOff",
            "restart_count": 15,
            "containers": [
                {
                    "name": "app",
                    "ready": False,
                    "state": "waiting",
                    "reason": "CrashLoopBackOff",
                    "last_termination": {
                        "reason": "Error",
                        "exit_code": 1,
                        "message": "OOMKilled"
                    }
                }
            ],
            "events": [
                {
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": "Back-off restarting failed container",
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            ],
            "logs": "Error: Cannot allocate memory\nFatal: Application crashed"
        }
    ],
    "summary": "Found 1 pod in CrashLoopBackOff state with 15 restarts"
}
```

### 2. Deployment Enrichment (`_enrich_deployments`)

**What to Retrieve:**
- Deployment status (replicas, available, updated)
- Rollout status (conditions, progress)
- ReplicaSet information
- Recent events
- Deployment strategy

**API Calls:**
```python
deployment = apps_v1.read_namespaced_deployment(name, namespace)
replica_sets = apps_v1.list_namespaced_replica_set(namespace, label_selector=f"app={name}")
events = core_v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}")
```

**Output Structure:**
```python
{
    "deployments": [
        {
            "name": "my-app",
            "namespace": "production",
            "replicas": {
                "desired": 3,
                "current": 2,
                "available": 1,
                "unavailable": 2
            },
            "conditions": [
                {
                    "type": "Progressing",
                    "status": "False",
                    "reason": "ProgressDeadlineExceeded",
                    "message": "ReplicaSet has timed out progressing"
                }
            ],
            "strategy": "RollingUpdate",
            "events": [...]
        }
    ]
}
```

### 3. Service/Networking Enrichment (`_enrich_services`)

**What to Retrieve:**
- Service endpoints (ready/not ready)
- Ingress rules and status
- Network policies affecting the service
- Load balancer status (if applicable)

**API Calls:**
```python
service = core_v1.read_namespaced_service(name, namespace)
endpoints = core_v1.read_namespaced_endpoints(name, namespace)
ingresses = networking_v1.list_namespaced_ingress(namespace)
network_policies = networking_v1.list_namespaced_network_policy(namespace)
```

**Output Structure:**
```python
{
    "services": [
        {
            "name": "my-service",
            "type": "LoadBalancer",
            "cluster_ip": "10.0.0.1",
            "external_ip": "52.1.2.3",
            "ports": [{"port": 80, "target_port": 8080}],
            "endpoints": {
                "ready": ["10.0.1.1:8080", "10.0.1.2:8080"],
                "not_ready": ["10.0.1.3:8080"]
            },
            "ingress": {
                "host": "myapp.example.com",
                "path": "/",
                "backend": "my-service:80"
            }
        }
    ]
}
```

### 4. Node Enrichment (`_enrich_nodes`)

**What to Retrieve:**
- Node conditions (Ready, MemoryPressure, DiskPressure)
- Capacity and allocatable resources
- Taints and labels
- Pod count per node

**API Calls:**
```python
nodes = core_v1.list_node()
for node in nodes:
    pods = core_v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node.metadata.name}")
```

**Output Structure:**
```python
{
    "nodes": [
        {
            "name": "ip-10-0-1-100.ec2.internal",
            "status": "Ready",
            "conditions": [
                {"type": "MemoryPressure", "status": "False"},
                {"type": "DiskPressure", "status": "True"}
            ],
            "capacity": {
                "cpu": "4",
                "memory": "16Gi",
                "pods": "110"
            },
            "allocatable": {
                "cpu": "3.9",
                "memory": "14.5Gi",
                "pods": "110"
            },
            "pod_count": 45,
            "taints": [
                {"key": "node.kubernetes.io/disk-pressure", "effect": "NoSchedule"}
            ]
        }
    ]
}
```

### 5. Storage Enrichment (`_enrich_storage`)

**What to Retrieve:**
- PVC status (bound, pending, lost)
- PV information
- Storage class details
- Volume mount issues

**API Calls:**
```python
pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace)
pvs = core_v1.list_persistent_volume()
storage_classes = storage_v1.list_storage_class()
```

### 6. ArgoCD Enrichment (`_enrich_argocd`)

**What to Retrieve:**
- Application CRD status
- Sync status (synced, out-of-sync)
- Health status (healthy, degraded, progressing)
- Last sync time and result

**API Calls:**
```python
applications = custom_objects.list_namespaced_custom_object(
    group="argoproj.io",
    version="v1alpha1",
    namespace="argocd",
    plural="applications"
)
```

**Output Structure:**
```python
{
    "applications": [
        {
            "name": "my-app",
            "sync_status": "OutOfSync",
            "health_status": "Degraded",
            "last_sync": "2024-01-15T10:00:00Z",
            "source": {
                "repo": "https://github.com/org/repo",
                "path": "k8s/production",
                "target_revision": "main"
            },
            "out_of_sync_resources": [
                {"kind": "Deployment", "name": "my-app", "status": "OutOfSync"}
            ]
        }
    ]
}
```

### 7. Security Enrichment (`_enrich_security`)

**What to Retrieve:**
- RBAC roles and bindings
- Service account details
- Secrets metadata (NOT values)
- Pod security policies/standards

**API Calls:**
```python
roles = rbac_v1.list_namespaced_role(namespace)
role_bindings = rbac_v1.list_namespaced_role_binding(namespace)
service_accounts = core_v1.list_namespaced_service_account(namespace)
```

### 8. AWS Enrichment (`_enrich_aws`)

**CRITICAL: Maximum 3 API calls per query**

**What to Retrieve (prioritized):**
1. **Load Balancer Status** (if service/networking query)
   ```python
   elb.describe_load_balancers(Names=[lb_name])
   ```

2. **EC2 Instance Health** (if node query)
   ```python
   ec2.describe_instances(InstanceIds=[instance_ids])
   ```

3. **VPC/Security Group** (if networking query)
   ```python
   ec2.describe_security_groups(GroupIds=[sg_ids])
   ```

**Call Priority Logic:**
```python
if QueryCategory.SERVICE_NETWORKING in plan.categories:
    # Priority 1: Load balancer
    # Priority 2: Security groups
    # Priority 3: VPC
elif QueryCategory.NODE_HEALTH in plan.categories:
    # Priority 1: EC2 instances
    # Priority 2: Auto-scaling groups
    # Priority 3: EBS volumes
```

## Parallel Execution Strategy

```python
async def execute(self, plan: EnrichmentPlan) -> EnrichedContext:
    """Execute enrichments in parallel for performance."""
    
    tasks = []
    
    # Create tasks based on categories
    for category in plan.categories:
        if category == QueryCategory.POD_ISSUE:
            tasks.append(self._enrich_pods(plan))
        elif category == QueryCategory.DEPLOYMENT_STATUS:
            tasks.append(self._enrich_deployments(plan))
        # ... etc
    
    # Always include K8sGPT results
    if plan.include_k8sgpt_results:
        tasks.append(self._read_k8sgpt_results())
    
    # Execute all tasks in parallel with timeout
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine results and handle errors
    context = EnrichedContext()
    for result in results:
        if isinstance(result, Exception):
            context.errors.append(str(result))
        else:
            context.merge(result)
    
    return context
```

## Error Handling Strategy

### 1. **RBAC Errors (403)**
```python
try:
    pods = core_v1.list_namespaced_pod(namespace)
except ApiException as e:
    if e.status == 403:
        return {
            "error": "permission_denied",
            "message": "You don't have permission to view pods in namespace '{namespace}'",
            "suggestion": "Contact your cluster administrator to grant pod read permissions"
        }
```

### 2. **Resource Not Found (404)**
```python
try:
    pod = core_v1.read_namespaced_pod(name, namespace)
except ApiException as e:
    if e.status == 404:
        return {
            "error": "not_found",
            "message": f"Pod '{name}' not found in namespace '{namespace}'",
            "suggestion": "The pod may have been deleted. Check recent events."
        }
```

### 3. **Timeout**
```python
try:
    async with asyncio.timeout(10):
        pods = await core_v1.list_namespaced_pod(namespace)
except asyncio.TimeoutError:
    return {
        "error": "timeout",
        "message": "Cluster is slow to respond",
        "partial_data": cached_data_if_available
    }
```

### 4. **Partial Failures**
```python
# If pod enrichment fails, still return deployment data
context = EnrichedContext()
context.pod_data = {"error": "Failed to retrieve pods"}
context.deployment_data = successful_deployment_data
context.errors.append("Pod enrichment failed: permission denied")
```

## Testing Strategy

### Unit Tests
1. **Mock K8s API responses** - Test each enrichment function independently
2. **Error scenarios** - Test RBAC, 404, timeout handling
3. **Resource extraction** - Test filtering by resource names
4. **Time range filtering** - Test event/log filtering by time
5. **AWS call limiting** - Test that max 3 AWS calls are made

### Integration Tests
1. **End-to-end enrichment** - Full enrichment plan execution
2. **Parallel execution** - Multiple enrichments at once
3. **Graceful degradation** - Partial failures don't block response
4. **Performance** - Enrichment completes within 10 seconds

## Data Flow Example

```
User Query: "Why is pod my-app-12345 in namespace production crashing?"
    ↓
QueryRouter classifies as: POD_ISSUE
    ↓
EnrichmentPlan created:
    - categories: [POD_ISSUE]
    - resource_names: ["my-app-12345"]
    - namespaces: ["production"]
    ↓
EnrichmentEngine executes:
    1. Read K8sGPT Results (parallel)
    2. Get pod status for "my-app-12345" (parallel)
    3. Get pod events (parallel)
    4. Get pod logs (parallel)
    ↓
EnrichedContext returned:
    {
        "k8sgpt_results": [...],
        "pod_data": {
            "pods": [{
                "name": "my-app-12345",
                "phase": "CrashLoopBackOff",
                "restart_count": 15,
                "last_termination": "OOMKilled",
                "logs": "Error: Cannot allocate memory"
            }]
        },
        "errors": []
    }
    ↓
LLM receives enriched context and generates response
```

## Implementation Checklist

- [x] Create `EnrichedContext` dataclass
- [x] Implement `EnrichmentEngine` class
- [x] Implement `_enrich_pods()` with error handling
- [x] Implement `_enrich_deployments()` with error handling
- [x] Implement `_enrich_services()` with error handling
- [x] Implement `_enrich_nodes()` with error handling
- [x] Implement `_enrich_storage()` with error handling
- [x] Implement `_enrich_argocd()` with error handling
- [x] Implement `_enrich_security()` with error handling
- [x] Implement `_enrich_aws()` with 3-call limit
- [x] Implement parallel execution with asyncio
- [x] Implement timeout protection
- [x] Add comprehensive error handling
- [x] Create unit tests (40+ test cases)
- [ ] Create integration tests
- [ ] Add performance benchmarks

## Key Decisions

### 1. **Async vs Sync**
**Decision:** Use async/await for parallel API calls
**Reason:** Significant performance improvement (10s → 2s for multiple enrichments)

### 2. **Error Handling**
**Decision:** Graceful degradation with partial data
**Reason:** Better UX - partial answer is better than no answer

### 3. **AWS Call Limit**
**Decision:** Hard limit of 3 calls with priority ordering
**Reason:** Cost control and performance

### 4. **Data Structure**
**Decision:** Structured dict with consistent schema
**Reason:** Easy to serialize, validate, and template

### 5. **Caching**
**Decision:** No caching in enrichment engine (handled at API level)
**Reason:** Simpler implementation, fresher data

## Questions to Consider

1. **Should we cache enriched data?**
   - Pro: Faster subsequent queries
   - Con: Stale data, memory usage
   - **Recommendation:** No caching, rely on K8s client caching

2. **How to handle very large log outputs?**
   - **Recommendation:** Limit to last 100 lines, or time-filtered

3. **Should we enrich all namespaces or just specified ones?**
   - **Recommendation:** Only specified namespaces, default to "default" if none specified

4. **How to handle clusters with 1000+ pods?**
   - **Recommendation:** Limit to 20 pods, prioritize by resource names or recent events

5. **Should we include metrics (CPU/memory usage)?**
   - **Recommendation:** Yes, if metrics-server is available, but don't fail if not

This plan provides a solid foundation for implementing a robust, performant, and user-friendly enrichment engine. Ready to implement?
