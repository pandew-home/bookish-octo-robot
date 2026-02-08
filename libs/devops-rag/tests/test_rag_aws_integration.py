"""Tests for RAG engine AWS integration."""

import pytest
from unittest.mock import Mock, patch
from devops_rag.rag_engine import RAGEngine
from devops_rag.aws_mcp_client import AWSMCPClient, AWSClusterContext


class TestRAGAWSIntegration:
    """Test RAG engine AWS MCP integration."""
    
    def test_rag_engine_with_aws_disabled(self):
        """Test RAG engine when AWS MCP is disabled."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Test response"
        
        mock_aws_client = Mock(spec=AWSMCPClient)
        mock_aws_client.enabled = False
        
        rag = RAGEngine(llm_client=mock_llm, aws_mcp_client=mock_aws_client)
        
        result = rag.process_query("Test query")
        
        assert result["response"] == "Test response"
        assert result["errors"] == []
        # AWS client should not be called when disabled
        mock_aws_client.get_cluster_context.assert_not_called()
    
    def test_rag_engine_with_aws_enabled_success(self):
        """Test RAG engine with successful AWS context retrieval."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Test response with AWS context"
        
        # Mock AWS context
        aws_context = AWSClusterContext(
            cluster={"name": "test-cluster", "version": "1.28"},
            region="us-east-1",
            node_groups=[{"nodegroupName": "ng-1"}],
            vpc={"vpcId": "vpc-123"},
            security_groups=[{"groupId": "sg-123"}],
            load_balancers=[{"loadBalancerName": "lb-1"}]
        )
        
        mock_aws_client = Mock(spec=AWSMCPClient)
        mock_aws_client.enabled = True
        mock_aws_client.get_cluster_context.return_value = aws_context
        
        rag = RAGEngine(llm_client=mock_llm, aws_mcp_client=mock_aws_client)
        
        result = rag.process_query("Test EKS query")
        
        assert result["response"] == "Test response with AWS context"
        assert result["errors"] == []
        
        # Verify AWS client was called
        mock_aws_client.get_cluster_context.assert_called_once()
        
        # Verify AWS context was added to citations
        aws_citation = None
        for citation in result["citations"]:
            if citation["id"] == "aws-context":
                aws_citation = citation
                break
        
        assert aws_citation is not None
        assert aws_citation["title"] == "AWS Infrastructure Context"
        assert "test-cluster" in aws_citation["snippet"]
    
    def test_rag_engine_with_aws_enabled_failure(self):
        """Test RAG engine with AWS context retrieval failure."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Test response without AWS context"
        
        mock_aws_client = Mock(spec=AWSMCPClient)
        mock_aws_client.enabled = True
        mock_aws_client.get_cluster_context.side_effect = Exception("AWS MCP server unavailable")
        
        rag = RAGEngine(llm_client=mock_llm, aws_mcp_client=mock_aws_client)
        
        result = rag.process_query("Test EKS query")
        
        assert result["response"] == "Test response without AWS context"
        
        # Should have an error tracked
        assert len(result["errors"]) == 1
        assert result["errors"][0]["type"] == "aws_context_retrieval"
        assert "AWS MCP server unavailable" in result["errors"][0]["message"]
        
        # Verify AWS client was called
        mock_aws_client.get_cluster_context.assert_called_once()
    
    def test_rag_engine_with_aws_context_in_prompt(self):
        """Test that AWS context is properly included in LLM prompt."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Response"
        
        # Mock AWS context
        aws_context = AWSClusterContext(
            cluster={"name": "prod-cluster", "version": "1.29"},
            region="us-west-2",
            node_groups=[],
            vpc={"vpcId": "vpc-456"},
            security_groups=[],
            load_balancers=[]
        )
        
        mock_aws_client = Mock(spec=AWSMCPClient)
        mock_aws_client.enabled = True
        mock_aws_client.get_cluster_context.return_value = aws_context
        
        rag = RAGEngine(llm_client=mock_llm, aws_mcp_client=mock_aws_client)
        
        _ = rag.process_query("Why is my pod failing?")
        
        # Check that LLM was called with AWS context in prompt
        mock_llm.generate.assert_called_once()
        prompt = mock_llm.generate.call_args[0][0]
        
        assert "AWS INFRASTRUCTURE CONTEXT:" in prompt
        assert "prod-cluster" in prompt
        assert "vpc-456" in prompt
        assert "us-west-2" in prompt
    
    def test_rag_engine_auto_creates_aws_client(self):
        """Test that RAG engine auto-creates AWS client if not provided."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Response"
        
        with patch('devops_rag.rag_engine.AWSMCPClient') as mock_aws_class:
            mock_aws_instance = Mock()
            mock_aws_instance.enabled = False
            mock_aws_class.return_value = mock_aws_instance
            
            rag = RAGEngine(llm_client=mock_llm)
            
            # Should have created AWS client
            mock_aws_class.assert_called_once()
            assert rag.aws_mcp_client == mock_aws_instance
    
    def test_rag_engine_with_existing_context_documents(self):
        """Test RAG engine adds AWS context to existing documents."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "Response"
        
        # Mock AWS context
        aws_context = AWSClusterContext(
            cluster={"name": "test-cluster"},
            region="us-east-1",
            node_groups=[],
            vpc={},
            security_groups=[],
            load_balancers=[]
        )
        
        mock_aws_client = Mock(spec=AWSMCPClient)
        mock_aws_client.enabled = True
        mock_aws_client.get_cluster_context.return_value = aws_context
        
        rag = RAGEngine(llm_client=mock_llm, aws_mcp_client=mock_aws_client)
        
        # Provide existing context documents
        existing_docs = [
            {"id": "doc1", "title": "Solution 1", "content": "Fix pod issues"}
        ]
        
        result = rag.process_query("Test query", context_documents=existing_docs)
        
        # Should have both existing doc and AWS context
        assert len(result["citations"]) == 2
        
        citation_ids = [c["id"] for c in result["citations"]]
        assert "doc1" in citation_ids
        assert "aws-context" in citation_ids


if __name__ == "__main__":
    pytest.main([__file__])