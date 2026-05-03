"""DevOps RAG library — slim layer over the LLM client and FAISS store."""

from devops_rag.rag_engine import RAGEngine
from devops_rag.llm_client import (
    LLMClientBase,
    OpenAIClient,
    AnthropicClient,
    OllamaClient,
)
from devops_rag.vector_store import VectorStore

__all__ = [
    "RAGEngine",
    "LLMClientBase",
    "OpenAIClient",
    "AnthropicClient",
    "OllamaClient",
    "VectorStore",
]
__version__ = "0.2.0"
