# devops-rag

LLM client abstraction for the DevOps chatbot agentic loop.

Providers:

- OpenAI-compatible (`OpenAIClient`, including OpenRouter)
- Anthropic (`AnthropicClient`)
- Ollama (`OllamaClient`)

Institutional memory is **not** in this package — use Vestige via `backend/memory` (MemoryPort).

## Install

```bash
pip install -e ./libs/devops-rag
```

## Usage

```python
from devops_rag import OpenAIClient

client = OpenAIClient(api_key="...", model="gpt-4o-mini")
text = client.generate("Explain CrashLoopBackOff")
```
