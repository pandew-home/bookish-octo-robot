"""
RAG Engine integration for DevOps Chatbot v2.

This module integrates the devops-rag library with the v2 backend,
providing semantic search and LLM-powered response generation.
"""
import logging
import sys
import os
from typing import Dict, Any, Optional, List

# Add libs to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libs', 'devops-rag', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libs', 'devops-kb', 'src'))

from devops_rag.rag_engine import RAGEngine
from devops_rag.llm_client import OpenAIClient, AnthropicClient
from devops_rag.vector_store import VectorStore
from devops_kb.knowledge_base import KnowledgeBase

from enrichment_engine import EnrichedContext
from utils.error_handler import handle_generic_error
from kb_seeder import seed_knowledge_base, should_seed_kb, should_force_reseed

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
        llm_provider: str = "openai",
        llm_model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        kb_path: Optional[str] = None,
        cluster_version: str = "v1.28"
    ):
        """
        Initialize RAG integration.
        
        Args:
            llm_provider: LLM provider ("openai" or "anthropic")
            llm_model: Model name
            api_key: API key for LLM provider
            kb_path: Path to knowledge base directory
            cluster_version: Kubernetes cluster version for API docs
            
        Raises:
            ValueError: Only if LLM client initialization fails (critical)
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.cluster_version = cluster_version
        self.initialization_warnings = []
        
        # Initialize LLM client (CRITICAL - must succeed)
        try:
            self.llm_client = self._init_llm_client(llm_provider, llm_model, api_key)
            logger.info(f"✓ LLM client initialized: {llm_provider}/{llm_model}")
        except Exception as e:
            logger.error(f"✗ CRITICAL: Failed to initialize LLM client: {e}")
            raise  # Re-raise - this is critical
        
        # Initialize knowledge base (NON-CRITICAL - can continue without)
        self.kb = self._init_knowledge_base(kb_path)
        if self.kb:
            logger.info(f"✓ Knowledge base initialized from {kb_path}")
            # Seed KB with initial solutions if enabled
            if should_seed_kb():
                force_reseed = should_force_reseed()
                seed_knowledge_base(self.kb, force_reseed=force_reseed)
        elif kb_path:
            warning = f"Knowledge base initialization failed for {kb_path} - continuing without KB"
            self.initialization_warnings.append(warning)
            logger.warning(f"⚠ {warning}")
        
        # Initialize vector store (NON-CRITICAL - can continue without)
        self.vector_store = self._init_vector_store()
        if self.vector_store:
            logger.info("✓ Vector store initialized for semantic search")
        elif self.kb:
            warning = "Vector store initialization failed - semantic search unavailable"
            self.initialization_warnings.append(warning)
            logger.warning(f"⚠ {warning}")
        
        # Initialize RAG engine (should always succeed if LLM client is available)
        try:
            self.rag_engine = RAGEngine(
                llm_client=self.llm_client,
                vector_store=self.vector_store,
                max_retries=3,
                cluster_version=cluster_version
            )
            logger.info("✓ RAG engine initialized")
        except Exception as e:
            logger.error(f"✗ CRITICAL: Failed to initialize RAG engine: {e}")
            raise ValueError(f"Failed to initialize RAG engine: {str(e)}")
        
        # Log final initialization status
        if self.initialization_warnings:
            logger.warning(f"RAG integration initialized with {len(self.initialization_warnings)} warning(s)")
            for warning in self.initialization_warnings:
                logger.warning(f"  - {warning}")
        else:
            logger.info(f"✓ RAG integration fully initialized: {llm_provider}/{llm_model}")
    
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
    
    def process_query(
        self,
        query: str,
        enriched_context: EnrichedContext,
        max_tokens: int = 500,
        is_export: bool = False
    ) -> Dict[str, Any]:
        """
        Process query with RAG pipeline using enriched cluster context.
        
        Args:
            query: User query string
            enriched_context: Enriched context from enrichment engine
            max_tokens: Maximum tokens for LLM response
            is_export: Whether this is for export (uses more tokens)
            
        Returns:
            Dictionary with response and metadata
        """
        try:
            # Convert enriched context to cluster context format
            cluster_context = self._format_cluster_context(enriched_context)
            
            # Extract K8sGPT results if available
            health_monitor_errors = None
            if enriched_context.k8sgpt_results:
                health_monitor_errors = self._format_k8sgpt_errors(enriched_context.k8sgpt_results)
            
            # Process query through RAG engine
            response = self.rag_engine.process_query(
                query=query,
                cluster_context=cluster_context,
                health_monitor_errors=health_monitor_errors,
                max_tokens=max_tokens,
                is_export=is_export
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing query with RAG: {e}")
            
            # Determine error type for frontend styling
            error_type = "unknown"
            
            # Provide user-friendly error messages based on error type
            error_message = "I encountered an error processing your query. "
            
            if "rate limit" in str(e).lower() or "quota" in str(e).lower():
                error_type = "rate_limited"
                error_message += "The LLM service is currently rate-limited. Please wait a moment and try again."
            elif "timeout" in str(e).lower():
                error_type = "timeout"
                error_message += "The request timed out. The cluster may be slow to respond. Please try again."
            elif "api_key" in str(e).lower() or "authentication" in str(e).lower():
                error_type = "auth_error"
                error_message += "There's an issue with the LLM API authentication. Please contact your administrator."
            elif "connection" in str(e).lower() or "network" in str(e).lower():
                error_type = "connection_error"
                error_message += "Unable to connect to the LLM service. Please check your network connection."
            else:
                error_message += "Please try rephrasing your question or contact support if the issue persists."
            
            return {
                'query': query,
                'response': error_message,
                'citations': [],
                'errors': [{'type': 'rag_processing', 'message': str(e), 'severity': 'error'}],
                'metadata': {
                    'error_handled': True,
                    'error_type': error_type
                }
            }
    
    def _format_cluster_context(self, enriched_context: EnrichedContext) -> Dict[str, Any]:
        """
        Format enriched context into cluster context format expected by RAG engine.
        
        Args:
            enriched_context: Enriched context from enrichment engine
            
        Returns:
            Formatted cluster context dictionary
        """
        cluster_context: Dict[str, Any] = {}
        
        # Add pod data
        if enriched_context.pod_data:
            cluster_context['pods'] = enriched_context.pod_data
        
        # Add deployment data
        if enriched_context.deployment_data:
            cluster_context['deployments'] = enriched_context.deployment_data
        
        # Add service data
        if enriched_context.service_data:
            cluster_context['services'] = enriched_context.service_data
        
        # Add node data
        if enriched_context.node_data:
            cluster_context['nodes'] = enriched_context.node_data
        
        # Add storage data
        if enriched_context.storage_data:
            cluster_context['storage'] = enriched_context.storage_data
        
        # Add ArgoCD data
        if enriched_context.argocd_data:
            cluster_context['argocd'] = enriched_context.argocd_data
        
        # Add security data
        if enriched_context.security_data:
            cluster_context['security'] = enriched_context.security_data
        
        # Add AWS data
        if enriched_context.aws_data:
            cluster_context['aws'] = enriched_context.aws_data
        
        # Add any errors encountered during enrichment
        if enriched_context.errors:
            cluster_context['enrichment_errors'] = enriched_context.errors
        
        return cluster_context
    
    def _format_k8sgpt_errors(self, k8sgpt_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format K8sGPT results into health monitor error format.
        
        Args:
            k8sgpt_results: K8sGPT Result CRDs
            
        Returns:
            List of formatted errors
        """
        errors = []
        
        for result in k8sgpt_results:
            error = {
                'resource_kind': result.get('kind', 'Unknown'),
                'resource_name': result.get('resource_name', 'Unknown'),
                'message': result.get('details', ''),
                'error': result.get('error', []),
                'backend': result.get('backend', 'Unknown')
            }
            errors.append(error)
        
        return errors
    
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


# Global RAG integration instance (initialized on first use)
_rag_integration: Optional[RAGIntegration] = None


def get_rag_integration(
    llm_provider: str = "openai",
    llm_model: str = "gpt-3.5-turbo",
    api_key: Optional[str] = None,
    kb_path: Optional[str] = None,
    cluster_version: str = "v1.28"
) -> RAGIntegration:
    """
    Get or create global RAG integration instance.
    
    Args:
        llm_provider: LLM provider
        llm_model: Model name
        api_key: API key
        kb_path: Knowledge base path
        cluster_version: Kubernetes version
        
    Returns:
        RAGIntegration instance
    """
    global _rag_integration
    
    if _rag_integration is None:
        _rag_integration = RAGIntegration(
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key,
            kb_path=kb_path,
            cluster_version=cluster_version
        )
    
    return _rag_integration
