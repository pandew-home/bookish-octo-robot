# K8sGPT Operator Deployment

This directory contains Kubernetes manifests for deploying the K8sGPT Operator to monitored EKS clusters. The K8sGPT Operator continuously analyzes cluster resources and produces diagnostic Result CRDs that the DevOps Chatbot reads for troubleshooting assistance.

## Architecture

The K8sGPT Operator is deployed **per cluster** (dev, staging, prod) and runs independently from the DevOps Chatbot application. It:

1. Continuously scans cluster resources (Pods, Deployments, Services, etc.)
2. Detects issues using built-in analyzers
3. Generates AI-powered diagnostic explanations using GPT-4o-mini
4. Stores results as Kubernetes Custom Resources (Result CRDs)
5. The DevOps Chatbot reads these Result CRDs remotely using user credentials

## Files

- **argocd-application.yaml**: ArgoCD Application manifest for GitOps deployment
- **k8sgpt-cr.yaml**: K8sGPT Custom Resource configuration
- **rbac.yaml**: RBAC permissions for the operator
- **secret-template.yaml**: Template for AI backend credentials (see below)
- **ALLOY_INTEGRATION.md**: Guide for integrating K8sGPT with Grafana Alloy for observability and cleanup
- **alloy-k8sgpt-integration.yaml**: Alloy configuration for scraping and cleanup
- **alloy-rbac.yaml**: RBAC for Alloy to access K8sGPT CRDs
- **alloy-configmap.yaml**: ConfigMap with cleanup scripts for Alloy
- **alloy-cleanup-script.sh**: Standalone cleanup script

## Prerequisites

1. **EKS Cluster**: Target cluster where K8sGPT will be deployed
2. **ArgoCD**: Installed in the cluster for GitOps deployment
3. **AI Backend Credentials**: OpenAI API key or AWS Bedrock access
4. **Namespace**: `k8sgpt-operator-system` (created automatically)

## Deployment Steps

### 1. Create AI Backend Secret

Choose one of the following based on your AI backend:

#### Option A: OpenAI (Default)

```bash
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system
```

#### Option B: Amazon Bedrock

```bash
# Create a JSON file with AWS credentials
cat > aws-creds.json <<EOF
{
  "access_key": "AKIA...",
  "secret_key": "...",
  "session_token": "...",
  "region": "us-east-1"
}
EOF

kubectl create secret generic k8sgpt-ai-secret \
  --from-file=aws-credentials=aws-creds.json \
  -n k8sgpt-operator-system

rm aws-creds.json
```

### 2. Deploy via ArgoCD

```bash
# Apply the ArgoCD Application manifest
kubectl apply -f argocd-application.yaml

# ArgoCD will automatically:
# - Create the k8sgpt-operator-system namespace
# - Install the K8sGPT Operator Helm chart
# - Apply RBAC permissions
# - Deploy the operator
```

### 3. Create K8sGPT Instance

```bash
# Apply the K8sGPT Custom Resource
kubectl apply -f k8sgpt-cr.yaml

# Verify the instance is running
kubectl get k8sgpt -n k8sgpt-operator-system
```

### 4. Verify Deployment

```bash
# Check operator pods
kubectl get pods -n k8sgpt-operator-system

# Check for Result CRDs
kubectl get results -n k8sgpt-operator-system

# View a specific result
kubectl get results -n k8sgpt-operator-system -o yaml
```

### 5. Deploy Grafana Alloy Integration (Recommended)

To prevent Result CRD accumulation and gain observability, integrate with Grafana Alloy:

**Benefits:**
- ✅ K8sGPT results in Loki alongside other logs
- ✅ Metrics and alerting in Prometheus/Grafana
- ✅ Automated cleanup (24-hour retention)
- ✅ No additional workloads needed

**Quick Start:**

```bash
# 1. Deploy RBAC for Alloy
kubectl apply -f alloy-rbac.yaml

# 2. Deploy cleanup scripts
kubectl apply -f alloy-configmap.yaml

# 3. Add Alloy configuration (see ALLOY_INTEGRATION.md)
# 4. Restart Alloy to pick up changes
kubectl rollout restart deployment/alloy -n monitoring
```

See **[ALLOY_INTEGRATION.md](./ALLOY_INTEGRATION.md)** for complete setup guide with:
- Detailed configuration steps
- Grafana dashboard queries
- Alerting examples
- Troubleshooting guide

## Configuration

### AI Backend Selection

Edit `k8sgpt-cr.yaml` to choose your AI backend:

**OpenAI (Default)**:
```yaml
ai:
  backend: openai
  model: gpt-4o-mini  # Cost-efficient
  secret:
    name: k8sgpt-ai-secret
    key: openai-api-key
```

**Amazon Bedrock**:
```yaml
ai:
  backend: amazonbedrock
  model: anthropic.claude-3-haiku-20240307-v1:0  # Cost-efficient
  region: us-east-1
  secret:
    name: k8sgpt-ai-secret
    key: aws-credentials
```

### Resource Filters

Configure which resources to analyze in `k8sgpt-cr.yaml`:

```yaml
filters:
  - Pod              # Pod issues (CrashLoopBackOff, ImagePullBackOff, etc.)
  - Service          # Service configuration issues
  - Deployment       # Deployment problems
  - ReplicaSet       # ReplicaSet issues
  - StatefulSet      # StatefulSet problems
  - PersistentVolumeClaim  # Storage issues
  - Ingress          # Ingress configuration
  - Node             # Node health
  - CronJob          # CronJob failures
  - NetworkPolicy    # Network policy issues
```

### Namespace Filtering

To scan specific namespaces only:

```yaml
# Scan all namespaces (default)
namespace: ""

# Scan specific namespace
namespace: "production"
```

### Performance Tuning

Enable remote caching for better performance:

```yaml
remoteCache:
  enabled: true
  backend: redis
  endpoint: redis-service:6379
```

## RBAC Permissions

The operator requires:

**Read-only access** to cluster resources:
- Pods, Services, Deployments, StatefulSets, DaemonSets
- ConfigMaps, Secrets (metadata only)
- Nodes, Namespaces, Events
- Ingresses, NetworkPolicies
- PVCs, StorageClasses
- RBAC resources (Roles, RoleBindings)
- ArgoCD Applications (optional)

**Read/write access** to:
- K8sGPT Result CRDs
- K8sGPT instance CRDs

See `rbac.yaml` for complete permissions.

## Integration with DevOps Chatbot

The DevOps Chatbot reads K8sGPT Result CRDs from remote clusters using:

1. **User Authentication**: Kion AWS credentials
2. **EKS Token Generation**: STS-based bearer tokens
3. **Remote CRD Reading**: Kubernetes API client with user credentials
4. **Weather Calculation**: Aggregates results to show cluster health
5. **Chat Enrichment**: Includes relevant results in troubleshooting responses

The operator runs independently and doesn't need to communicate with the chatbot directly.

## Monitoring

### Check Operator Logs

```bash
kubectl logs -n k8sgpt-operator-system -l app.kubernetes.io/name=k8sgpt-operator -f
```

### View Results

```bash
# List all results
kubectl get results -A

# View results with details
kubectl get results -A -o wide

# Get result details
kubectl describe result <result-name> -n k8sgpt-operator-system
```

### Metrics (Optional)

If Prometheus Operator is installed, enable ServiceMonitor in `argocd-application.yaml`:

```yaml
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
```

## Troubleshooting

### No Results Generated

1. Check operator logs for errors
2. Verify AI backend secret exists and is valid
3. Check RBAC permissions
4. Verify filters are configured correctly

### Permission Denied Errors

1. Verify RBAC manifests are applied: `kubectl apply -f rbac.yaml`
2. Check ClusterRoleBinding: `kubectl get clusterrolebinding k8sgpt-operator-rolebinding`
3. Verify ServiceAccount: `kubectl get sa k8sgpt-operator -n k8sgpt-operator-system`

### AI Backend Errors

**OpenAI**:
- Verify API key is valid
- Check quota limits
- Ensure network connectivity to api.openai.com

**Bedrock**:
- Verify AWS credentials have Bedrock permissions
- Check model availability in region
- Ensure IAM policy includes `bedrock:InvokeModel`

### High Costs

1. Reduce scanning frequency (not configurable in CR, but can adjust operator deployment)
2. Enable remote caching to reduce duplicate AI calls
3. Filter namespaces to scan only production workloads
4. Use cost-efficient models (gpt-4o-mini, claude-3-haiku)

## Uninstallation

```bash
# Delete K8sGPT instance
kubectl delete k8sgpt k8sgpt-instance -n k8sgpt-operator-system

# Delete Alloy integration (if deployed)
kubectl delete clusterrolebinding alloy-k8sgpt-reader-cleaner
kubectl delete clusterrole alloy-k8sgpt-reader-cleaner
kubectl delete serviceaccount alloy-k8sgpt -n monitoring
kubectl delete configmap alloy-k8sgpt-scripts alloy-k8sgpt-config -n monitoring

# Delete ArgoCD Application (will remove operator)
kubectl delete application k8sgpt-operator -n argocd

# Delete namespace (if needed)
kubectl delete namespace k8sgpt-operator-system
```

## References

- [K8sGPT Documentation](https://docs.k8sgpt.ai/)
- [K8sGPT Operator GitHub](https://github.com/k8sgpt-ai/k8sgpt-operator)
- [K8sGPT Helm Chart](https://github.com/k8sgpt-ai/k8sgpt-operator/tree/main/chart)
- [DevOps Chatbot v2 Design Document](../.kiro/specs/devops-chatbot-v2/design.md)
