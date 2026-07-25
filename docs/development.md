# Development Guide

Local setup, tests, and layout for DevOps Chatbot v2.0.

**Baseline tag:** `faiss-202607`. Agent-facing rules: [../AGENTS.md](../AGENTS.md).

## Local development setup

### 1. Clone

```bash
git clone https://github.com/pandew-home/bookish-octo-robot.git
cd bookish-octo-robot
git checkout main
# optional pin: git checkout faiss-202607
```

### 2. Backend

```bash
cd backend
python3 -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

pip install -r requirements.txt

# Shared libraries (paths are repo-root libs/, not backend/libs/)
pip install -e ../libs/devops-k8s
pip install -e ../libs/devops-kb
pip install -e ../libs/devops-rag

uvicorn app:app --reload --port 8000
```

There is **no** `libs/devops-prompts` package; prompts live under `backend/prompts/` (see `system.md`).

### 3. Frontend

```bash
cd frontend
npm install
npm start
# Dev server proxies /api → localhost:8000 (see frontend package config)
```

### 4. Environment

Create `.env` at repo root or export vars for the backend process:

```bash
LLM_API_KEY=sk-...
DEFAULT_REGION=us-east-1
LLM_PROVIDER=openai          # or openrouter, etc.
LLM_MODEL=gpt-4o-mini
KB_SEEDING_ENABLED=true
KB_FORCE_RESEED=false
# Optional single-cluster:
# IN_CLUSTER_EKS_CLUSTER_NAME=my-cluster
# EKS_CLUSTER_NAME=my-cluster
```

### 5. Access

| Surface | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |

## Testing

### Backend

```bash
cd backend
pytest
pytest --cov=. --cov-report=html
pytest -k "property"
pytest tests/test_credential_store.py
```

### Frontend unit

```bash
cd frontend
npm test -- --no-watch
npm test -- --coverage
npm test -- src/components/LoginForm.test.tsx
```

### Frontend e2e (Playwright)

```bash
cd frontend
npx playwright install   # first time
npx playwright test
```

Specs live under `frontend/e2e/`. Point `BASE_URL` at a running stack when testing against deploy.

### Workflow lint

```bash
# See .github/workflows/workflow-lint.yml for CI expectations
```

## Project structure

```
bookish-octo-robot/
├── AGENTS.md                 # Rules for coding agents
├── argocd/                   # App-of-apps GitOps
├── helm/                     # Charts (chatbot, k8sgpt-instance, alloy-extras, dashboards)
├── backend/
│   ├── api/                  # credentials, clusters, chat, weather, solutions
│   ├── skills/               # SKILL.md packs for the agent
│   ├── prompts/system.md     # System prompt
│   ├── agentic_engine.py
│   ├── agent_tools.py
│   ├── rag_integration.py
│   ├── k8sgpt_reader.py
│   ├── weather_calculator.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/                  # components, hooks, types
│   ├── e2e/                  # Playwright
│   └── playwright.config.ts
├── libs/
│   ├── devops-k8s/
│   ├── devops-kb/
│   └── devops-rag/
├── k8s/                      # Legacy/reference manifests
├── k8sgpt/                   # Operator/Alloy docs & fixtures
├── .github/workflows/
├── docs/
└── Dockerfile
```

## Contributing

1. Branch from `main`.  
2. Prefer small PRs; run backend + frontend tests.  
3. Update docs/AGENTS when behavior or GitOps paths change.  
4. Do not commit secrets, FAISS index dumps, or coverage HTML trees.  
5. Do not reintroduce Flux.

## Code style

- **Python:** PEP 8, type hints, focused modules.  
- **TypeScript:** strict mode, ESLint, small components/hooks.  
- **Helm/YAML:** 2-space; security context and resources explicit.

## Debugging

- Backend: `DEBUG=true` / `LOG_LEVEL=DEBUG`; use `/docs`.  
- Frontend: React DevTools; network tab for `/api/*` and session cookie.  
- Cluster: `kubectl logs -n devops-chatbot deploy/devops-chatbot`; check Argo CD app sync.

## Related

- [Architecture](architecture.md) · [Deployment](deployment.md) · [Usage](usage.md)
