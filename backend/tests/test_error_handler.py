"""
Unit tests for error handler.
"""
import pytest
from unittest.mock import Mock
from fastapi import HTTPException
from botocore.exceptions import ClientError, BotoCoreError
from kubernetes.client.exceptions import ApiException

from utils.error_handler import (
    handle_aws_error,
    handle_k8s_error,
    handle_generic_error,
    create_error_response,
    get_error_message,
    UserFriendlyError
)


class TestAWSErrorHandling:
    """Test cases for AWS error handling."""
    
    def test_handle_invalid_access_key(self):
        """Test handling of invalid access key error."""
        error = ClientError(
            {'Error': {'Code': 'InvalidClientTokenId', 'Message': 'Invalid access key'}},
            'GetCallerIdentity'
        )
        
        http_error = handle_aws_error(error, "validating credentials")
        
        assert http_error.status_code == 401
        assert "access key" in http_error.detail.lower()
        assert "kion" in http_error.detail.lower()
    
    def test_handle_invalid_secret_key(self):
        """Test handling of invalid secret key error."""
        error = ClientError(
            {'Error': {'Code': 'SignatureDoesNotMatch', 'Message': 'Invalid signature'}},
            'GetCallerIdentity'
        )
        
        http_error = handle_aws_error(error, "validating credentials")
        
        assert http_error.status_code == 401
        assert "secret key" in http_error.detail.lower()
    
    def test_handle_expired_token(self):
        """Test handling of expired token error."""
        error = ClientError(
            {'Error': {'Code': 'ExpiredToken', 'Message': 'Token expired'}},
            'ListClusters'
        )
        
        http_error = handle_aws_error(error, "listing clusters")
        
        assert http_error.status_code == 401
        assert "expired" in http_error.detail.lower()
        assert "kion" in http_error.detail.lower()
    
    def test_handle_access_denied(self):
        """Test handling of access denied error."""
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'DescribeCluster'
        )
        
        http_error = handle_aws_error(error, "describe cluster")
        
        assert http_error.status_code == 403
        assert "permission" in http_error.detail.lower()
        assert "describe cluster" in http_error.detail.lower()
    
    def test_handle_resource_not_found(self):
        """Test handling of resource not found error."""
        error = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Not found'}},
            'DescribeCluster'
        )
        
        http_error = handle_aws_error(error, "cluster")
        
        assert http_error.status_code == 404
        assert "not found" in http_error.detail.lower()
    
    def test_handle_throttling(self):
        """Test handling of throttling error."""
        error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'ListClusters'
        )
        
        http_error = handle_aws_error(error, "listing clusters")
        
        assert http_error.status_code == 429
        assert "too many" in http_error.detail.lower() or "wait" in http_error.detail.lower()
    
    def test_handle_botocore_error(self):
        """Test handling of BotoCore connection errors."""
        error = BotoCoreError()
        
        http_error = handle_aws_error(error, "connecting to AWS")
        
        assert http_error.status_code == 500
        assert "connection" in http_error.detail.lower()
    
    def test_handle_unknown_aws_error(self):
        """Test handling of unknown AWS errors."""
        error = ClientError(
            {'Error': {'Code': 'UnknownError', 'Message': 'Something went wrong'}},
            'SomeOperation'
        )
        
        http_error = handle_aws_error(error, "performing operation")
        
        assert http_error.status_code == 500
        assert "error" in http_error.detail.lower()


class TestK8sErrorHandling:
    """Test cases for Kubernetes error handling."""
    
    def test_handle_k8s_401_unauthorized(self):
        """Test handling of K8s 401 unauthorized error."""
        error = ApiException(status=401, reason="Unauthorized")
        
        http_error = handle_k8s_error(error, "accessing pods")
        
        assert http_error.status_code == 401
        assert "authentication" in http_error.detail.lower()
    
    def test_handle_k8s_403_forbidden(self):
        """Test handling of K8s 403 forbidden error."""
        error = ApiException(status=403, reason="Forbidden")
        
        http_error = handle_k8s_error(error, "listing deployments")
        
        assert http_error.status_code == 403
        assert "permission" in http_error.detail.lower()
        assert "listing deployments" in http_error.detail.lower()
    
    def test_handle_k8s_404_not_found(self):
        """Test handling of K8s 404 not found error."""
        error = ApiException(status=404, reason="Not Found")
        
        http_error = handle_k8s_error(error, "pod 'my-pod'")
        
        assert http_error.status_code == 404
        assert "not found" in http_error.detail.lower()
        assert "pod 'my-pod'" in http_error.detail.lower()
    
    def test_handle_k8s_409_conflict(self):
        """Test handling of K8s 409 conflict error."""
        error = ApiException(status=409, reason="Conflict")
        
        http_error = handle_k8s_error(error, "creating resource")
        
        assert http_error.status_code == 409
        assert "conflict" in http_error.detail.lower()
    
    def test_handle_k8s_429_rate_limit(self):
        """Test handling of K8s 429 rate limit error."""
        error = ApiException(status=429, reason="Too Many Requests")
        
        http_error = handle_k8s_error(error, "querying API")
        
        assert http_error.status_code == 429
        assert "too many" in http_error.detail.lower()
    
    def test_handle_k8s_500_server_error(self):
        """Test handling of K8s 500 server error."""
        error = ApiException(status=500, reason="Internal Server Error")
        
        http_error = handle_k8s_error(error, "accessing cluster")
        
        assert http_error.status_code == 503
        assert "cluster" in http_error.detail.lower()
    
    def test_handle_non_api_exception(self):
        """Test handling of non-ApiException K8s errors."""
        error = Exception("Connection timeout")
        
        http_error = handle_k8s_error(error, "connecting to cluster")
        
        assert http_error.status_code == 500
        assert "error" in http_error.detail.lower()


class TestGenericErrorHandling:
    """Test cases for generic error handling."""
    
    def test_handle_generic_error_with_custom_message(self):
        """Test handling generic error with custom message."""
        error = ValueError("Invalid value")
        
        http_error = handle_generic_error(
            error,
            "processing request",
            "The value you provided is invalid. Please check and try again."
        )
        
        assert http_error.status_code == 500
        assert "invalid" in http_error.detail.lower()
    
    def test_handle_generic_error_without_custom_message(self):
        """Test handling generic error without custom message."""
        error = RuntimeError("Something broke")
        
        http_error = handle_generic_error(error, "performing operation")
        
        assert http_error.status_code == 500
        assert "performing operation" in http_error.detail.lower()
    
    def test_user_friendly_error(self):
        """Test UserFriendlyError exception."""
        error = UserFriendlyError(
            "This is a user-friendly message",
            details="Technical details here",
            status_code=400
        )
        
        assert error.message == "This is a user-friendly message"
        assert error.details == "Technical details here"
        assert error.status_code == 400


class TestErrorResponseCreation:
    """Test cases for error response creation."""
    
    def test_create_basic_error_response(self):
        """Test creating basic error response."""
        response = create_error_response("Something went wrong")
        
        assert response['error'] is True
        assert response['message'] == "Something went wrong"
        assert 'details' not in response
        assert 'error_code' not in response
        assert 'suggestions' not in response
    
    def test_create_detailed_error_response(self):
        """Test creating detailed error response."""
        response = create_error_response(
            message="Operation failed",
            details="Connection timeout after 30 seconds",
            error_code="TIMEOUT_ERROR",
            suggestions=["Check your network", "Try again later"]
        )
        
        assert response['error'] is True
        assert response['message'] == "Operation failed"
        assert response['details'] == "Connection timeout after 30 seconds"
        assert response['error_code'] == "TIMEOUT_ERROR"
        assert len(response['suggestions']) == 2
    
    def test_get_predefined_error_message(self):
        """Test getting predefined error messages."""
        error = get_error_message('credentials_expired')
        
        assert 'message' in error
        assert 'suggestions' in error
        assert "expired" in error['message'].lower()
        assert len(error['suggestions']) > 0
    
    def test_get_unknown_error_message(self):
        """Test getting unknown error message returns default."""
        error = get_error_message('nonexistent_error')
        
        assert 'message' in error
        assert 'suggestions' in error
        assert "unexpected" in error['message'].lower()
    
    def test_all_predefined_errors_have_suggestions(self):
        """Test that all predefined errors have suggestions."""
        from utils.error_handler import ERROR_MESSAGES
        
        for key, error_info in ERROR_MESSAGES.items():
            assert 'message' in error_info
            assert 'suggestions' in error_info
            assert len(error_info['suggestions']) > 0
