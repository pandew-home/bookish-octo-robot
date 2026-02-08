"""
Unit tests for RAG integration.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from rag_integration import RAGIntegration, get_rag_integration
from enrichment_engine import EnrichedContext


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    client = Mock()
    client.generate.return_value = "This is a test response"
    client.embed.return_value = [0.1] * 1536  # Mock embedding
    client.count_tokens.return_value = 10
    client.estimate_cost.return_value = 0.001
    client.total_prompt_tokens = 100
    client.total_completion_tokens = 50
    return client


@pytest.fixture
def mock_kb():
    """Create mock knowledge base."""
    kb = Mock()
    kb.get_all_documents.return_value = [
        {
            'id': 'doc1',
            'title': 'Test Document',
            'content': 'This is test content',
            'type': 'solution'
        }
    ]
    return kb


@pytest.fixture
def mock_vector_store():
    """Create mock vector store."""
    store = Mock()
    store.search.return_value = [
        {
            'id': 'doc1',
            'title': 'Test Document',
            'content': 'This is test content',
            'score': 0.95
        }
    ]
    return store


@pytest.fixture
def mock_rag_engine():
    """Create mock RAG engine."""
    engine = Mock()
    engine.process_query.return_value = {
        'query': 'test query',
        'response': 'test response',
        'citations': [],
        'errors': [],
        'metadata': {}
    }
    return engine


@pytest.fixture
def enriched_context():
    """Create sample enriched context."""
    context = EnrichedContext()
    context.pod_data = {
        'pods': [
            {
                'name': 'test-pod',
                'namespace': 'default',
                'phase': 'Running'
            }
        ]
    }
    context.k8sgpt_results = [
        {
            'kind': 'Pod',
            'resource_name': 'test-pod',
            'details': 'Pod is running normally',
            'error': [],
            'backend': 'openai'
        }
    ]
    return context


class TestRAGIntegration:
    """Test RAGIntegration class."""
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.RAGEngine')
    def test_initialization_openai(self, mock_rag, mock_vector, mock_kb_class, mock_openai):
        """Test RAG integration initialization with OpenAI."""
        mock_openai.return_value = Mock()
        mock_kb_class.return_value = Mock()
        mock_vector.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            llm_model="gpt-3.5-turbo",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        assert rag.llm_provider == "openai"
        assert rag.llm_model == "gpt-3.5-turbo"
        mock_openai.assert_called_once()
    
    @patch('rag_integration.AnthropicClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.RAGEngine')
    def test_initialization_anthropic(self, mock_rag, mock_vector, mock_kb_class, mock_anthropic):
        """Test RAG integration initialization with Anthropic."""
        mock_anthropic.return_value = Mock()
        mock_kb_class.return_value = Mock()
        mock_vector.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="anthropic",
            llm_model="claude-3-sonnet",
            api_key="test-key"
        )
        
        assert rag.llm_provider == "anthropic"
        mock_anthropic.assert_called_once()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_initialization_without_kb(self, mock_rag, mock_openai):
        """Test initialization without knowledge base."""
        mock_openai.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path=None
        )
        
        assert rag.kb is None
        assert rag.vector_store is None
    
    def test_format_cluster_context(self, enriched_context):
        """Test formatting enriched context to cluster context."""
        with patch('rag_integration.OpenAIClient'), \
             patch('rag_integration.RAGEngine'):
            rag = RAGIntegration(llm_provider="openai", api_key="test-key")
            
            cluster_context = rag._format_cluster_context(enriched_context)
            
            assert 'pods' in cluster_context
            assert cluster_context['pods'] == enriched_context.pod_data
    
    def test_format_cluster_context_with_errors(self):
        """Test formatting cluster context with enrichment errors."""
        context = EnrichedContext()
        context.errors = ['Error 1', 'Error 2']
        
        with patch('rag_integration.OpenAIClient'), \
             patch('rag_integration.RAGEngine'):
            rag = RAGIntegration(llm_provider="openai", api_key="test-key")
            
            cluster_context = rag._format_cluster_context(context)
            
            assert 'enrichment_errors' in cluster_context
            assert len(cluster_context['enrichment_errors']) == 2
    
    def test_format_k8sgpt_errors(self, enriched_context):
        """Test formatting K8sGPT results to error format."""
        with patch('rag_integration.OpenAIClient'), \
             patch('rag_integration.RAGEngine'):
            rag = RAGIntegration(llm_provider="openai", api_key="test-key")
            
            errors = rag._format_k8sgpt_errors(enriched_context.k8sgpt_results)
            
            assert len(errors) == 1
            assert errors[0]['resource_kind'] == 'Pod'
            assert errors[0]['resource_name'] == 'test-pod'
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query(self, mock_rag_class, mock_openai, enriched_context):
        """Test processing query with enriched context."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.return_value = {
            'query': 'test query',
            'response': 'test response',
            'citations': [],
            'errors': [],
            'metadata': {}
        }
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query(
            query="Why is my pod failing?",
            enriched_context=enriched_context
        )
        
        assert response['query'] == 'test query'
        assert response['response'] == 'test response'
        mock_rag_engine.process_query.assert_called_once()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_with_export(self, mock_rag_class, mock_openai, enriched_context):
        """Test processing query for export (more tokens)."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.return_value = {
            'query': 'test',
            'response': 'test',
            'citations': [],
            'errors': [],
            'metadata': {}
        }
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query(
            query="Test query",
            enriched_context=enriched_context,
            is_export=True
        )
        
        # Verify is_export was passed
        call_args = mock_rag_engine.process_query.call_args
        assert call_args[1]['is_export'] is True
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_error_handling(self, mock_rag_class, mock_openai, enriched_context):
        """Test error handling in process_query."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.side_effect = Exception("Test error")
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query(
            query="Test query",
            enriched_context=enriched_context
        )
        
        assert 'error' in response['response'].lower()
        assert len(response['errors']) > 0
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    def test_search_knowledge_base(self, mock_rag, mock_kb_class, mock_vector_class, mock_openai):
        """Test searching knowledge base."""
        mock_llm = Mock()
        mock_llm.embed.return_value = [0.1] * 1536
        mock_openai.return_value = mock_llm
        
        mock_kb = Mock()
        mock_kb.get_all_documents.return_value = []
        mock_kb_class.return_value = mock_kb
        
        mock_vector = Mock()
        mock_vector.search.return_value = [
            {'id': 'doc1', 'title': 'Test', 'content': 'Test content'}
        ]
        mock_vector_class.return_value = mock_vector
        
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        results = rag.search_knowledge_base("test query", top_k=5)
        
        assert len(results) == 1
        assert results[0]['id'] == 'doc1'
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_search_knowledge_base_without_vector_store(self, mock_rag, mock_openai):
        """Test searching KB without vector store returns empty."""
        mock_openai.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        results = rag.search_knowledge_base("test query")
        
        assert results == []
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_get_token_usage(self, mock_rag, mock_openai):
        """Test getting token usage statistics."""
        mock_llm = Mock()
        mock_llm.total_prompt_tokens = 100
        mock_llm.total_completion_tokens = 50
        mock_openai.return_value = mock_llm
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        usage = rag.get_token_usage()
        
        assert usage['prompt_tokens'] == 100
        assert usage['completion_tokens'] == 50
        assert usage['total_tokens'] == 150
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_estimate_cost(self, mock_rag, mock_openai):
        """Test estimating API cost."""
        mock_llm = Mock()
        mock_llm.total_prompt_tokens = 1000
        mock_llm.total_completion_tokens = 500
        mock_llm.estimate_cost.return_value = 0.0025
        mock_openai.return_value = mock_llm
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        cost = rag.estimate_cost()
        
        assert cost == 0.0025
        mock_llm.estimate_cost.assert_called_once_with(1000, 500)


class TestGetRAGIntegration:
    """Test get_rag_integration singleton function."""
    
    @patch('rag_integration.RAGIntegration')
    def test_get_rag_integration_creates_instance(self, mock_rag_class):
        """Test that get_rag_integration creates instance."""
        # Reset global
        import rag_integration
        rag_integration._rag_integration = None
        
        mock_instance = Mock()
        mock_rag_class.return_value = mock_instance
        
        result = get_rag_integration(
            llm_provider="openai",
            api_key="test-key"
        )
        
        assert result == mock_instance
        mock_rag_class.assert_called_once()
    
    @patch('rag_integration.RAGIntegration')
    def test_get_rag_integration_returns_existing(self, mock_rag_class):
        """Test that get_rag_integration returns existing instance."""
        # Set global
        import rag_integration
        existing_instance = Mock()
        rag_integration._rag_integration = existing_instance
        
        result = get_rag_integration()
        
        assert result == existing_instance
        mock_rag_class.assert_not_called()



class TestEnhancedErrorHandling:
    """Test enhanced error handling in RAG integration."""
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_init_llm_client_import_error(self, mock_rag, mock_openai):
        """Test LLM client initialization with import error."""
        mock_openai.side_effect = ImportError("No module named 'openai'")
        
        with pytest.raises(ValueError) as exc_info:
            RAGIntegration(llm_provider="openai", api_key="test-key")
        
        assert "library not available" in str(exc_info.value).lower()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_init_llm_client_api_key_error(self, mock_rag, mock_openai):
        """Test LLM client initialization with API key error."""
        mock_openai.side_effect = Exception("Invalid API key")
        
        with pytest.raises(ValueError) as exc_info:
            RAGIntegration(llm_provider="openai", api_key="invalid")
        
        assert "api key" in str(exc_info.value).lower()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    def test_init_kb_file_not_found(self, mock_rag, mock_kb_class, mock_openai):
        """Test knowledge base initialization with file not found."""
        mock_openai.return_value = Mock()
        mock_kb_class.side_effect = FileNotFoundError("KB path not found")
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/nonexistent/path"
        )
        
        # Should handle gracefully
        assert rag.kb is None
        assert rag.vector_store is None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    def test_init_kb_permission_error(self, mock_rag, mock_kb_class, mock_openai):
        """Test knowledge base initialization with permission error."""
        mock_openai.return_value = Mock()
        mock_kb_class.side_effect = PermissionError("Permission denied")
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/restricted/path"
        )
        
        # Should handle gracefully
        assert rag.kb is None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    def test_init_vector_store_import_error(self, mock_rag, mock_kb_class, mock_vector_class, mock_openai):
        """Test vector store initialization with FAISS import error."""
        mock_openai.return_value = Mock()
        mock_kb = Mock()
        mock_kb.get_all_documents.return_value = []
        mock_kb_class.return_value = mock_kb
        mock_vector_class.side_effect = ImportError("No module named 'faiss'")
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        # Should handle gracefully
        assert rag.vector_store is None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_rate_limit_error(self, mock_rag_class, mock_openai, enriched_context):
        """Test query processing with rate limit error."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.side_effect = Exception("Rate limit exceeded")
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query("test", enriched_context)
        
        assert "rate-limited" in response['response'].lower()
        assert response['errors'][0]['severity'] == 'error'
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_timeout_error(self, mock_rag_class, mock_openai, enriched_context):
        """Test query processing with timeout error."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.side_effect = Exception("Request timeout")
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query("test", enriched_context)
        
        assert "timed out" in response['response'].lower()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_auth_error(self, mock_rag_class, mock_openai, enriched_context):
        """Test query processing with authentication error."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.side_effect = Exception("Invalid API key")
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query("test", enriched_context)
        
        assert "authentication" in response['response'].lower()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_process_query_connection_error(self, mock_rag_class, mock_openai, enriched_context):
        """Test query processing with connection error."""
        mock_openai.return_value = Mock()
        mock_rag_engine = Mock()
        mock_rag_engine.process_query.side_effect = Exception("Connection refused")
        mock_rag_class.return_value = mock_rag_engine
        
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        
        response = rag.process_query("test", enriched_context)
        
        assert "connect" in response['response'].lower()
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    def test_vector_store_embed_error_handling(self, mock_rag, mock_kb_class, mock_vector_class, mock_openai):
        """Test vector store handles embedding errors gracefully."""
        mock_llm = Mock()
        mock_llm.embed.side_effect = [
            [0.1] * 1536,  # First doc succeeds
            Exception("Embedding failed"),  # Second doc fails
            [0.1] * 1536  # Third doc succeeds
        ]
        mock_openai.return_value = mock_llm
        
        mock_kb = Mock()
        mock_kb.get_all_documents.return_value = [
            {'id': 'doc1', 'content': 'test1'},
            {'id': 'doc2', 'content': 'test2'},
            {'id': 'doc3', 'content': 'test3'}
        ]
        mock_kb_class.return_value = mock_kb
        
        mock_vector = Mock()
        mock_vector_class.return_value = mock_vector
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        # Should have indexed 2 out of 3 documents
        assert mock_vector.add.call_count == 2



class TestImprovedInitialization:
    """Test improved initialization with better error handling."""
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_initialization_tracks_warnings(self, mock_rag, mock_openai):
        """Test that initialization warnings are tracked."""
        mock_openai.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path=None  # No KB path
        )
        
        assert hasattr(rag, 'initialization_warnings')
        assert isinstance(rag.initialization_warnings, list)
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    @patch('rag_integration.os.path.exists')
    def test_kb_init_path_not_exists(self, mock_exists, mock_rag, mock_kb_class, mock_openai):
        """Test KB initialization when path doesn't exist."""
        mock_openai.return_value = Mock()
        mock_exists.return_value = False
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/nonexistent/path"
        )
        
        assert rag.kb is None
        assert any("Knowledge base initialization failed" in w for w in rag.initialization_warnings)
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    @patch('rag_integration.os.path.exists')
    @patch('rag_integration.os.path.isdir')
    def test_kb_init_path_not_directory(self, mock_isdir, mock_exists, mock_rag, mock_kb_class, mock_openai):
        """Test KB initialization when path is not a directory."""
        mock_openai.return_value = Mock()
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/file.txt"
        )
        
        assert rag.kb is None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    @patch('rag_integration.os.path.exists')
    @patch('rag_integration.os.path.isdir')
    @patch('rag_integration.os.access')
    def test_kb_init_no_read_permission(self, mock_access, mock_isdir, mock_exists, mock_rag, mock_kb_class, mock_openai):
        """Test KB initialization when no read permission."""
        mock_openai.return_value = Mock()
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_access.return_value = False
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/restricted/path"
        )
        
        assert rag.kb is None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    @patch('rag_integration.os.path.exists')
    @patch('rag_integration.os.path.isdir')
    @patch('rag_integration.os.access')
    def test_kb_init_empty_kb(self, mock_access, mock_isdir, mock_exists, mock_rag, mock_kb_class, mock_openai):
        """Test KB initialization with empty knowledge base."""
        mock_openai.return_value = Mock()
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_access.return_value = True
        
        mock_kb = Mock()
        mock_kb.get_all_documents.return_value = []
        mock_kb_class.return_value = mock_kb
        
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        # Should still initialize KB even if empty
        assert rag.kb is not None
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.FAISSVectorStore')
    @patch('rag_integration.KnowledgeBase')
    @patch('rag_integration.RAGEngine')
    @patch('rag_integration.os.path.exists')
    @patch('rag_integration.os.path.isdir')
    @patch('rag_integration.os.access')
    def test_vector_store_tracks_failed_documents(self, mock_access, mock_isdir, mock_exists, mock_rag, mock_kb_class, mock_vector_class, mock_openai):
        """Test that vector store tracks failed document embeddings."""
        mock_llm = Mock()
        mock_llm.embed.side_effect = [
            [0.1] * 1536,  # Doc 1 succeeds
            Exception("Embedding failed"),  # Doc 2 fails
            [0.1] * 1536  # Doc 3 succeeds
        ]
        mock_openai.return_value = mock_llm
        
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_access.return_value = True
        
        mock_kb = Mock()
        mock_kb.get_all_documents.return_value = [
            {'id': 'doc1', 'content': 'test1'},
            {'id': 'doc2', 'content': 'test2'},
            {'id': 'doc3', 'content': 'test3'}
        ]
        mock_kb_class.return_value = mock_kb
        
        mock_vector = Mock()
        mock_vector_class.return_value = mock_vector
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/path/to/kb"
        )
        
        # Should have warning about failed document
        assert any("failed to index" in w.lower() for w in rag.initialization_warnings)
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_get_initialization_status(self, mock_rag, mock_openai):
        """Test getting initialization status."""
        mock_openai.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            llm_model="gpt-4",
            api_key="test-key"
        )
        
        status = rag.get_initialization_status()
        
        assert 'llm_client' in status
        assert status['llm_client']['initialized'] is True
        assert status['llm_client']['provider'] == 'openai'
        assert status['llm_client']['model'] == 'gpt-4'
        assert 'knowledge_base' in status
        assert 'vector_store' in status
        assert 'rag_engine' in status
        assert 'warnings' in status
        assert 'fully_functional' in status
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_initialization_status_with_warnings(self, mock_rag, mock_openai):
        """Test initialization status when there are warnings."""
        mock_openai.return_value = Mock()
        mock_rag.return_value = Mock()
        
        rag = RAGIntegration(
            llm_provider="openai",
            api_key="test-key",
            kb_path="/nonexistent"  # Will cause warning
        )
        
        status = rag.get_initialization_status()
        
        assert len(status['warnings']) > 0
        assert status['fully_functional'] is False
    
    @patch('rag_integration.OpenAIClient')
    @patch('rag_integration.RAGEngine')
    def test_rag_engine_init_failure_raises(self, mock_rag_class, mock_openai):
        """Test that RAG engine initialization failure raises exception."""
        mock_openai.return_value = Mock()
        mock_rag_class.side_effect = Exception("RAG engine failed")
        
        with pytest.raises(ValueError) as exc_info:
            RAGIntegration(llm_provider="openai", api_key="test-key")
        
        assert "rag engine" in str(exc_info.value).lower()
