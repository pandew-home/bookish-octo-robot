# Development

Local setup, tests, and layout. Agent rules: [../AGENTS.md](../AGENTS.md).

## Setup

### Clone

```bash
git clone https://github.com/pandew-home/bookish-octo-robot.git
cd bookish-octo-robot
git checkout main
```

### Backend

```bash
cd backend
python3 -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

pip install -r requirements.txt
pip install -e ../libs/devops-k8s
pip install -e ../libs/devops-rag

uvicorn app:app --reload --port 8000
```

Prompts live under `backend/prompts/` (no separate `libs/devops-prompts` package).

### Frontend

```bash
cd frontend
npm install
npm start
# Dev server proxies /api → localhost:8000
```

### Environment

```bash
LLM_API_KEY=sk-...
DEFAULT_REGION=us-east-1
LLM_PROVIDER=openai          # or openrouter, etc.
LLM_MODEL=gpt-4o-mini
MEMORY_BACKEND=noop          # or vestige when Vestige is up
# VESTIGE_HTTP_URL=http://localhost:3928
# IN_CLUSTER_EKS_CLUSTER_NAME=my-cluster
```

| Surface | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |

## Testing

```bash
# Backend
cd backend && pytest
pytest --cov=. --cov-report=html
pytest tests/test_credential_store.py

# Frontend unit
cd frontend && npm test -- --no-watch
npm test -- --coverage

# Frontend e2e
cd frontend
npx playwright install   # first time
npx playwright test
# Specs: frontend/e2e/; set BASE_URL for deployed stack
```

## Project structure

```
bookish-octo-robot/
├── AGENTS.md
├── argocd/                   # App-of-apps GitOps
├── helm/                     # Charts
├── backend/                  # FastAPI, agent, memory, skills
├── frontend/                 # React + Playwright e2e
├── libs/devops-k8s|devops-rag
├── k8s/                      # Legacy/reference manifests
├── k8sgpt/                   # Operator/Alloy notes
├── .github/workflows/
├── docs/
└── Dockerfile
```

## Contributing

1. Branch from `main`.  
2. Small PRs; run backend + frontend tests.  
3. Update docs/AGENTS when behavior or GitOps paths change.  
4. No secrets or coverage HTML trees in git.  
5. Do not reintroduce Flux.

## Style

- **Python:** PEP 8, type hints.  
- **TypeScript:** strict, ESLint, small components/hooks.  
- **Helm/YAML:** 2-space; security context and resources explicit.

## Debugging

- Backend: `DEBUG=true` / `LOG_LEVEL=DEBUG`; `/docs`.  
- Frontend: DevTools; network for `/api/*` and session cookie.  
- Cluster: `kubectl logs -n devops-chatbot deploy/devops-chatbot`; Argo app sync.

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Usage](usage.md)
