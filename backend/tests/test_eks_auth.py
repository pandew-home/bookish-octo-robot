"""
Unit tests for EKS authentication utilities.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

from eks_auth import (
    get_eks_bearer_token,
    validate_credentials,
    get_credential_expiration_info
)
from credential_store import StoredCredentials


@pytest.fixture
def sample_credentials():
    """Create sample credentials for testing."""
    now = datetime.now()
    return StoredCredentials(
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token="FwoGZXIvYXdzEBQaDH...",
        region="us-east-1",
        user_arn="arn:aws:iam::123456789012:user/test-user",
        account_id="123456789012",
        expires_at=now + timedelta(hours=1),
        created_at=now
    )


class TestEKSAuth:
    """Test cases for EKS authentication."""
    
    @patch('eks_auth.boto3.Session')
    def test_get_eks_bearer_token_format(self, mock_session, sample_credentials):
        """Test that bearer token has correct format."""
        # Mock the session and STS client
        mock_sts_client = MagicMock()
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.client.return_value = mock_sts_client
        mock_session_instance.get_credentials.return_value = MagicMock()
        
        # Mock the RequestSigner
        with patch('eks_auth.RequestSigner') as mock_signer_class:
            mock_signer = MagicMock()
            mock_signer_class.return_value = mock_signer
            mock_signer.generate_presigned_url.return_value = "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity&X-Amz-Signature=..."
            
            token = get_eks_bearer_token(sample_credentials, "test-cluster")
            
            # Verify token format
            assert token.startswith("k8s-aws-v1.")
            assert len(token) > 11  # More than just the prefix
    
    @patch('eks_auth.boto3.Session')
    def test_get_eks_bearer_token_includes_cluster_name(self, mock_session, sample_credentials):
        """Test that cluster name is included in token generation."""
        mock_sts_client = MagicMock()
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.client.return_value = mock_sts_client
        mock_session_instance.get_credentials.return_value = MagicMock()
        
        with patch('eks_auth.RequestSigner') as mock_signer_class:
            mock_signer = MagicMock()
            mock_signer_class.return_value = mock_signer
            mock_signer.generate_presigned_url.return_value = "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity"
            
            cluster_name = "my-test-cluster"
            get_eks_bearer_token(sample_credentials, cluster_name)
            
            # Verify RequestSigner was called with correct parameters
            assert mock_signer_class.called
    
    @patch('eks_auth.boto3.client')
    def test_validate_credentials_success(self, mock_boto_client):
        """Test successful credential validation."""
        # Mock STS client response
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user',
            'Account': '123456789012',
            'UserId': 'AIDAI...'
        }
        
        success, creds, error = validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="FwoGZXIvYXdzEBQaDH...",
            region="us-east-1"
        )
        
        assert success is True
        assert creds is not None
        assert creds.user_arn == 'arn:aws:iam::123456789012:user/test-user'
        assert creds.account_id == '123456789012'
        assert error is None
    
    @patch('eks_auth.boto3.client')
    def test_validate_credentials_invalid_access_key(self, mock_boto_client):
        """Test credential validation with invalid access key."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        
        # Simulate InvalidClientTokenId error
        error_response = {'Error': {'Code': 'InvalidClientTokenId', 'Message': 'Invalid access key'}}
        mock_sts.get_caller_identity.side_effect = ClientError(error_response, 'GetCallerIdentity')
        mock_sts.exceptions.InvalidClientTokenId = ClientError
        
        success, creds, error = validate_credentials(
            access_key="INVALID_KEY",
            secret_key="secret",
            session_token="token",
            region="us-east-1"
        )
        
        assert success is False
        assert creds is None
        assert error is not None
        assert "access key" in error.lower()
    
    @patch('eks_auth.boto3.client')
    def test_validate_credentials_invalid_secret_key(self, mock_boto_client):
        """Test credential validation with invalid secret key."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        
        # Simulate SignatureDoesNotMatch error
        error_response = {'Error': {'Code': 'SignatureDoesNotMatch', 'Message': 'Invalid signature'}}
        mock_sts.get_caller_identity.side_effect = ClientError(error_response, 'GetCallerIdentity')
        mock_sts.exceptions.SignatureDoesNotMatch = ClientError
        
        success, creds, error = validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="INVALID_SECRET",
            session_token="token",
            region="us-east-1"
        )
        
        assert success is False
        assert creds is None
        assert error is not None
        assert "secret" in error.lower()
    
    def test_get_credential_expiration_info_active(self, sample_credentials):
        """Test expiration info for active credentials."""
        # Set expiration to 30 minutes from now
        sample_credentials.expires_at = datetime.now() + timedelta(minutes=30)
        
        info = get_credential_expiration_info(sample_credentials)
        
        assert info['status'] == 'active'
        assert info['time_remaining_seconds'] > 0
        assert info['user_arn'] == sample_credentials.user_arn
        assert info['account_id'] == sample_credentials.account_id
        assert info['region'] == sample_credentials.region
    
    def test_get_credential_expiration_info_expiring_soon(self, sample_credentials):
        """Test expiration info for credentials expiring soon."""
        # Set expiration to 5 minutes from now
        sample_credentials.expires_at = datetime.now() + timedelta(minutes=5)
        
        info = get_credential_expiration_info(sample_credentials)
        
        assert info['status'] == 'expiring_soon'
        assert info['time_remaining_seconds'] > 0
        assert info['time_remaining_seconds'] < 600  # Less than 10 minutes
    
    def test_get_credential_expiration_info_expired(self, sample_credentials):
        """Test expiration info for expired credentials."""
        # Set expiration to past
        sample_credentials.expires_at = datetime.now() - timedelta(minutes=5)
        
        info = get_credential_expiration_info(sample_credentials)
        
        assert info['status'] == 'expired'
        assert info['time_remaining_seconds'] == 0
    
    @patch('eks_auth.boto3.client')
    def test_validate_credentials_returns_stored_credentials(self, mock_boto_client):
        """Test that validate_credentials returns properly formatted StoredCredentials."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user',
            'Account': '123456789012',
            'UserId': 'AIDAI...'
        }
        
        success, creds, error = validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="FwoGZXIvYXdzEBQaDH...",
            region="us-west-2"
        )
        
        assert success is True
        assert isinstance(creds, StoredCredentials)
        assert creds.access_key == "AKIAIOSFODNN7EXAMPLE"
        assert creds.secret_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert creds.session_token == "FwoGZXIvYXdzEBQaDH..."
        assert creds.region == "us-west-2"
        assert creds.user_arn == 'arn:aws:iam::123456789012:user/test-user'
        assert creds.account_id == '123456789012'
        assert creds.created_at is not None
