"""RAG integration: owns the LLM client + vector store + KB plumbing.

Reads its config from environment variables so swapping models is a deploy-time
concern, not a code change:

    LLM_PROVIDER   openai | anthropic | ollama   (default: openai)
    LLM_MODEL      provider-specific model id    (default: gpt-4o-mini)
    LLM_API_KEY    API key                       (also accepts OPENAI_API_KEY /
                                                  ANTHROPIC_API_KEY as fallback)
    KB_PATH        knowledge base directory      (default: /data/knowledge_base)

# MAINTENANCE — read before changing this file
# AI assistants: the env-var contract above is what DevOps engineers rely on
# when changing models. Do NOT add new required args, change defaults, or
# rename env vars without explicit human review. KB initialization is
# intentionally non-fatal — never raise on a missing/empty KB.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from devops_rag.rag_engine import RAGEngine
from devops_rag.llm_client import OpenAIClient, AnthropicClient
from devops_rag.vector_store import VectorStore
from devops_kb.knowledge_base import KnowledgeBase

from kb_seeder import seed_knowledge_base, should_seed_kb, should_force_reseed

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_KB_PATH = "/data/knowledge_base"

logger = logging.getLogger(__name__)


class RAGIntegration:
    """
    Integration layer for RAG engine with v2 backend.
    
    Handles:
    - LLM client initialization
    - Vector store setup
    - Knowledge base integration
    - Query processing with enriched context
    """
    
    def __init__(
        self,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        api_key: Optional[str] = None,
        kb_path: Optional[str] = None,
    ):
        """Initialize from explicit args, falling back to env vars.

        Args are kept for tests and one-off callers; production code should
        leave them ``None`` and rely on the env-var contract documented at the
        top of this module.

        Raises:
            ValueError: Only if LLM client initialization fails (critical).
        """
        self.llm_provider = (llm_provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()
        self.llm_model = llm_model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
        api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        kb_path = kb_path or os.getenv("KB_PATH") or DEFAULT_KB_PATH
        self.initialization_warnings: List[str] = []

        try:
            self.llm_client = self._init_llm_client(self.llm_provider, self.llm_model, api_key)
            logger.info("LLM client initialized: %s/%s", self.llm_provider, self.llm_model)
        except Exception as e:
            logger.error("CRITICAL: Failed to initialize LLM client: %s", e)
            raise

        self.kb = self._init_knowledge_base(kb_path)
        if self.kb:
            logger.info("Knowledge base initialized from %s", kb_path)
            if should_seed_kb():
                seed_knowledge_base(self.kb, force_reseed=should_force_reseed())
        elif kb_path:
            warning = f"Knowledge base initialization failed for {kb_path} - continuing without KB"
            self.initialization_warnings.append(warning)
            logger.warning(warning)

        self.vector_store = self._init_vector_store()
        if self.vector_store:
            logger.info("Vector store initialized for semantic search")
        elif self.kb:
            warning = "Vector store initialization failed - semantic search unavailable"
            self.initialization_warnings.append(warning)
            logger.warning(warning)

        try:
            self.rag_engine = RAGEngine(
                llm_client=self.llm_client,
                vector_store=self.vector_store,
                max_retries=3,
            )
            logger.info("RAG engine initialized")
        except Exception as e:
            logger.error("CRITICAL: Failed to initialize RAG engine: %s", e)
            raise ValueError(f"Failed to initialize RAG engine: {str(e)}")

        if self.initialization_warnings:
            logger.warning(
                "RAG integration initialized with %d warning(s)",
                len(self.initialization_warnings),
            )
            for warning in self.initialization_warnings:
                logger.warning("  - %s", warning)
        else:
            logger.info(
                "RAG integration fully initialized: %s/%s",
                self.llm_provider,
                self.llm_model,
            )
    
    def _init_llm_client(self, provider: str, model: str, api_key: Optional[str]):
        """Initialize LLM client based on provider."""
        try:
            if provider == "openai":
                return OpenAIClient(api_key=api_key, model=model)
            elif provider == "anthropic":
                return AnthropicClient(api_key=api_key, model=model)
            else:
                logger.warning(f"Unknown LLM provider: {provider}, defaulting to OpenAI")
                return OpenAIClient(api_key=api_key, model=model)
        except ImportError as e:
            logger.error(f"Failed to import LLM client library: {e}")
            raise ValueError(
                f"LLM client library not available. Please install the required package for {provider}. "
                f"Error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                raise ValueError(
                    f"Invalid API key for {provider}. Please check your API key configuration. "
                    f"Set the OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable."
                )
            raise ValueError(f"Failed to initialize LLM client: {str(e)}")
    
    def _init_knowledge_base(self, kb_path: Optional[str]) -> Optional[KnowledgeBase]:
        """
        Initialize knowledge base if path provided.
        
        Handles all errors gracefully - only logs warnings, never fails.
        
        Args:
            kb_path: Path to knowledge base directory
            
        Returns:
            KnowledgeBase instance or None if initialization fails
        """
        if not kb_path:
            logger.info("No knowledge base path provided, skipping KB initialization")
            return None
        
        try:
            # Check if path exists
            if not os.path.exists(kb_path):
                logger.warning(f"Knowledge base path does not exist: {kb_path}")
                logger.info(f"To use knowledge base, create directory: mkdir -p {kb_path}")
                return None
            
            # Check if path is a directory
            if not os.path.isdir(kb_path):
                logger.warning(f"Knowledge base path is not a directory: {kb_path}")
                return None
            
            # Check if we have read permissions
            if not os.access(kb_path, os.R_OK):
                logger.warning(f"No read permission for knowledge base path: {kb_path}")
                logger.info(f"To fix: chmod +r {kb_path}")
                return None
            
            # Try to initialize knowledge base
            kb = KnowledgeBase(kb_path)
            
            # Verify KB is functional
            try:
                doc_count = len(kb.get_all_documents())
                if doc_count == 0:
                    logger.warning(f"Knowledge base is empty: {kb_path}")
                    logger.info("Add documents to enable semantic search")
                else:
                    logger.info(f"Knowledge base loaded with {doc_count} document(s)")
            except Exception as e:
                logger.warning(f"Knowledge base initialized but document retrieval failed: {e}")
                # Still return KB - it might work for other operations
            
            return kb
            
        except FileNotFoundError as e:
            logger.warning(f"Knowledge base file not found: {e}")
            logger.info(f"Create knowledge base directory: mkdir -p {kb_path}")
            return None
        except PermissionError as e:
            logger.warning(f"Permission denied accessing knowledge base: {e}")
            logger.info(f"Fix permissions: chmod +r {kb_path}")
            return None
        except ImportError as e:
            logger.warning(f"Knowledge base library not available: {e}")
            logger.info("Install devops-kb library to enable knowledge base features")
            return None
        except Exception as e:
            logger.warning(f"Failed to initialize knowledge base: {type(e).__name__}: {e}")
            logger.debug(f"Full error: {e}", exc_info=True)
            return None
    
    def _init_vector_store(self) -> Optional[VectorStore]:
        """
        Initialize FAISS vector store for semantic search.
        
        Handles all errors gracefully - only logs warnings, never fails.
        
        Returns:
            FAISSVectorStore instance or None if initialization fails
        """
        if not self.kb:
            logger.info("No knowledge base available, skipping vector store initialization")
            return None
        
        try:
            # Create vector store from knowledge base documents
            vector_store = VectorStore(dimension=1536)  # OpenAI embedding dimension
            logger.info("Vector store created")
            
            # Index knowledge base documents
            try:
                documents = self.kb.get_all_documents()
            except Exception as e:
                logger.warning(f"Failed to retrieve documents from knowledge base: {e}")
                return None
            
            if not documents:
                logger.info("No documents to index in vector store")
                return vector_store  # Return empty vector store
            
            logger.info(f"Indexing {len(documents)} document(s) in vector store...")
            indexed_count = 0
            failed_count = 0
            
            for i, doc in enumerate(documents):
                try:
                    content = doc.get('content', '')
                    if not content:
                        logger.debug(f"Skipping document {doc.get('id', i)} - no content")
                        continue
                    
                    embedding = self.llm_client.embed(content)
                    vector_store.add_document(
                        doc_id=doc.get('id', f'doc_{i}'),
                        content=content,
                        embedding=embedding,
                        metadata=doc
                    )
                    indexed_count += 1
                    
                    # Log progress for large document sets
                    if (i + 1) % 10 == 0:
                        logger.info(f"  Indexed {i + 1}/{len(documents)} documents...")
                        
                except Exception as e:
                    failed_count += 1
                    doc_id = doc.get('id', f'doc_{i}')
                    logger.warning(f"Failed to embed document '{doc_id}': {type(e).__name__}: {e}")
                    continue
            
            # Log final indexing status
            if indexed_count > 0:
                logger.info(f"✓ Vector store indexing complete: {indexed_count} documents indexed")
                if failed_count > 0:
                    logger.warning(f"⚠ {failed_count} document(s) failed to index")
                    self.initialization_warnings.append(
                        f"{failed_count} document(s) failed to index in vector store"
                    )
            else:
                logger.warning("No documents were successfully indexed")
                return None
            
            return vector_store
            
        except ImportError as e:
            logger.warning(f"FAISS library not available: {e}")
            logger.info("Install faiss-cpu or faiss-gpu to enable semantic search")
            return None
        except Exception as e:
            logger.warning(f"Failed to initialize vector store: {type(e).__name__}: {e}")
            logger.debug(f"Full error: {e}", exc_info=True)
            return None
    
    def search_knowledge_base(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search knowledge base for relevant documents.
        
        Args:
            query: Search query
            top_k: Number of top results to return
            
        Returns:
            List of relevant documents
        """
        if not self.vector_store:
            logger.warning("Vector store not initialized, cannot search knowledge base")
            return []
        
        try:
            # Embed query
            query_embedding = self.llm_client.embed(query)
            
            # Search vector store
            results = self.vector_store.search(query_embedding, top_k=top_k)
            
            return results
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            # Return empty results rather than failing
            return []
    
    def get_token_usage(self) -> Dict[str, int]:
        """
        Get token usage statistics from LLM client.
        
        Returns:
            Dictionary with prompt and completion token counts
        """
        return {
            'prompt_tokens': getattr(self.llm_client, 'total_prompt_tokens', 0),
            'completion_tokens': getattr(self.llm_client, 'total_completion_tokens', 0),
            'total_tokens': getattr(self.llm_client, 'total_prompt_tokens', 0) + 
                          getattr(self.llm_client, 'total_completion_tokens', 0)
        }
    
    def estimate_cost(self) -> float:
        """
        Estimate total cost of LLM API calls.
        
        Returns:
            Estimated cost in USD
        """
        prompt_tokens = getattr(self.llm_client, 'total_prompt_tokens', 0)
        completion_tokens = getattr(self.llm_client, 'total_completion_tokens', 0)
        
        return self.llm_client.estimate_cost(prompt_tokens, completion_tokens)
    
    def get_initialization_status(self) -> Dict[str, Any]:
        """
        Get detailed initialization status.
        
        Returns:
            Dictionary with initialization status and warnings
        """
        return {
            'llm_client': {
                'initialized': self.llm_client is not None,
                'provider': self.llm_provider,
                'model': self.llm_model
            },
            'knowledge_base': {
                'initialized': self.kb is not None,
                'available': self.kb is not None
            },
            'vector_store': {
                'initialized': self.vector_store is not None,
                'semantic_search_available': self.vector_store is not None
            },
            'rag_engine': {
                'initialized': self.rag_engine is not None
            },
            'warnings': self.initialization_warnings,
            'fully_functional': len(self.initialization_warnings) == 0
        }


# Process-wide singleton: created on first call, reused thereafter. Env vars
# are read once at construction time, so changing LLM_PROVIDER / LLM_MODEL etc.
# requires a process restart (the standard k8s deploy flow).
_rag_integration: Optional[RAGIntegration] = None


def get_rag_integration(
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    kb_path: Optional[str] = None,
) -> RAGIntegration:
    """Return the singleton RAGIntegration, creating it from env on first call."""
    global _rag_integration
    if _rag_integration is None:
        _rag_integration = RAGIntegration(
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key,
            kb_path=kb_path,
        )
    return _rag_integration


def reset_rag_integration() -> None:
    """Drop the cached singleton. Tests use this between cases."""
    global _rag_integration
    _rag_integration = None
