"""
Unit tests for cluster manager.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
import tempfile

from cluster_manager import (
    discover_clusters,
    get_k8s_clients,
    cleanup_k8s_clients,
    ClusterCache
)
from credential_store import StoredCredentials


@pytest.fixture
def sample_credentials():
    """Create sample credentials for testing."""
    now = datetime.now()
    return StoredCredentials(
        auth_mode="aws",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token="FwoGZXIvYXdzEBQaDH...",
        region="us-east-1",
        user_arn="arn:aws:iam::123456789012:user/test-user",
        account_id="123456789012",
        expires_at=now + timedelta(hours=1),
        created_at=now
    )


@pytest.fixture
def sample_cluster():
    """Create sample cluster metadata."""
    return {
        'name': 'test-cluster',
        'endpoint': 'https://ABCDEF123456.gr7.us-east-1.eks.amazonaws.com',
        'version': '1.28',
        'status': 'ACTIVE',
        'region': 'us-east-1',
        'ca_data': 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...'  # Base64 encoded cert
    }


class TestClusterDiscovery:
    """Test cases for cluster discovery."""
    
    @pytest.mark.asyncio
    @patch('cluster_manager.boto3.client')
    async def test_discover_clusters_success(self, mock_boto_client, sample_credentials):
        """Test successful cluster discovery."""
        # Mock EKS client
        mock_eks = MagicMock()
        mock_boto_client.return_value = mock_eks
        
        # Mock list_clusters response
        mock_eks.list_clusters.return_value = {
            'clusters': ['cluster-1', 'cluster-2']
        }
        
        # Mock describe_cluster responses
        mock_eks.describe_cluster.side_effect = [
            {
                'cluster': {
                    'name': 'cluster-1',
                    'endpoint': 'https://ABC123.gr7.us-east-1.eks.amazonaws.com',
                    'version': '1.28',
                    'status': 'ACTIVE',
                    'certificateAuthority': {
                        'data': 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...'
                    }
                }
            },
            {
                'cluster': {
                    'name': 'cluster-2',
                    'endpoint': 'https://DEF456.gr7.us-east-1.eks.amazonaws.com',
                    'version': '1.27',
                    'status': 'ACTIVE',
                    'certificateAuthority': {
                        'data': 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...'
                    }
                }
            }
        ]
        
        clusters = await discover_clusters(sample_credentials)
        
        assert len(clusters) == 2
        assert clusters[0]['name'] == 'cluster-1'
        assert clusters[0]['version'] == '1.28'
        assert clusters[1]['name'] == 'cluster-2'
        assert clusters[1]['version'] == '1.27'
        assert all('ca_data' in cluster for cluster in clusters)
    
    @pytest.mark.asyncio
    @patch('cluster_manager.boto3.client')
    async def test_discover_clusters_empty(self, mock_boto_client, sample_credentials):
        """Test cluster discovery with no clusters."""
        mock_eks = MagicMock()
        mock_boto_client.return_value = mock_eks
        mock_eks.list_clusters.return_value = {'clusters': []}
        
        clusters = await discover_clusters(sample_credentials)
        
        assert len(clusters) == 0
    
    @pytest.mark.asyncio
    @patch('cluster_manager.boto3.client')
    async def test_discover_clusters_partial_failure(self, mock_boto_client, sample_credentials):
        """Test cluster discovery when some clusters fail to describe."""
        mock_eks = MagicMock()
        mock_boto_client.return_value = mock_eks
        
        mock_eks.list_clusters.return_value = {
            'clusters': ['cluster-1', 'cluster-2']
        }
        
        # First cluster succeeds, second fails
        mock_eks.describe_cluster.side_effect = [
            {
                'cluster': {
                    'name': 'cluster-1',
                    'endpoint': 'https://ABC123.gr7.us-east-1.eks.amazonaws.com',
                    'version': '1.28',
                    'status': 'ACTIVE',
                    'certificateAuthority': {
                        'data': 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...'
                    }
                }
            },
            Exception("Access denied")
        ]
        
        clusters = await discover_clusters(sample_credentials)
        
        # Should return only the successful cluster
        assert len(clusters) == 1
        assert clusters[0]['name'] == 'cluster-1'
    
    @pytest.mark.asyncio
    @patch('cluster_manager.boto3.client')
    async def test_discover_clusters_includes_metadata(self, mock_boto_client, sample_credentials):
        """Test that discovered clusters include all required metadata."""
        mock_eks = MagicMock()
        mock_boto_client.return_value = mock_eks
        
        mock_eks.list_clusters.return_value = {'clusters': ['test-cluster']}
        mock_eks.describe_cluster.return_value = {
            'cluster': {
                'name': 'test-cluster',
                'endpoint': 'https://ABC123.gr7.us-east-1.eks.amazonaws.com',
                'version': '1.28',
                'status': 'ACTIVE',
                'certificateAuthority': {
                    'data': 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...'
                }
            }
        }
        
        clusters = await discover_clusters(sample_credentials)
        
        assert len(clusters) == 1
        cluster = clusters[0]
        
        # Verify all required fields are present
        assert 'name' in cluster
        assert 'endpoint' in cluster
        assert 'version' in cluster
        assert 'status' in cluster
        assert 'region' in cluster
        assert 'ca_data' in cluster
        
        assert cluster['region'] == sample_credentials.region


class TestK8sClientFactory:
    """Test cases for Kubernetes client factory."""
    
    @patch('cluster_manager.get_eks_bearer_token')
    @patch('cluster_manager.k8s_client')
    @patch('cluster_manager.tempfile.NamedTemporaryFile')
    @patch('cluster_manager.base64.b64decode')
    def test_get_k8s_clients_creates_all_clients(
        self, mock_b64decode, mock_tempfile, mock_k8s_client, mock_get_token,
        sample_credentials, sample_cluster
    ):
        """Test that all required K8s API clients are created."""
        # Mock token generation
        mock_get_token.return_value = "k8s-aws-v1.ABC123..."
        
        # Mock base64 decode
        mock_b64decode.return_value = b"fake-cert-data"
        
        # Mock temp file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test-ca.crt"
        mock_tempfile.return_value = mock_file
        
        # Mock K8s API clients
        mock_api_client = MagicMock()
        mock_k8s_client.ApiClient.return_value = mock_api_client
        
        clients = get_k8s_clients(sample_credentials, sample_cluster)
        
        # Verify all required clients are present
        assert 'core_v1' in clients
        assert 'apps_v1' in clients
        assert 'custom_objects' in clients
        assert 'networking_v1' in clients
        assert 'rbac_v1' in clients
        assert '_api_client' in clients
        assert '_ca_cert_path' in clients
    
    @patch('cluster_manager.get_eks_bearer_token')
    @patch('cluster_manager.k8s_client')
    @patch('cluster_manager.tempfile.NamedTemporaryFile')
    @patch('cluster_manager.base64.b64decode')
    def test_get_k8s_clients_uses_bearer_token(
        self, mock_b64decode, mock_tempfile, mock_k8s_client, mock_get_token,
        sample_credentials, sample_cluster
    ):
        """Test that bearer token is used for authentication."""
        bearer_token = "k8s-aws-v1.TEST_TOKEN_123"
        mock_get_token.return_value = bearer_token
        
        mock_b64decode.return_value = b"fake-cert-data"
        mock_file = MagicMock()
        mock_file.name = "/tmp/test-ca.crt"
        mock_tempfile.return_value = mock_file
        
        mock_config = MagicMock()
        mock_k8s_client.Configuration.return_value = mock_config
        mock_api_client = MagicMock()
        mock_k8s_client.ApiClient.return_value = mock_api_client
        
        get_k8s_clients(sample_credentials, sample_cluster)
        
        # Verify token was generated for the correct cluster
        mock_get_token.assert_called_once_with(sample_credentials, sample_cluster['name'])
    
    @patch('cluster_manager.os.unlink')
    def test_cleanup_k8s_clients(self, mock_unlink):
        """Test cleanup of K8s clients and temp files."""
        mock_api_client = MagicMock()
        mock_conf = MagicMock()
        mock_conf.api_key = {"authorization": "Bearer tok"}
        mock_conf.api_key_prefix = {"authorization": "Bearer"}
        mock_api_client.configuration = mock_conf
        clients = {
            'core_v1': MagicMock(),
            '_api_client': mock_api_client,
            '_ca_cert_path': '/tmp/test-ca.crt'
        }
        
        cleanup_k8s_clients(clients)
        
        # Verify API client was closed and secrets wiped
        mock_api_client.close.assert_called_once()
        assert mock_conf.api_key == {}
        assert mock_conf.api_key_prefix == {}
        
        # Verify temp file was removed; closed marker retained for fail-closed refresh
        mock_unlink.assert_called_once_with('/tmp/test-ca.crt')
        assert clients == {"_closed": True}


class TestClusterCache:
    """Test cases for cluster cache."""
    
    def test_cache_set_and_get(self):
        """Test setting and getting cached clusters."""
        cache = ClusterCache(ttl_seconds=60)
        session_id = "test-session"
        clusters = [{'name': 'cluster-1'}, {'name': 'cluster-2'}]
        
        cache.set(session_id, clusters)
        retrieved = cache.get(session_id)
        
        assert retrieved is not None
        assert len(retrieved) == 2
        assert retrieved[0]['name'] == 'cluster-1'
    
    def test_cache_miss(self):
        """Test cache miss for non-existent session."""
        cache = ClusterCache()
        result = cache.get("nonexistent-session")
        
        assert result is None
    
    def test_cache_expiration(self):
        """Test that cache entries expire after TTL."""
        import time
        
        cache = ClusterCache(ttl_seconds=1)
        session_id = "expiring-session"
        clusters = [{'name': 'cluster-1'}]
        
        cache.set(session_id, clusters)
        
        # Should be retrievable immediately
        assert cache.get(session_id) is not None
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should return None after expiration
        assert cache.get(session_id) is None
    
    def test_cache_invalidate(self):
        """Test manual cache invalidation."""
        cache = ClusterCache()
        session_id = "test-session"
        clusters = [{'name': 'cluster-1'}]
        
        cache.set(session_id, clusters)
        assert cache.get(session_id) is not None
        
        cache.invalidate(session_id)
        assert cache.get(session_id) is None
    
    def test_cache_cleanup_expired(self):
        """Test cleanup of expired cache entries."""
        import time
        
        cache = ClusterCache(ttl_seconds=1)
        
        # Add entries
        for i in range(3):
            cache.set(f"session-{i}", [{'name': f'cluster-{i}'}])
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Add one fresh entry
        cache.set("fresh-session", [{'name': 'fresh-cluster'}])
        
        # Cleanup expired
        removed = cache.cleanup_expired()
        
        assert removed == 3
        assert cache.get("fresh-session") is not None
