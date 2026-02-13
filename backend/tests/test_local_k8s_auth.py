"""
Tests for local_k8s_auth module - kubeconfig parsing, cluster discovery, and client creation.
"""
import pytest
from unittest.mock import Mock, patch, mock_open
import tempfile
import os

from local_k8s_auth import (
    validate_kubeconfig,
    discover_local_clusters,
    get_local_k8s_client,
)


class TestValidateKubeconfig:
    """Tests for validate_kubeconfig function."""

    def test_validate_kubeconfig_valid_file(self, tmp_path):
        """Test validation of a valid kubeconfig file."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://localhost:6443
    name: local-cluster
contexts:
  - context:
      cluster: local-cluster
      user: local-user
    name: local-context
users:
  - name: local-user
    user:
      token: test-token
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = validate_kubeconfig(str(kubeconfig_path))
        
        assert result is True

    def test_validate_kubeconfig_missing_file(self):
        """Test validation returns False for missing file."""
        result = validate_kubeconfig("/nonexistent/path/kubeconfig")
        
        assert result is False

    def test_validate_kubeconfig_directory(self, tmp_path):
        """Test validation returns False when path is a directory."""
        result = validate_kubeconfig(str(tmp_path))
        
        assert result is False

    def test_validate_kubeconfig_missing_apiversion(self, tmp_path):
        """Test validation returns False when apiVersion is missing."""
        kubeconfig_content = """
kind: Config
clusters: []
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = validate_kubeconfig(str(kubeconfig_path))
        
        assert result is False

    def test_validate_kubeconfig_missing_kind(self, tmp_path):
        """Test validation returns False when kind is missing."""
        kubeconfig_content = """
apiVersion: v1
clusters: []
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = validate_kubeconfig(str(kubeconfig_path))
        
        assert result is False

    def test_validate_kubeconfig_invalid_yaml(self, tmp_path):
        """Test validation returns False for invalid YAML."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
  invalid indentation
    broken yaml
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = validate_kubeconfig(str(kubeconfig_path))
        
        assert result is False

    def test_validate_kubeconfig_non_dict_content(self, tmp_path):
        """Test validation returns False when content is not a dict."""
        kubeconfig_content = "- item1\n- item2\n"
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = validate_kubeconfig(str(kubeconfig_path))
        
        assert result is False


class TestDiscoverLocalClusters:
    """Tests for discover_local_clusters function."""

    def test_discover_single_cluster(self, tmp_path):
        """Test discovery of a single cluster/context."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://localhost:6443
    name: local-cluster
contexts:
  - context:
      cluster: local-cluster
      user: local-user
    name: local-context
users:
  - name: local-user
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = discover_local_clusters(str(kubeconfig_path))
        
        assert result == {"local-context": "local-cluster"}

    def test_discover_multiple_clusters(self, tmp_path):
        """Test discovery of multiple clusters/contexts."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://cluster1.example.com
    name: cluster1
  - cluster:
      server: https://cluster2.example.com
    name: cluster2
contexts:
  - context:
      cluster: cluster1
      user: user1
    name: ctx-cluster1
  - context:
      cluster: cluster2
      user: user2
    name: ctx-cluster2
users:
  - name: user1
  - name: user2
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = discover_local_clusters(str(kubeconfig_path))
        
        assert result == {
            "ctx-cluster1": "cluster1",
            "ctx-cluster2": "cluster2",
        }

    def test_discover_no_contexts(self, tmp_path):
        """Test discovery returns empty dict when no contexts."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://localhost:6443
    name: local-cluster
users: []
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = discover_local_clusters(str(kubeconfig_path))
        
        assert result == {}

    def test_discover_missing_file(self):
        """Test discovery returns empty dict for missing file."""
        result = discover_local_clusters("/nonexistent/path/kubeconfig")
        
        assert result == {}

    def test_discover_invalid_yaml(self, tmp_path):
        """Test discovery returns empty dict for invalid YAML."""
        kubeconfig_content = "invalid: yaml: content: ["
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        result = discover_local_clusters(str(kubeconfig_path))
        
        assert result == {}


class TestGetLocalK8sClient:
    """Tests for get_local_k8s_client function."""

    @patch('local_k8s_auth.config.load_kube_config')
    @patch('local_k8s_auth.client.CoreV1Api')
    def test_get_client_default_context(self, mock_corev1, mock_load_config):
        """Test client creation with default context."""
        mock_client = Mock()
        mock_corev1.return_value = mock_client
        
        result = get_local_k8s_client("/path/to/kubeconfig")
        
        mock_load_config.assert_called_once_with(
            config_file="/path/to/kubeconfig",
            context=None
        )
        mock_corev1.assert_called_once()
        assert result == mock_client

    @patch('local_k8s_auth.config.load_kube_config')
    @patch('local_k8s_auth.client.CoreV1Api')
    def test_get_client_specific_context(self, mock_corev1, mock_load_config):
        """Test client creation with specific context."""
        mock_client = Mock()
        mock_corev1.return_value = mock_client
        
        result = get_local_k8s_client("/path/to/kubeconfig", context_name="my-context")
        
        mock_load_config.assert_called_once_with(
            config_file="/path/to/kubeconfig",
            context="my-context"
        )
        mock_corev1.assert_called_once()
        assert result == mock_client

    @patch('local_k8s_auth.config.load_kube_config')
    def test_get_client_config_exception(self, mock_load_config):
        """Test client creation raises ConfigException on config error."""
        from kubernetes.config.config_exception import ConfigException
        
        mock_load_config.side_effect = ConfigException("Invalid kubeconfig")
        
        with pytest.raises(ConfigException):
            get_local_k8s_client("/path/to/kubeconfig")

    @patch('local_k8s_auth.config.load_kube_config')
    def test_get_client_generic_exception(self, mock_load_config):
        """Test client creation raises exception on generic error."""
        mock_load_config.side_effect = RuntimeError("Unexpected error")
        
        with pytest.raises(RuntimeError):
            get_local_k8s_client("/path/to/kubeconfig")


class TestKubeconfigIntegration:
    """Integration tests for kubeconfig workflows."""

    def test_full_validation_and_discovery_workflow(self, tmp_path):
        """Test complete workflow: validate then discover."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://prod.example.com
    name: prod-cluster
  - cluster:
      server: https://dev.example.com
    name: dev-cluster
contexts:
  - context:
      cluster: prod-cluster
      user: prod-user
    name: prod-context
  - context:
      cluster: dev-cluster
      user: dev-user
    name: dev-context
users:
  - name: prod-user
  - name: dev-user
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        # Step 1: Validate
        is_valid = validate_kubeconfig(str(kubeconfig_path))
        assert is_valid is True
        
        # Step 2: Discover
        clusters = discover_local_clusters(str(kubeconfig_path))
        assert clusters == {
            "prod-context": "prod-cluster",
            "dev-context": "dev-cluster",
        }

    def test_invalid_kubeconfig_short_circuits(self, tmp_path):
        """Test that invalid kubeconfig fails validation before discovery."""
        kubeconfig_content = """
# Missing apiVersion and kind
clusters: []
"""
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(kubeconfig_content)
        
        # Validation should fail
        is_valid = validate_kubeconfig(str(kubeconfig_path))
        assert is_valid is False
        
        # Discovery would still work on partial content but validation caught the issue
        clusters = discover_local_clusters(str(kubeconfig_path))
        assert clusters == {}
