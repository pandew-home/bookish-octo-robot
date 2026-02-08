# devops-rag

RAG (Retrieval-Augmented Generation) engine for DevOps chatbot.

## Features

- FAISS vector store for semantic search
- Sentence-transformers for embeddings
- LLM client abstraction (OpenAI, Anthropic, Ollama)
- Embedding cache for cost optimization
- Response generation with citations

## Installation

```bash
pip install -e .
```

## Usage

```python
from devops_rag import RAGEngine, LLMClient

llm_client = LLMClient(provider="openai", api_key="...")
rag_engine = RAGEngine(llm_client=llm_client)

response = rag_engine.process_query("Why is my pod failing?")
print(response.content)
```
