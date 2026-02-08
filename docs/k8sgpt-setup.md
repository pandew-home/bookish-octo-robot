# K8sGPT Setup Guide

This guide explains how to install and configure K8sGPT in your Kubernetes clusters for testing the DevOps Chatbot v2.

## Overview

The K8sGPT Operator must be deployed to each EKS cluster you want to monitor. It continuously analyzes cluster resources and produces Result CRDs that the chatbot reads for health monitoring and troubleshooting.

For detailed information, see the [K8sGPT README](../k8sgpt/README.md).

## Prerequisites

- Kubernetes cluster (EKS, GKE, AKS, or local)
- kubectl configured to access the cluster
- Helm 3.x installed
- OpenAI API key (or other AI backend)

## Quick Start

```bash
# 1. Create AI backend secret
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system

# 2. Deploy via ArgoCD
kubectl apply -f k8sgpt/argocd-application.yaml

# 3. Create K8sGPT instance
kubectl apply -f k8sgpt/k8sgpt-cr.yaml

# 4. Verify deployment
kubectl get results -n k8sgpt-operator-system
```

## Installation Steps

### 1. Add K8sGPT Helm Repository

```bash
helm repo add k8sgpt https://charts.k8sgpt.ai/
helm repo update
```

### 2. Create Namespace

```bash
kubectl create namespace k8sgpt-operator-system
```

### 3. Create Secret for AI Backend

For OpenAI:

```bash
kubectl create secret generic k8sgpt-secret \
  --from-literal=openai-api-key=<your-openai-api-key> \
  -n k8sgpt-operator-system
```

For Azure OpenAI:

```bash
kubectl create secret generic k8sgpt-secret \
  --from-literal=azure-api-key=<your-azure-api-key> \
  -n k8sgpt-operator-system
```

### 4. Install K8sGPT Operator

```bash
helm install k8sgpt k8sgpt/k8sgpt-operator \
  --namespace k8sgpt-operator-system \
  --set ai.enabled=true \
  --set ai.backend=openai \
  --set ai.secret.name=k8sgpt-secret \
  --set ai.secret.key=openai-api-key
```

### 5. Create K8sGPT Custom Resource

Apply the K8sGPT CR to start analysis:

```bash
kubectl apply -f k8sgpt/k8sgpt-cr.yaml
```

### 6. Verify Installation

```bash
# Check operator pods
kubectl get pods -n k8sgpt-operator-system

# Check K8sGPT instance
kubectl get k8sgpt -n k8sgpt-operator-system

# Check results
kubectl get results -A
```

## Configuration

### K8sGPT Custom Resource

The K8sGPT CR configures what the operator analyzes. See [k8sgpt-cr.yaml](../k8sgpt/k8sgpt-cr.yaml) for the full configuration.

Key settings:
- **AI Backend**: OpenAI, Azure OpenAI, LocalAI, etc.
- **Model**: GPT model to use for analysis
- **Analyzers**: Which Kubernetes resources to analyze
- **Filters**: Exclude specific namespaces or resources
- **Sink**: Where to send results (webhook, S3, etc.)

### RBAC

The operator requires permissions to read cluster resources and create Result CRDs. See [rbac.yaml](../k8sgpt/rbac.yaml) for the required permissions.

### ArgoCD Integration

For GitOps-based deployment, use the ArgoCD Application manifest:

```bash
kubectl apply -f k8sgpt/argocd-application.yaml
```

This enables:
- Automated deployment and updates
- Configuration drift detection
- Rollback capabilities
- Multi-cluster management

## Troubleshooting

### No Results Generated

**Problem**: `kubectl get results -A` returns no results

**Solution**:
1. Check operator logs: `kubectl logs -n k8sgpt-operator-system -l app=k8sgpt-operator`
2. Verify AI backend secret exists and is valid
3. Check K8sGPT CR status: `kubectl describe k8sgpt -n k8sgpt-operator-system`
4. Ensure analyzers are enabled in the CR

### API Rate Limiting

**Problem**: Operator hitting OpenAI rate limits

**Solution**:
1. Use a higher-tier OpenAI account
2. Configure rate limiting in the K8sGPT CR
3. Consider using a local AI backend (LocalAI, Ollama)
4. Enable result caching with Redis

### High Costs

**Problem**: Unexpected OpenAI API costs

**Solution**:
1. Use cost-efficient models (gpt-3.5-turbo, gpt-4o-mini)
2. Limit analyzers to critical resources only
3. Increase analysis interval
4. Use filters to exclude noisy namespaces
5. Consider self-hosted AI backends

## Advanced Configuration

### Redis Caching

Enable Redis caching to reduce API calls:

```bash
helm install k8sgpt k8sgpt/k8sgpt-operator \
  --namespace k8sgpt-operator-system \
  --set ai.enabled=true \
  --set redis.enabled=true \
  --set redis.host=redis-service \
  --set redis.port=6379
```

### Custom Analyzers

Create custom analyzers for application-specific resources. See the [K8sGPT documentation](https://docs.k8sgpt.ai/) for details.

### Webhook Integration

Send results to external systems:

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: K8sGPT
metadata:
  name: k8sgpt-sample
spec:
  sink:
    type: webhook
    webhook:
      url: https://your-webhook-endpoint.com
      headers:
        Authorization: Bearer <token>
```

## References

- [K8sGPT Documentation](https://docs.k8sgpt.ai/)
- [K8sGPT GitHub](https://github.com/k8sgpt-ai/k8sgpt)
- [K8sGPT Operator GitHub](https://github.com/k8sgpt-ai/k8sgpt-operator)
