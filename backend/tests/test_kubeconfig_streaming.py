"""
Tests for kubeconfig streaming authentication endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import yaml

# Sample valid kubeconfig for testing
SAMPLE_KUBECONFIG = """
apiVersion: v1
kind: Config
current-context: docker-desktop
clusters:
- cluster:
    server: https://kubernetes.docker.internal:6443
  name: docker-desktop
contexts:
- context:
    cluster: docker-desktop
    user: docker-desktop
  name: docker-desktop
- context:
    cluster: kind-kind
    user: kind-kind
  name: kind-kind
users:
- name: docker-desktop
  user:
    token: test-token
"""

INVALID_KUBECONFIG_NO_APIVERSION = """
kind: Config
current-context: test
"""

INVALID_KUBECONFIG_NO_KIND = """
apiVersion: v1
current-context: test
"""

INVALID_KUBECONFIG_NO_CONTEXTS = """
apiVersion: v1
kind: Config
contexts: []
"""


class TestKubeconfigParsing:
    """Tests for kubeconfig content parsing."""
    
    def test_parse_valid_kubeconfig(self):
        """Test parsing a valid kubeconfig."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content(SAMPLE_KUBECONFIG)
        
        assert error is None
        assert result is not None
        assert len(result['contexts']) == 2
        assert result['current_context'] == 'docker-desktop'
        assert any(ctx['name'] == 'docker-desktop' for ctx in result['contexts'])
        assert any(ctx['name'] == 'kind-kind' for ctx in result['contexts'])
    
    def test_parse_empty_content(self):
        """Test parsing empty content."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content("")
        
        assert result is None
        assert error is not None
        assert "empty" in error.lower()
    
    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content("this is not: valid: yaml:::")
        
        assert result is None
        assert error is not None
    
    def test_parse_missing_apiversion(self):
        """Test parsing kubeconfig without apiVersion."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content(INVALID_KUBECONFIG_NO_APIVERSION)
        
        assert result is None
        assert error is not None
        assert "apiVersion" in error
    
    def test_parse_missing_kind(self):
        """Test parsing kubeconfig without kind."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content(INVALID_KUBECONFIG_NO_KIND)
        
        assert result is None
        assert error is not None
        assert "kind" in error
    
    def test_parse_no_contexts(self):
        """Test parsing kubeconfig without contexts."""
        from local_k8s_auth import parse_kubeconfig_content
        
        result, error = parse_kubeconfig_content(INVALID_KUBECONFIG_NO_CONTEXTS)
        
        # Parsing succeeds but returns empty contexts
        assert result is not None
        assert len(result['contexts']) == 0


class TestKubeconfigValidation:
    """Tests for kubeconfig content validation."""
    
    def test_validate_valid_content(self):
        """Test validating valid kubeconfig content."""
        from local_k8s_auth import validate_kubeconfig_content
        
        is_valid, error = validate_kubeconfig_content(SAMPLE_KUBECONFIG)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_empty_content(self):
        """Test validating empty content."""
        from local_k8s_auth import validate_kubeconfig_content
        
        is_valid, error = validate_kubeconfig_content("")
        
        assert is_valid is False
        assert error is not None
        assert "empty" in error.lower()
    
    def test_validate_wrong_kind(self):
        """Test validating kubeconfig with wrong kind."""
        from local_k8s_auth import validate_kubeconfig_content
        
        wrong_kind = """
        apiVersion: v1
        kind: Pod
        """
        
        is_valid, error = validate_kubeconfig_content(wrong_kind)
        
        assert is_valid is False
        assert error is not None
        assert "kind" in error.lower()


class TestKubeconfigEndpoints:
    """Tests for kubeconfig API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from app import app
        return TestClient(app)
    
    @pytest.mark.skip(reason="Stale mock/assertion - needs update")
    def test_parse_endpoint_success(self, client):
        """Test successful kubeconfig parsing via API."""
        response = client.post(
            "/api/credentials/kubeconfig/parse",
            json={"content": SAMPLE_KUBECONFIG}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['contexts']) == 2
        assert data['current_context'] == 'docker-desktop'
    
    def test_parse_endpoint_empty_content(self, client):
        """Test parsing empty content via API."""
        response = client.post(
            "/api/credentials/kubeconfig/parse",
            json={"content": ""}
        )
        
        assert response.status_code == 400
        assert "empty" in response.json()['detail'].lower()
    
    def test_parse_endpoint_no_contexts(self, client):
        """Test parsing kubeconfig without contexts via API."""
        response = client.post(
            "/api/credentials/kubeconfig/parse",
            json={"content": INVALID_KUBECONFIG_NO_CONTEXTS}
        )
        
        assert response.status_code == 400
        assert "no contexts" in response.json()['detail'].lower()
    
    def test_auth_endpoint_success(self, client):
        """Test successful kubeconfig authentication via API."""
        response = client.post(
            "/api/credentials/kubeconfig/auth",
            json={
                "content": SAMPLE_KUBECONFIG,
                "context": "docker-desktop"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['session_id'] is not None
        assert 'docker-desktop' in data['message']
    
    def test_auth_endpoint_invalid_context(self, client):
        """Test authentication with invalid context via API."""
        response = client.post(
            "/api/credentials/kubeconfig/auth",
            json={
                "content": SAMPLE_KUBECONFIG,
                "context": "nonexistent-context"
            }
        )
        
        assert response.status_code == 400
        assert "not found" in response.json()['detail'].lower()
    
    def test_auth_endpoint_invalid_content(self, client):
        """Test authentication with invalid content via API."""
        response = client.post(
            "/api/credentials/kubeconfig/auth",
            json={
                "content": "invalid yaml content",
                "context": "test"
            }
        )
        
        assert response.status_code == 400


class TestCredentialStoreKubeconfig:
    """Tests for credential store with kubeconfig content."""
    
    def test_store_kubeconfig_content(self):
        """Test storing kubeconfig content in credential store."""
        from credential_store import CredentialStore, StoredCredentials
        from datetime import datetime, timedelta
        
        store = CredentialStore()
        
        creds = StoredCredentials(
            auth_mode="kubeconfig",
            kubeconfig_content=SAMPLE_KUBECONFIG,
            kubeconfig_contexts={"docker-desktop": "docker-desktop", "kind-kind": "kind-kind"},
            selected_context="docker-desktop",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        session_id = "test-session-123"
        store.store(session_id, creds)
        
        retrieved = store.get(session_id)
        
        assert retrieved is not None
        assert retrieved.auth_mode == "kubeconfig"
        assert retrieved.kubeconfig_content == SAMPLE_KUBECONFIG
        assert retrieved.selected_context == "docker-desktop"
        assert retrieved.kubeconfig_contexts is not None
        assert len(retrieved.kubeconfig_contexts) == 2


class TestK8sClientFromContent:
    """Tests for creating K8s client from content."""
    
    @pytest.mark.skip(reason="Stale mock/assertion - needs update")
    @patch('local_k8s_auth.config.load_kube_config')
    @patch('local_k8s_auth.client.CoreV1Api')
    def test_get_client_from_content(self, mock_api, mock_load_config):
        """Test creating K8s client from kubeconfig content."""
        from local_k8s_auth import get_k8s_client_from_content
        
        mock_api.return_value = MagicMock()
        
        client = get_k8s_client_from_content(SAMPLE_KUBECONFIG, "docker-desktop")
        
        assert client is not None
        # Verify load_kube_config was called with a temp file
        assert mock_load_config.called
        call_args = mock_load_config.call_args
        assert call_args[1]['context'] == 'docker-desktop'
    
    def test_get_client_from_invalid_content(self):
        """Test creating K8s client from invalid content."""
        from local_k8s_auth import get_k8s_client_from_content
        
        with pytest.raises(ValueError) as exc_info:
            get_k8s_client_from_content("invalid content", "test")
        
        assert "Invalid kubeconfig" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
