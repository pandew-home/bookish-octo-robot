# Usage Guide

This guide covers how to use DevOps Chatbot v2.0 for Kubernetes troubleshooting.

## Getting Started

### 1. Authentication

1. Navigate to the application URL
2. Enter your Kion AWS credentials:
   - Access Key ID
   - Secret Access Key
   - Session Token
   - Region
3. Click "Login"

The system validates credentials via STS GetCallerIdentity and stores them with a 3600-second TTL.

### 2. Cluster Selection

1. After authentication, select a target cluster from the dropdown
2. The system discovers available clusters using EKS ListClusters
3. Selecting a cluster generates an EKS bearer token and configures the Kubernetes API client

## Features

### Health Monitoring

The **Weather Widget** displays real-time cluster health:

- ☀️ **Sunny**: No critical issues
- ⛅ **Partly Cloudy**: 1-2 low-severity issues
- ☁️ **Cloudy**: 3-5 issues or 1 medium-severity issue
- 🌧️ **Rainy**: 5-10 issues or multiple medium-severity issues
- ⛈️ **Stormy**: 10+ issues or any high-severity issues

The widget polls every 60 seconds and shows the top issues from K8sGPT diagnostics.

### Troubleshooting with Chat

1. Type your question in the chat interface
2. The system:
   - Classifies your query using pattern matching
   - Reads relevant K8sGPT Result CRDs
   - Makes targeted K8s/AWS API calls for context
   - Searches the knowledge base for similar solutions
   - Generates a response with the LLM
3. Review the response with:
   - Assessment and root cause analysis
   - Evidence from cluster data
   - Recommended fixes (preferring GitOps/IaC)
   - Safety notices for destructive operations
   - Verification commands
   - Related knowledge base articles

### Saving Solutions

1. Click "Save to KB" on helpful assistant messages
2. Fill in the solution form:
   - Title
   - Description
   - Tags
   - Optional: Runbook URL, automation script, estimated fix time
3. Submit to add to the shared knowledge base
4. Solutions are immediately available to all users via semantic search

### Switching Clusters

1. Select a different cluster from the dropdown
2. The system:
   - Generates a new bearer token
   - Reconfigures the Kubernetes API client
   - Switches to that cluster's conversation history
   - Clears cached cluster-specific data

## Query Examples

### Pod Issues
- "Why is my pod crashing?"
- "Show me pods in CrashLoopBackOff"
- "What's wrong with the nginx deployment?"

### Resource Issues
- "Why is my node running out of memory?"
- "Show me pods with high CPU usage"
- "What's causing the disk pressure?"

### Network Issues
- "Why can't my pod reach the database?"
- "Show me network policies affecting the frontend"
- "What's blocking traffic to the API?"

### Configuration Issues
- "Why is my ConfigMap not loading?"
- "Show me invalid RBAC permissions"
- "What's wrong with my service account?"

### General Questions
- "What's the health of my cluster?"
- "Show me all critical issues"
- "What should I investigate first?"

## Best Practices

### Query Formulation
- Be specific about the resource (pod name, namespace, etc.)
- Include error messages if available
- Mention recent changes or deployments
- Specify the expected vs actual behavior

### Solution Management
- Save solutions that helped you
- Use descriptive titles and tags
- Include runbook links when available
- Update solutions as they evolve

### Security
- Never share credentials in chat
- Don't paste sensitive data (API keys, passwords)
- Review commands before executing
- Use GitOps for configuration changes

### Cost Optimization
- Use specific queries to reduce LLM token usage
- Review knowledge base before asking
- Batch related questions
- Close unused conversations

## Troubleshooting

### No Clusters Available
- Verify Kion credentials are valid
- Check AWS region matches cluster region
- Ensure credentials have `eks:ListClusters` permission

### Weather Widget Shows "No Data"
- Verify K8sGPT Operator is deployed to cluster
- Check Result CRDs exist: `kubectl get results -A`
- Ensure credentials have permission to read CRDs

### Chat Not Responding
- Check backend logs for errors
- Verify LLM API key is valid
- Ensure network connectivity to LLM provider

### Knowledge Base Not Working
- Verify PVC is mounted at `/data`
- Check KB seeding completed in logs
- Ensure FAISS index exists

## Advanced Features

### Custom Analyzers
Configure K8sGPT to analyze custom resources specific to your applications.

### Webhook Integration
Send K8sGPT results to external systems (Slack, PagerDuty, etc.).

### Multi-Cluster Management
Monitor multiple clusters from a single chatbot deployment.

### Team Collaboration
Share solutions and best practices via the knowledge base.

## References

- [Architecture](architecture.md)
- [Deployment](deployment.md)
- [K8sGPT Setup](k8sgpt-setup.md)
- [Security](security.md)
