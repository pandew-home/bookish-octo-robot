"""DevOps RAG engine library."""

from devops_rag.rag_engine import RAGEngine
from devops_rag.llm_client import LLMClient, LLMClientBase, OpenAIClient, AnthropicClient, OllamaClient
from devops_rag.vector_store import VectorStore
from devops_rag.embeddings import EmbeddingCache
from devops_rag.api_reference_builder import APIReferenceBuilder
from devops_rag.aws_mcp_client import AWSMCPClient, AWSClusterContext, format_aws_context
from devops_rag.k8sgpt_mcp_client import K8sGPTMCPClient, K8sGPTAnalysis, format_k8sgpt_analysis

__all__ = [
    "RAGEngine",
    "LLMClient",
    "LLMClientBase",
    "OpenAIClient",
    "AnthropicClient",
    "OllamaClient",
    "VectorStore",
    "EmbeddingCache",
    "APIReferenceBuilder",
    "AWSMCPClient",
    "AWSClusterContext",
    "format_aws_context",
    "K8sGPTMCPClient",
    "K8sGPTAnalysis",
    "format_k8sgpt_analysis",
]
__version__ = "0.1.0"
