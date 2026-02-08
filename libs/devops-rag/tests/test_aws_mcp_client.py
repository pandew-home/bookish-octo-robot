"""Tests for AWS MCP client."""

import pytest
from unittest.mock import Mock, patch
import requests
from devops_rag.aws_mcp_client import AWSMCPClient, AWSClusterContext, format_aws_context


class TestAWSMCPClient:
    """Test AWS MCP client functionality."""
    
    def test_init_disabled_when_not_eks(self):
        """Test client is disabled when not on EKS."""
        with patch.object(AWSMCPClient, 'is_eks_cluster', return_value=False):
            client = AWSMCPClient()
            assert not client.enabled
    
    def test_init_enabled_when_eks(self):
        """Test client is enabled when on EKS."""
        with patch.object(AWSMCPClient, 'is_eks_cluster', return_value=True), \
             patch.object(AWSMCPClient, '_get_cluster_name', return_value='test-cluster'), \
             patch.object(AWSMCPClient, '_get_region', return_value='us-east-1'):
            client = AWSMCPClient()
            assert client.enabled
            assert client.cluster_name == 'test-cluster'
            assert client.region == 'us-east-1'
    
    def test_is_eks_cluster_with_env_var(self):
        """Test EKS detection via environment variable."""
        with patch.dict('os.environ', {'CLUSTER_PLATFORM': 'eks'}):
            client = AWSMCPClient()
            assert client.is_eks_cluster()
    
    def test_is_eks_cluster_with_node_labels(self):
        """Test EKS detection via node labels."""
        mock_node = Mock()
        mock_node.metadata.labels = {'eks.amazonaws.com/nodegroup': 'test-ng'}
        
        mock_nodes = Mock()
        mock_nodes.items = [mock_node]
        
        with patch('devops_rag.aws_mcp_client.config.load_incluster_config'), \
             patch('devops_rag.aws_mcp_client.client.CoreV1Api') as mock_api:
            mock_api.return_value.list_node.return_value = mock_nodes
            
            client = AWSMCPClient()
            assert client.is_eks_cluster()
    
    def test_get_cluster_name_from_env(self):
        """Test cluster name detection from environment."""
        with patch.dict('os.environ', {'CLUSTER_NAME': 'my-cluster'}):
            client = AWSMCPClient(enabled=False)  # Disable to avoid other calls
            assert client._get_cluster_name() == 'my-cluster'
    
    def test_get_region_from_env(self):
        """Test region detection from environment."""
        with patch.dict('os.environ', {'AWS_REGION': 'us-west-2'}):
            client = AWSMCPClient(enabled=False)
            assert client._get_region() == 'us-west-2'
    
    def test_get_cluster_context_disabled(self):
        """Test get_cluster_context returns None when disabled."""
        client = AWSMCPClient(enabled=False)
        result = client.get_cluster_context()
        assert result is None
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_cluster_context_success(self, mock_post):
        """Test successful cluster context retrieval."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "cluster": {"name": "test-cluster", "version": "1.28"},
                "region": "us-east-1",
                "node_groups": [{"nodegroupName": "ng-1"}],
                "vpc": {"vpcId": "vpc-123"},
                "security_groups": [{"groupId": "sg-123"}],
                "load_balancers": [{"loadBalancerName": "lb-1"}]
            }
        }
        mock_post.return_value = mock_response
        
        client = AWSMCPClient(enabled=True)
        result = client.get_cluster_context("test-cluster", "us-east-1")
        
        assert result is not None
        assert isinstance(result, AWSClusterContext)
        assert result.cluster["name"] == "test-cluster"
        assert result.region == "us-east-1"
        assert len(result.node_groups) == 1
        assert result.vpc["vpcId"] == "vpc-123"
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_cluster_context_timeout(self, mock_post):
        """Test cluster context retrieval with timeout."""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        client = AWSMCPClient(enabled=True)
        result = client.get_cluster_context()
        
        assert result is None
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_cluster_context_connection_error(self, mock_post):
        """Test cluster context retrieval with connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError()
        
        client = AWSMCPClient(enabled=True)
        result = client.get_cluster_context()
        
        assert result is None
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_cluster_context_http_error(self, mock_post):
        """Test cluster context retrieval with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        client = AWSMCPClient(enabled=True)
        result = client.get_cluster_context()
        
        assert result is None
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_eks_cluster_info(self, mock_post):
        """Test EKS cluster info retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"name": "test-cluster", "version": "1.28"}
        }
        mock_post.return_value = mock_response
        
        client = AWSMCPClient(enabled=True)
        result = client.get_eks_cluster_info()
        
        assert result is not None
        assert result["name"] == "test-cluster"
    
    @patch('devops_rag.aws_mcp_client.requests.post')
    def test_get_node_groups(self, mock_post):
        """Test node groups retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [{"nodegroupName": "ng-1"}, {"nodegroupName": "ng-2"}]
        }
        mock_post.return_value = mock_response
        
        client = AWSMCPClient(enabled=True)
        result = client.get_node_groups()
        
        assert len(result) == 2
        assert result[0]["nodegroupName"] == "ng-1"
    
    def test_format_aws_context(self):
        """Test AWS context formatting for LLM."""
        aws_context = AWSClusterContext(
            cluster={"name": "test-cluster", "version": "1.28"},
            region="us-east-1",
            node_groups=[{
                "nodegroupName": "ng-1",
                "instanceTypes": ["t3.medium"],
                "status": "ACTIVE"
            }],
            vpc={"vpcId": "vpc-123", "cidrBlock": "10.0.0.0/16"},
            security_groups=[{
                "groupName": "test-sg",
                "groupId": "sg-123",
                "description": "Test security group"
            }],
            load_balancers=[{
                "loadBalancerName": "test-lb",
                "type": "application",
                "scheme": "internet-facing"
            }]
        )
        
        formatted = format_aws_context(aws_context)
        
        assert "# AWS Infrastructure Context" in formatted
        assert "## EKS Cluster" in formatted
        assert "test-cluster" in formatted
        assert "## Node Groups" in formatted
        assert "ng-1" in formatted
        assert "## VPC Configuration" in formatted
        assert "vpc-123" in formatted
        assert "## Security Groups" in formatted
        assert "test-sg" in formatted
        assert "## Load Balancers" in formatted
        assert "test-lb" in formatted


if __name__ == "__main__":
    pytest.main([__file__])