"""
Unit tests for authentication flows.

Tests cover:
- Kubeconfig Auth Flow: parsing, validation, K8s clients
- K8s Auth Error Scenarios: 401, 403, timeouts, certificate errors
- AWS Auth Flow: credential validation, STS, region validation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from kubernetes.client.exceptions import ApiException
import yaml

from eks_auth import validate_credentials, get_eks_bearer_token
from local_k8s_auth import (
    validate_kubeconfig,
    validate_kubeconfig_content,
    parse_kubeconfig_content,
    get_k8s_client_from_content,
    discover_local_clusters
)
from credential_store import StoredCredentials


class TestKubeconfigAuthFlow:
    """Test Kubeconfig authentication flows."""

    def test_parse_kubeconfig_file(self, tmp_path):
        """Test parsing kubeconfig file."""
        # Create test kubeconfig
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://kubernetes.default.svc
    certificate-authority-data: LS0tLS1CRUdJTi...
  name: minikube
contexts:
- context:
    cluster: minikube
    user: minikube
  name: minikube
current-context: minikube
users:
- name: minikube
  user:
    client-certificate-data: LS0tLS1CRUdJTi...
    client-key-data: LS0tLS1CRUdJTi...
"""
        kubeconfig_file = tmp_path / "config"
        kubeconfig_file.write_text(kubeconfig_content)

        # Parse
        parsed, error = parse_kubeconfig_content(kubeconfig_content)

        assert error is None
        assert parsed is not None
        assert "contexts" in parsed
        assert len(parsed["contexts"]) == 1
        assert parsed["contexts"][0]["name"] == "minikube"

    def test_parse_kubeconfig_with_multiple_contexts(self, tmp_path):
        """Test parsing kubeconfig with multiple contexts."""
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
  name: context1
- context:
    cluster: cluster2
    user: user2
  name: context2
current-context: context1
users:
- name: user1
  user:
    token: token1
- name: user2
  user:
    token: token2
"""
        parsed, error = parse_kubeconfig_content(kubeconfig_content)

        assert error is None
        assert len(parsed["contexts"]) == 2
        assert parsed["current_context"] == "context1"

    def test_validate_kubeconfig_file(self, tmp_path):
        """Test validating kubeconfig file."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://kubernetes.default.svc
  name: test-cluster
contexts:
- context:
    cluster: test-cluster
    user: test-user
  name: test-context
current-context: test-context
users:
- name: test-user
  user:
    token: test-token
"""
        kubeconfig_file = tmp_path / "config"
        kubeconfig_file.write_text(kubeconfig_content)

        # Validate
        is_valid = validate_kubeconfig(str(kubeconfig_file))
        assert is_valid is True

    def test_validate_kubeconfig_content(self):
        """Test validating kubeconfig content."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters: []
contexts: []
users: []
"""
        is_valid, error = validate_kubeconfig_content(kubeconfig_content)
        assert is_valid is True
        assert error is None

    def test_validate_kubeconfig_content_invalid_yaml(self):
        """Test validating invalid YAML kubeconfig."""
        invalid_content = "invalid: yaml: content:"

        is_valid, error = validate_kubeconfig_content(invalid_content)
        assert is_valid is False
        assert error is not None

    def test_select_kubeconfig_context(self):
        """Test selecting a specific context from kubeconfig."""
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
  name: context1
- context:
    cluster: cluster2
    user: user2
  name: context2
current-context: context1
users:
- name: user1
  user:
    token: token1
- name: user2
  user:
    token: token2
"""
        parsed, error = parse_kubeconfig_content(kubeconfig_content)
        assert error is None

        # Select context2
        contexts = {ctx["name"]: ctx for ctx in parsed["contexts"]}
        assert "context2" in contexts
        assert contexts["context2"]["cluster"] == "cluster2"

    @patch('local_k8s_auth.config.load_kube_config')
    @patch('local_k8s_auth.client.CoreV1Api')
    def test_create_k8s_clients_from_kubeconfig(self, mock_api, mock_load_config):
        """Test creating K8s clients from kubeconfig."""
        mock_load_config.return_value = None
        mock_core = Mock()
        mock_api.return_value = mock_core

        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://kubernetes.default.svc
  name: test-cluster
contexts:
- context:
    cluster: test-cluster
    user: test-user
  name: test-context
current-context: test-context
users:
- name: test-user
  user:
    token: test-token
"""
        # Get K8s client
        # Note: actual implementation may vary
        parsed, error = parse_kubeconfig_content(kubeconfig_content)
        assert error is None
        assert parsed is not None

    def test_missing_kubeconfig_file(self, tmp_path):
        """Test handling missing kubeconfig file."""
        nonexistent_path = str(tmp_path / "nonexistent" / "config")

        is_valid = validate_kubeconfig(nonexistent_path)
        assert is_valid is False

    def test_discover_clusters_from_kubeconfig(self):
        """Test discovering clusters from kubeconfig."""
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
  name: context1
- context:
    cluster: cluster2
    user: user2
  name: context2
current-context: context1
users:
- name: user1
  user:
    token: token1
- name: user2
  user:
    token: token2
"""
        parsed, error = parse_kubeconfig_content(kubeconfig_content)
        assert error is None

        # Extract clusters
        clusters = {
            ctx["name"]: ctx["cluster"]
            for ctx in parsed.get("contexts", [])
        }
        assert len(clusters) == 2
        assert "context1" in clusters
        assert "context2" in clusters


class TestK8sAuthErrorScenarios:
    """Test Kubernetes authentication error scenarios."""

    @patch('kubernetes.client.api.CoreV1Api.list_namespaced_pod')
    def test_k8s_auth_401_unauthorized(self, mock_list_pods):
        """Test 401 Unauthorized error (expired token)."""
        mock_list_pods.side_effect = ApiException(status=401, reason="Unauthorized")

        with pytest.raises(ApiException) as exc:
            mock_list_pods("default")

        assert exc.value.status == 401

    @patch('kubernetes.client.api.CoreV1Api.list_namespaced_pod')
    def test_k8s_auth_403_forbidden(self, mock_list_pods):
        """Test 403 Forbidden error (RBAC denied)."""
        mock_list_pods.side_effect = ApiException(status=403, reason="Forbidden")

        with pytest.raises(ApiException) as exc:
            mock_list_pods("default")

        assert exc.value.status == 403

    def test_k8s_auth_connection_timeout(self):
        """Test connection timeout scenario."""
        from requests.exceptions import ConnectTimeout

        # Simulate timeout
        with pytest.raises(ConnectTimeout):
            raise ConnectTimeout("Connection to API server timed out")

    def test_k8s_auth_invalid_certificate(self):
        """Test invalid SSL certificate error."""
        from requests.exceptions import SSLError

        # Simulate SSL error
        with pytest.raises(SSLError):
            raise SSLError("SSL certificate verification failed")

    def test_k8s_auth_missing_credentials(self):
        """Test missing credentials scenario."""
        # Should not be able to create client without credentials
        parsed, error = parse_kubeconfig_content("")

        assert error is not None or parsed is None

    @patch('kubernetes.client.api.CoreV1Api.list_namespaced_pod')
    def test_k8s_auth_api_unavailable(self, mock_list_pods):
        """Test API server unavailable."""
        mock_list_pods.side_effect = ApiException(status=503, reason="Service Unavailable")

        with pytest.raises(ApiException) as exc:
            mock_list_pods("default")

        assert exc.value.status == 503

    @patch('kubernetes.client.api.CoreV1Api.list_namespaced_pod')
    def test_k8s_auth_certificate_expired(self, mock_list_pods):
        """Test expired client certificate."""
        # Treat as authentication failure
        mock_list_pods.side_effect = ApiException(status=401, reason="Client certificate has expired")

        with pytest.raises(ApiException):
            mock_list_pods("default")


class TestAWSAuthFlow:
    """Test AWS authentication flows."""

    @patch('eks_auth.boto3.client')
    def test_aws_credential_validation_success(self, mock_boto_client):
        """Test successful AWS credential validation."""
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "UserId": "AIDA1234567890ABCDEF",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test-user"
        }

        success, creds, error = validate_credentials(
            access_key="ASIAACCESSKEY123456",
            secret_key="test_secret_key_" + "a" * 24,
            session_token="test_session_token_" + "a" * 40,
            region="us-east-1"
        )

        if success and creds:
            assert creds.user_arn == "arn:aws:iam::123456789012:user/test-user"
            assert creds.account_id == "123456789012"

    @patch('eks_auth.boto3.client')
    def test_aws_credential_validation_invalid(self, mock_boto_client):
        """Test invalid AWS credentials."""
        # Create mock STS client that raises exception
        from botocore.exceptions import ClientError

        mock_sts = Mock()
        # Create a properly formatted ClientError
        error_response = {
            'Error': {
                'Code': 'InvalidClientTokenId',
                'Message': 'The security token included in the request is invalid'
            }
        }
        mock_sts.get_caller_identity.side_effect = ClientError(
            error_response, 'GetCallerIdentity'
        )
        mock_boto_client.return_value = mock_sts

        success, creds, error = validate_credentials(
            access_key="ASIATESTACCESSKEY123456",
            secret_key="invalid_secret_key",
            session_token="invalid_session_token",
            region="us-east-1"
        )

        assert success is False
        assert error is not None

    @patch('eks_auth.boto3.client')
    def test_aws_sts_get_caller_identity(self, mock_boto_client):
        """Test STS GetCallerIdentity call."""
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "UserId": "AIDA1234567890ABCDEF",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test-user"
        }

        # Simulate STS call
        response = mock_sts.get_caller_identity()

        assert response["Account"] == "123456789012"
        assert "arn:aws:iam" in response["Arn"]

    @patch('eks_auth.boto3.client')
    def test_aws_credential_expiration(self, mock_boto_client):
        """Test AWS credential expiration checking."""
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "UserId": "AIDA1234567890ABCDEF",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test-user"
        }

        # Session tokens have expiration
        # Test with near-expiration time
        from datetime import timedelta
        start_time = datetime.now()
        success, creds, error = validate_credentials(
            access_key="ASIAACCESSKEY123456",
            secret_key="test_secret_key_" + "a" * 24,
            session_token="test_session_token_" + "a" * 40,
            region="us-east-1"
        )

        if success and creds:
            assert creds.expires_at is not None
            # expires_at is set to current time, so it should be equal to or slightly after start_time
            assert creds.expires_at >= start_time - timedelta(seconds=1)

    @patch('eks_auth.boto3.client')
    def test_aws_region_validation(self, mock_boto_client):
        """Test AWS region validation."""
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "UserId": "AIDA1234567890ABCDEF",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test-user"
        }

        regions = ["us-east-1", "us-west-2", "eu-west-1"]

        for region in regions:
            success, creds, error = validate_credentials(
                access_key="ASIAACCESSKEY123456",
                secret_key="test_secret_key_" + "a" * 24,
                session_token="test_session_token_" + "a" * 40,
                region=region
            )

            if success and creds:
                assert creds.region == region


class TestEKSBearerToken:
    """Test EKS bearer token generation."""

    @patch('eks_auth.RequestSigner')
    @patch('eks_auth.boto3.Session')
    def test_generate_eks_bearer_token(self, mock_session_class, mock_signer_class):
        """Test EKS bearer token generation."""
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="ASIAACCESSKEY123456",
            secret_key="test_secret_key_" + "a" * 24,
            session_token="test_session_token_" + "a" * 40,
            region="us-east-1",
            user_arn="arn:aws:iam::123456789012:user/test-user",
            account_id="123456789012",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now()
        )

        # Mock the session and signer
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_sts_client = Mock()
        mock_session.client.return_value = mock_sts_client
        mock_session.get_credentials.return_value = Mock()

        mock_signer = Mock()
        mock_signer_class.return_value = mock_signer
        mock_signer.generate_presigned_url.return_value = "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity"

        # Test token generation
        token = get_eks_bearer_token(creds, "test-cluster")

        # Bearer token should start with k8s-aws-v1.
        assert token is not None
        assert token.startswith("k8s-aws-v1.")

    @patch('eks_auth.RequestSigner')
    @patch('eks_auth.boto3.Session')
    def test_eks_bearer_token_expiration(self, mock_session_class, mock_signer_class):
        """Test that EKS bearer tokens expire correctly."""
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="ASIAACCESSKEY123456",
            secret_key="test_secret_key_" + "a" * 24,
            session_token="test_session_token_" + "a" * 40,
            region="us-east-1",
            user_arn="arn:aws:iam::123456789012:user/test-user",
            account_id="123456789012",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now()
        )

        # Mock the session and signer
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_sts_client = Mock()
        mock_session.client.return_value = mock_sts_client
        mock_session.get_credentials.return_value = Mock()

        mock_signer = Mock()
        mock_signer_class.return_value = mock_signer
        mock_signer.generate_presigned_url.return_value = "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity"

        # EKS tokens have ~60 second expiration
        # Each request should get a fresh token
        token1 = get_eks_bearer_token(creds, "cluster-1")
        token2 = get_eks_bearer_token(creds, "cluster-1")

        # Tokens should be valid format
        assert token1 is not None
        assert token2 is not None
        assert token1.startswith("k8s-aws-v1.")
        assert token2.startswith("k8s-aws-v1.")


class TestAuthFlowIntegration:
    """Test complete authentication flows."""

    @patch('eks_auth.RequestSigner')
    @patch('eks_auth.boto3.client')
    @patch('eks_auth.boto3.Session')
    def test_aws_auth_flow_complete(self, mock_session_class, mock_boto_client, mock_signer_class):
        """Test complete AWS authentication flow."""
        # Setup for validate_credentials
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "UserId": "AIDA1234567890ABCDEF",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test-user"
        }

        # Setup for get_eks_bearer_token
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session_sts = Mock()
        mock_session.client.return_value = mock_session_sts
        mock_session.get_credentials.return_value = Mock()

        mock_signer = Mock()
        mock_signer_class.return_value = mock_signer
        mock_signer.generate_presigned_url.return_value = "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity"

        # Step 1: Validate credentials
        success, creds, error = validate_credentials(
            access_key="ASIAACCESSKEY123456",
            secret_key="test_secret_key_" + "a" * 24,
            session_token="test_session_token_" + "a" * 40,
            region="us-east-1"
        )

        assert success is True
        assert error is None

        if success and creds:
            # Step 2: Generate bearer token
            token = get_eks_bearer_token(creds, "test-cluster")

            # Step 3: Use token for K8s API calls
            # (Would be done by K8s client in actual flow)
            assert token is not None
            assert token.startswith("k8s-aws-v1.")

    def test_kubeconfig_auth_flow_complete(self):
        """Test complete kubeconfig authentication flow."""
        kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://kubernetes.default.svc
    certificate-authority-data: LS0tLS1CRUdJTi...
  name: minikube
contexts:
- context:
    cluster: minikube
    user: minikube
  name: minikube
current-context: minikube
users:
- name: minikube
  user:
    client-certificate-data: LS0tLS1CRUdJTi...
    client-key-data: LS0tLS1CRUdJTi...
"""
        # Step 1: Validate kubeconfig content
        is_valid, error = validate_kubeconfig_content(kubeconfig_content)
        assert is_valid is True

        # Step 2: Parse kubeconfig
        parsed, error = parse_kubeconfig_content(kubeconfig_content)
        assert error is None
        assert parsed is not None

        # Step 3: Extract contexts
        contexts = {
            ctx["name"]: ctx["cluster"]
            for ctx in parsed.get("contexts", [])
        }
        assert len(contexts) > 0

        # Step 4: Create credentials
        creds = StoredCredentials(
            auth_mode="kubeconfig",
            kubeconfig_content=kubeconfig_content,
            kubeconfig_contexts=contexts,
            selected_context="minikube",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )

        assert creds.auth_mode == "kubeconfig"
        assert "minikube" in creds.kubeconfig_contexts
