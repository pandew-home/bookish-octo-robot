"""Test RAG engine error tracking integration."""

from unittest.mock import Mock

from devops_rag.rag_engine import RAGEngine


def test_rag_engine_includes_health_monitor_errors_in_prompt():
    """Test that health monitor errors are included in LLM prompt."""
    # Create mock LLM client
    mock_llm_client = Mock()
    mock_llm_client.generate.return_value = "Test response"
    
    # Create RAG engine
    rag_engine = RAGEngine(llm_client=mock_llm_client)
    
    # Sample health monitor errors
    health_monitor_errors = [
        {
            "type": "k8s_api_call",
            "message": "list_pods attempt 1 failed: Connection timeout",
            "severity": "warning",
            "timestamp": "2024-01-15T10:00:00Z",
        },
        {
            "type": "k8s_api_call", 
            "message": "list_nodes failed after 5 attempts: API server unavailable",
            "severity": "error",
            "timestamp": "2024-01-15T10:01:00Z",
        }
    ]
    
    # Process query with health monitor errors
    result = rag_engine.process_query(
        query="Why are my pods failing?",
        health_monitor_errors=health_monitor_errors
    )
    
    # Verify LLM was called
    assert mock_llm_client.generate.called
    
    # Get the prompt that was sent to LLM
    prompt = mock_llm_client.generate.call_args[0][0]
    
    # Verify health monitor errors are included in prompt
    assert "CLUSTER MONITORING ERRORS:" in prompt
    assert "list_pods attempt 1 failed: Connection timeout" in prompt
    assert "NOTE: Some cluster metrics may be incomplete due to API errors above." in prompt
    assert "Consider these limitations when providing recommendations." in prompt
    
    # Verify response structure
    assert result["query"] == "Why are my pods failing?"
    assert result["response"] == "Test response"
    assert result["errors"] == []  # RAG engine's own errors


def test_rag_engine_handles_no_health_monitor_errors():
    """Test that RAG engine works normally when no health monitor errors provided."""
    # Create mock LLM client
    mock_llm_client = Mock()
    mock_llm_client.generate.return_value = "Test response"
    
    # Create RAG engine
    rag_engine = RAGEngine(llm_client=mock_llm_client)
    
    # Process query without health monitor errors
    result = rag_engine.process_query(
        query="How do I check pod status?",
        health_monitor_errors=None
    )
    
    # Verify LLM was called
    assert mock_llm_client.generate.called
    
    # Get the prompt that was sent to LLM
    prompt = mock_llm_client.generate.call_args[0][0]
    
    # Verify no health monitor error section in prompt
    assert "CLUSTER MONITORING ERRORS:" not in prompt
    assert "NOTE: Some cluster metrics may be incomplete" not in prompt
    
    # Verify response structure
    assert result["query"] == "How do I check pod status?"
    assert result["response"] == "Test response"


def test_rag_engine_filters_warning_severity_errors():
    """Test that only warning severity errors are included in prompt."""
    # Create mock LLM client
    mock_llm_client = Mock()
    mock_llm_client.generate.return_value = "Test response"
    
    # Create RAG engine
    rag_engine = RAGEngine(llm_client=mock_llm_client)
    
    # Sample health monitor errors with different severities
    health_monitor_errors = [
        {
            "type": "k8s_api_call",
            "message": "Warning level error",
            "severity": "warning",
            "timestamp": "2024-01-15T10:00:00Z",
        },
        {
            "type": "k8s_api_call", 
            "message": "Error level error",
            "severity": "error",
            "timestamp": "2024-01-15T10:01:00Z",
        }
    ]
    
    # Process query with mixed severity errors
    _ = rag_engine.process_query(
        query="Test query",
        health_monitor_errors=health_monitor_errors
    )
    
    # Get the prompt that was sent to LLM
    prompt = mock_llm_client.generate.call_args[0][0]
    
    # Verify only warning severity errors are included
    assert "Warning level error" in prompt
    assert "Error level error" not in prompt