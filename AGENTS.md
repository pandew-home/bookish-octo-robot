# Agent Requirements

## Required Tools

### spec-kit (v0.4.3)
Spec-Driven Development is required for all new features.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install spec-kit
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.4.3
```

## Development Workflow

1. `/speckit.constitution` - View project principles
2. `/speckit.specify` - Define requirements
3. `/speckit.plan` - Create technical plan
4. `/speckit.tasks` - Generate task list
5. `/speckit.implement` - Execute implementation

## Project Context

- k8sgpt operator runs cluster analyzers every few minutes
- Grafana dashboard + in-cluster chatbot for troubleshooting
- **Product is READ-ONLY** - never modifies the cluster
- Development/test clusters: agents have full access for testing
- Production: read-only enforced via RBAC
