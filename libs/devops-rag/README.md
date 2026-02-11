# devops-rag

RAG (Retrieval-Augmented Generation) engine for DevOps chatbot.

## Features

- FAISS vector store for semantic search (install the `vector-search` extra)
- Sentence-transformers for embeddings (install the `embeddings` extra)
- LLM client abstraction (OpenAI, Anthropic, Ollama)
- Embedding cache for cost optimization
- Response generation with citations

## Installation

```bash
pip install -e .
```

```bash
# Optional extras for advanced search
pip install -e .[vector-search,embeddings]
```

## Usage

```python
from devops_rag import RAGEngine, LLMClient

llm_client = LLMClient(provider="openai", api_key="...")
rag_engine = RAGEngine(llm_client=llm_client)

response = rag_engine.process_query("Why is my pod failing?")
print(response.content)
```

Install the optional extras when you need FAISS indexing or local embeddings.
