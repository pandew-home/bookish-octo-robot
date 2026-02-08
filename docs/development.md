# Development Guide

This guide covers local development setup and testing for DevOps Chatbot v2.0.

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd bookish-octo-robot
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install shared libraries in editable mode
pip install -e ./libs/devops-k8s
pip install -e ./libs/devops-kb
pip install -e ./libs/devops-prompts
pip install -e ./libs/devops-rag
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

### 4. Environment Configuration

Create a `.env` file in the root directory:

```bash
# Required
LLM_API_KEY=sk-...
DEFAULT_REGION=us-east-1

# Optional
KB_SEEDING_ENABLED=true
KB_FORCE_RESEED=false
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
```

See [Environment Variables](deployment.md#environment-variables) for all options.

### 5. Start Backend

```bash
cd backend
uvicorn app:app --reload --port 8000
```

### 6. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run property-based tests only
pytest -k "property"

# Run specific test file
pytest tests/test_credential_store.py
```

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- src/components/LoginForm.test.tsx
```

## Project Structure

```
bookish-octo-robot/
├── backend/                 # FastAPI backend
│   ├── api/                # API endpoints
│   ├── middleware/         # Rate limiting, auth
│   ├── tests/              # Backend tests
│   ├── utils/              # Utilities and metrics
│   ├── app.py              # FastAPI application
│   ├── credential_store.py # Kion credential management
│   ├── eks_auth.py         # EKS token generation
│   ├── cluster_manager.py  # Cluster discovery
│   ├── query_router.py     # Query classification
│   ├── enrichment_engine.py # Context enrichment
│   ├── k8sgpt_reader.py    # K8sGPT CRD reading
│   ├── weather_calculator.py # Health monitoring
│   ├── rag_integration.py  # RAG engine
│   ├── template_engine.py  # Prompt templates
│   ├── conversation_history.py # History management
│   ├── solution_manager.py # Knowledge base
│   ├── input_sanitizer.py  # Input validation
│   ├── response_parser.py  # Response parsing
│   ├── startup_validator.py # Startup checks
│   └── requirements.txt    # Python dependencies
├── frontend/               # React frontend
│   ├── public/            # Static assets
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom hooks
│   │   ├── types/         # TypeScript types
│   │   ├── utils/         # Utilities
│   │   ├── App.tsx        # Main app component
│   │   └── index.tsx      # Entry point
│   ├── package.json       # Node dependencies
│   └── tsconfig.json      # TypeScript config
├── libs/                  # Shared libraries
│   ├── devops-k8s/       # Kubernetes utilities
│   ├── devops-kb/        # Knowledge base
│   ├── devops-prompts/   # Prompt templates
│   └── devops-rag/       # RAG engine
├── k8s/                   # Kubernetes manifests
├── k8sgpt/               # K8sGPT Operator manifests
├── docker/               # Docker configuration
├── docs/                 # Documentation
├── Dockerfile           # Multi-stage build
└── .env                 # Environment variables
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest` (backend) and `npm test` (frontend)
5. Submit a pull request

## Code Style

### Backend (Python)
- Follow PEP 8
- Use type hints
- Write docstrings for public functions
- Keep functions focused and small

### Frontend (TypeScript)
- Follow ESLint rules
- Use TypeScript strict mode
- Write JSDoc comments for complex functions
- Keep components focused and reusable

## Debugging

### Backend Debugging
- Enable debug logging: `DEBUG=true`
- Use FastAPI's interactive docs: http://localhost:8000/docs
- Check logs for detailed error messages

### Frontend Debugging
- Use React DevTools browser extension
- Check browser console for errors
- Use network tab to inspect API calls

## Common Development Tasks

### Adding a New API Endpoint
1. Create endpoint in `backend/api/`
2. Add route to `backend/app.py`
3. Write tests in `backend/tests/`
4. Update API documentation

### Adding a New Frontend Component
1. Create component in `frontend/src/components/`
2. Write tests in same directory
3. Export from component index
4. Use in parent components

### Updating Shared Libraries
1. Make changes in `libs/` directory
2. Reinstall in editable mode: `pip install -e ./libs/<library>`
3. Test changes in backend
4. Update version in `setup.py`

## Technical Documentation

For detailed implementation documentation, see:

### Backend
- [Authentication Flow](../backend/AUTHENTICATION_FLOW.md)
- [Enrichment Engine](../backend/ENRICHMENT_ENGINE_SUMMARY.md)
- [Error Handling & Observability](../backend/ERROR_HANDLING_OBSERVABILITY_SUMMARY.md)
- [K8sGPT Implementation](../backend/K8SGPT_IMPLEMENTATION_SUMMARY.md)
- [RAG Error Handling](../backend/RAG_ERROR_HANDLING.md)
- [Startup Validation](../backend/STARTUP_VALIDATION_SUMMARY.md)
- [Template Query Mapping](../backend/TEMPLATE_QUERY_MAPPING.md)

### Docker
- [Build Optimization](../docker/BUILD_OPTIMIZATION.md)
- [Optimization Summary](../docker/OPTIMIZATION_SUMMARY.md)
