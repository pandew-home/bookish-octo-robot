# DevOps Chatbot v2.0

A Kubernetes-native troubleshooting assistant that provides real-time cluster health monitoring, RAG-powered chat, and a shared team knowledge base. The system uses Kion AWS credentials for simplified authentication and integrates with K8sGPT Operator for automated cluster diagnostics.

## Key Features

- **Simplified Authentication**: Single credential source (Kion) for both K8s and AWS APIs
- **Real-Time Health Monitoring**: Weather widget shows cluster health based on K8sGPT diagnostics
- **RAG-Powered Chat**: Semantic search over team knowledge base for troubleshooting guidance
- **Multi-Cluster Support**: Switch between clusters with a single app deployment
- **Shared Knowledge Base**: Team-wide solutions stored on shared PVC
- **Deterministic Routing**: Pattern-based query classification for targeted context enrichment
- **Cost Optimization**: Caching, small models, and limited API calls

## Quick Start

### Prerequisites

1. **Kion Access**: AWS credential management system providing temporary credentials
2. **EKS Clusters**: One or more EKS clusters to monitor and troubleshoot
3. **K8sGPT Operator**: Deployed per monitored cluster (see [K8sGPT Setup](docs/k8sgpt-setup.md))
4. **LLM API Key**: OpenAI, Anthropic, or Ollama endpoint
5. **Kubernetes Cluster**: For deploying the chatbot application (can be one of the monitored clusters)

### Local Development

```bash
# Clone repository
git clone <repository-url>
cd bookish-octo-robot

# Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup frontend
cd ../frontend
npm install

# Configure environment
cp .env.example .env
# Edit .env with your LLM_API_KEY and DEFAULT_REGION

# Start services
cd ../backend && uvicorn app:app --reload --port 8000 &
cd ../frontend && npm start
```

For detailed setup instructions, see the [Development Guide](docs/development.md).

### K8sGPT Operator Setup

Deploy K8sGPT to each cluster you want to monitor:

```bash
kubectl create secret generic k8sgpt-ai-secret \
  --from-literal=openai-api-key=sk-... \
  -n k8sgpt-operator-system

kubectl apply -f k8sgpt/argocd-application.yaml
kubectl apply -f k8sgpt/k8sgpt-cr.yaml
```

For detailed instructions, see the [K8sGPT Setup Guide](docs/k8sgpt-setup.md).

### Deployment to Kubernetes

```bash
# Build and push image
DOCKER_BUILDKIT=1 docker build -t devops-chatbot:v2.0 .
docker push devops-chatbot:v2.0

# Deploy to cluster
kubectl create namespace devops-chatbot
kubectl create secret generic devops-chatbot-secrets \
  --from-literal=llm-api-key=sk-... \
  -n devops-chatbot
kubectl apply -f k8s/
```

For detailed deployment instructions, see the [Deployment Guide](docs/deployment.md).

## Documentation

- **[Architecture](docs/architecture.md)** - System design and components
- **[Development](docs/development.md)** - Local setup and testing
- **[Deployment](docs/deployment.md)** - Kubernetes deployment guide
- **[K8sGPT Setup](docs/k8sgpt-setup.md)** - K8sGPT Operator installation
- **[Security](docs/security.md)** - Security features and best practices
- **[Usage](docs/usage.md)** - How to use the chatbot

## Usage

1. **Login** with Kion AWS credentials
2. **Select** a target EKS cluster
3. **Monitor** cluster health via the weather widget
4. **Ask** questions about cluster issues
5. **Save** helpful solutions to the knowledge base

For detailed usage instructions, see the [Usage Guide](docs/usage.md).









## Contributing

Contributions are welcome! See the [Development Guide](docs/development.md) for setup instructions.

## License

See [LICENSE](LICENSE) file.
