# K8sGPT Result CRD Structure and Analysis

## Overview

K8sGPT is a tool that scans Kubernetes clusters for issues and creates Result Custom Resource Definitions (CRDs) containing diagnostic information. This document explains the CRD structure and how our system processes them.

## K8sGPT Result CRD Structure

### API Group and Version
- **Group**: `core.k8sgpt.ai`
- **Version**: `v1alpha1`
- **Kind**: `Result`
- **Plural**: `results`

### CRD Schema

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: <result-name>
  namespace: <namespace>
  creationTimestamp: "2024-01-15T10:30:00Z"
spec:
  kind: <resource-kind>          # Pod, Deployment, Service, etc.
  name: <resource-name>          # Name of the affected resource
  namespace: <resource-namespace>
  details: <problem-description> # Human-readable problem description
  error:                         # List of error messages
    - "Error message 1"
    - "Error message 2"
  backend: <ai-backend>          # openai, azureopenai, localai, etc.
status:
  # Status information (if any)
```

### Example: Pod CrashLoopBackOff

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: default-nginx-pod-crashloopbackoff
  namespace: default
  creationTimestamp: "2024-01-15T10:30:00Z"
spec:
  kind: Pod
  name: nginx-pod
  namespace: default
  details: "Pod is in CrashLoopBackOff state"
  error:
    - "Container 'nginx' failed with exit code 1"
    - "Last termination reason: Error"
    - "Solution: Check application logs for startup errors. Verify container image and configuration."
  backend: openai
```

### Example: Deployment Replica Issues

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: production-api-deployment-replicas
  namespace: production
  creationTimestamp: "2024-01-15T10:35:00Z"
spec:
  kind: Deployment
  name: api-deployment
  namespace: production
  details: "Deployment has 0/3 replicas available"
  error:
    - "Desired replicas: 3, Available: 0"
    - "Pods are failing to start due to ImagePullBackOff"
    - "Solution: Verify image name and registry credentials. Check imagePullSecrets."
  backend: openai
```

### Example: Service Without Endpoints

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: default-frontend-service-noendpoints
  namespace: default
  creationTimestamp: "2024-01-15T10:40:00Z"
spec:
  kind: Service
  name: frontend-service
  namespace: default
  details: "Service has no endpoints"
  error:
    - "No pods match the service selector"
    - "Selector: app=frontend, version=v1"
    - "Solution: Verify pod labels match service selector. Check if pods are running."
  backend: openai
```

## K8sGPT Analyzers

K8sGPT includes multiple analyzers that scan different resource types:

### Core Analyzers
1. **Pod Analyzer**: Detects pod issues
   - CrashLoopBackOff
   - ImagePullBackOff
   - OOMKilled
   - Pending state
   - Failed containers

2. **Deployment Analyzer**: Detects deployment issues
   - Replica unavailability
   - Rollout failures
   - Image pull errors
   - Resource constraints

3. **Service Analyzer**: Detects service issues
   - No endpoints
   - Selector mismatches
   - Port configuration errors

4. **Node Analyzer**: Detects node issues
   - NotReady state
   - Disk pressure
   - Memory pressure
   - Network unavailable

5. **PVC Analyzer**: Detects storage issues
   - Pending PVCs
   - Binding failures
   - Storage class issues

6. **Ingress Analyzer**: Detects ingress issues
   - Backend service errors
   - TLS configuration issues
   - Path routing problems

7. **StatefulSet Analyzer**: Detects statefulset issues
   - Pod management errors
   - Volume claim issues
   - Update strategy problems

8. **NetworkPolicy Analyzer**: Detects network policy issues
   - Policy conflicts
   - Selector mismatches

## Our Implementation

### Reading Results

Our `K8sGPTReader` class reads Result CRDs using the Kubernetes CustomObjectsApi:

```python
# Read all results from cluster
results = await reader.read_results()

# Read from specific namespace
results = await reader.read_results(namespace='production')

# Filter by severity
results = await reader.read_results(severity_filter='high')
```

### Parsing Results

The `_parse_result()` method extracts and structures the data:

1. **Extract metadata**: name, namespace, timestamp
2. **Extract spec fields**: kind, resource name, details, errors, backend
3. **Determine severity**: Based on problem content
   - High: crashloopbackoff, imagepullbackoff, oomkilled, failed, error, critical
   - Low: warning, pending, info, notice, deprecated
   - Medium: Everything else

4. **Parse solutions**: Look for solution indicators in error messages
5. **Build structured result**: K8sGPTResult dataclass

### Severity Detection Logic

```python
def _determine_severity(problem: str, kind: str) -> str:
    problem_lower = problem.lower()
    
    # High severity indicators
    if any(indicator in problem_lower for indicator in [
        'crashloopbackoff', 'imagepullbackoff', 'oomkilled',
        'failed', 'error', 'critical', 'down', 'unavailable'
    ]):
        return 'high'
    
    # Low severity indicators
    if any(indicator in problem_lower for indicator in [
        'warning', 'pending', 'info', 'notice', 'deprecated'
    ]):
        return 'low'
    
    # Default to medium
    return 'medium'
```

## Weather State Calculation

Our `WeatherCalculator` translates K8sGPT results into intuitive weather states:

### Weather Classification Rules

| Weather State | Conditions |
|--------------|------------|
| ☀️ **Sunny** | 0 issues |
| 🌤️ **Partly Cloudy** | 1-2 low severity issues |
| ☁️ **Cloudy** | 3-5 low severity OR 1-2 medium severity |
| 🌧️ **Rainy** | 6+ low severity OR 3+ medium severity OR 1 high severity |
| ⛈️ **Stormy** | 2+ high severity OR 10+ total issues |

### Example Weather Calculation

```python
# Scenario: 1 high severity, 2 medium severity, 3 low severity
severity_counts = {'high': 1, 'medium': 2, 'low': 3}
total_count = 6

# Result: RAINY (1 high severity triggers rainy state)
weather_state = calculator._determine_weather_state(severity_counts, total_count)
```

## Integration with Enrichment Engine

The enrichment engine reads K8sGPT results as part of query processing:

```python
# In enrichment_engine.py
async def _enrich_general(self, query_info: dict, k8s_clients: dict) -> dict:
    """General health enrichment includes K8sGPT results."""
    
    # Read K8sGPT Result CRDs
    k8sgpt_results = await self._read_k8sgpt_results(k8s_clients)
    
    # Format for LLM context
    formatted_results = [
        self._format_k8sgpt_result(result)
        for result in k8sgpt_results
    ]
    
    return {
        'k8sgpt_results': formatted_results,
        'result_count': len(formatted_results)
    }
```

## API Endpoints Using K8sGPT Results

### 1. Weather Endpoint (GET /api/weather)

Returns cluster health overview:

```json
{
  "weather_state": "rainy",
  "cluster_name": "production-eks",
  "cluster_version": "1.28",
  "k8sgpt_result_count": 5,
  "top_issues": [
    {
      "name": "default-nginx-pod-crashloopbackoff",
      "kind": "Pod",
      "namespace": "default",
      "severity": "high",
      "problem": "Pod is in CrashLoopBackOff state",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ],
  "cluster_tools": [
    {
      "name": "k8sgpt",
      "version": "0.3.0",
      "status": "running"
    }
  ],
  "timestamp": "2024-01-15T10:45:00Z"
}
```

### 2. Results Endpoint (GET /api/results)

Lists all K8sGPT results with filtering:

```json
{
  "results": [
    {
      "name": "default-nginx-pod-crashloopbackoff",
      "kind": "Pod",
      "namespace": "default",
      "severity": "high",
      "problem": "Pod is in CrashLoopBackOff state",
      "solution": "Check application logs for startup errors",
      "analyzer": "openai",
      "timestamp": "2024-01-15T10:30:00Z",
      "details": {
        "resource_name": "nginx-pod",
        "error": ["Container failed with exit code 1"],
        "backend": "openai"
      }
    }
  ],
  "total_count": 5,
  "filtered_count": 1
}
```

### 3. Chat Endpoint (POST /api/chat)

Includes relevant K8sGPT results in LLM context:

```python
# Query: "Why is my nginx pod crashing?"

# System reads K8sGPT results
# Filters by relevance (pod name, namespace)
# Includes in LLM prompt:

"""
K8sGPT Analysis:
- Pod 'nginx-pod' in namespace 'default' is in CrashLoopBackOff
- Container failed with exit code 1
- Suggested solution: Check application logs for startup errors

Recent Events:
- Back-off restarting failed container
- Container terminated with exit code 1

Pod Logs (last 50 lines):
[application logs here]
"""
```

## Error Handling

### CRD Not Installed (404)

```python
# K8sGPT operator not installed in cluster
# Returns empty list, proceeds without K8sGPT context
results = []  # No error raised
```

### RBAC Permission Denied (403)

```python
# Service account lacks permission to read Result CRDs
# Logs error, returns user-friendly message
error_msg = "Permission denied. Unable to read K8sGPT results from cluster."
```

### No Results Found

```python
# K8sGPT hasn't found any issues (healthy cluster)
results = []
weather_state = WeatherState.SUNNY
```

## K8sGPT Operator Configuration

The K8sGPT operator is deployed per cluster with this configuration:

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: K8sGPT
metadata:
  name: k8sgpt
  namespace: k8sgpt-operator-system
spec:
  ai:
    enabled: true
    backend: openai  # or azureopenai, localai
    model: gpt-4o-mini
    secret:
      name: k8sgpt-secret
      key: openai-api-key
  noCache: false
  filters:
    - Pod
    - Deployment
    - Service
    - PersistentVolumeClaim
    - Node
    - Ingress
    - StatefulSet
  sink:
    type: slack  # Optional: send alerts to Slack
```

## Benefits of K8sGPT Integration

1. **Proactive Issue Detection**: Continuously scans cluster for problems
2. **AI-Powered Analysis**: Uses LLM to provide context and solutions
3. **Structured Data**: CRDs provide consistent, queryable format
4. **Multi-Cluster Support**: Each cluster has its own K8sGPT operator
5. **Real-Time Updates**: Results update as cluster state changes
6. **Reduced MTTR**: Faster issue identification and resolution

## Future Enhancements

1. **Custom Analyzers**: Add domain-specific analyzers for custom resources
2. **Severity Tuning**: Allow users to customize severity thresholds
3. **Alert Integration**: Trigger alerts based on weather state changes
4. **Historical Tracking**: Store result history for trend analysis
5. **Auto-Remediation**: Trigger automated fixes for common issues
