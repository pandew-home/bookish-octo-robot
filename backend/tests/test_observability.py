"""
Tests for error handling and observability features.

Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.7
"""
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from kubernetes.client.exceptions import ApiException
from botocore.exceptions import ClientError

from utils.error_handler import (
    log_error,
    log_aws_api_call,
    log_llm_api_call,
    retry_with_exponential_backoff,
    k8s_api_retry
)
from utils.metrics import (
    record_query,
    record_error,
    record_aws_api_call,
    record_k8s_api_call,
    record_llm_api_call,
    get_metrics
)


class TestComprehensiveErrorLogging:
    """Test comprehensive error logging functionality."""
    
    def test_log_error_includes_all_required_fields(self, caplog):
        """Test that log_error includes severity, timestamp, user ID, and stack trace."""
        error = ValueError("Test error")
        
        with caplog.at_level("ERROR"):
            log_error(
                error,
                context="test operation",
                user_id="test-user-123",
                severity="ERROR",
                additional_data={"test_field": "test_value"}
            )
        
        # Check log message
        assert len(caplog.records) == 1
        record = caplog.records[0]
        
        # Verify required fields
        assert "test operation" in record.message
        assert "ValueError" in record.message
        assert "test-user-123" in record.message
        assert record.levelname == "ERROR"
        
        # Verify extra data
        assert hasattr(record, 'timestamp')
        assert hasattr(record, 'error_type')
        assert hasattr(record, 'stack_trace')
        assert record.error_type == "ValueError"
        assert record.user_id == "test-user-123"
    
    def test_log_error_handles_anonymous_user(self, caplog):
        """Test that log_error handles missing user ID."""
        error = RuntimeError("Test error")
        
        with caplog.at_level("ERROR"):
            log_error(error, context="test operation")
        
        record = caplog.records[0]
        assert record.user_id == "anonymous"
        assert "anonymous" in record.message


class TestAWSAPILogging:
    """Test AWS API call logging."""
    
    def test_log_aws_api_call_includes_duration_and_status(self, caplog):
        """Test that AWS API calls are logged with duration and status."""
        with caplog.at_level("INFO"):
            log_aws_api_call(
                operation="ListClusters",
                duration_ms=123.45,
                status="success",
                user_id="test-user",
                additional_data={"region": "us-east-1"}
            )
        
        record = caplog.records[0]
        assert "ListClusters" in record.message
        assert "123.45ms" in record.message
        assert "success" in record.message
        assert "test-user" in record.message
        assert record.operation == "ListClusters"
        assert record.duration_ms == 123.45
        assert record.status == "success"
        assert record.api_type == "aws"


class TestLLMAPILogging:
    """Test LLM API call logging."""
    
    def test_log_llm_api_call_includes_token_counts(self, caplog):
        """Test that LLM API calls are logged with token counts and latency."""
        with caplog.at_level("INFO"):
            log_llm_api_call(
                model="gpt-3.5-turbo",
                duration_ms=2500.0,
                status="success",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                user_id="test-user"
            )
        
        record = caplog.records[0]
        assert "gpt-3.5-turbo" in record.message
        assert "2500.00ms" in record.message
        assert "success" in record.message
        assert "150" in record.message  # total tokens
        assert "100" in record.message  # input tokens
        assert "50" in record.message   # output tokens
        assert record.model == "gpt-3.5-turbo"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.api_type == "llm"


class TestRetryLogic:
    """Test retry logic with exponential backoff."""
    
    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test that retry logic succeeds after transient failures."""
        call_count = 0
        
        @retry_with_exponential_backoff(
            max_retries=3,
            initial_delay=0.01,
            exponential_base=2.0,
            exceptions=(RuntimeError,)
        )
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient error")
            return "success"
        
        result = await flaky_function()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_does_not_retry_on_403(self):
        """Test that retry logic does not retry on RBAC 403 errors."""
        call_count = 0
        
        @retry_with_exponential_backoff(
            max_retries=3,
            initial_delay=0.01,
            exceptions=(ApiException,)
        )
        async def rbac_error_function():
            nonlocal call_count
            call_count += 1
            raise ApiException(status=403, reason="Forbidden")
        
        with pytest.raises(ApiException) as exc_info:
            await rbac_error_function()
        
        assert exc_info.value.status == 403
        assert call_count == 1  # Should not retry
    
    @pytest.mark.asyncio
    async def test_retry_does_not_retry_on_401(self):
        """Test that retry logic does not retry on authentication errors."""
        call_count = 0
        
        @retry_with_exponential_backoff(
            max_retries=3,
            initial_delay=0.01,
            exceptions=(ApiException,)
        )
        async def auth_error_function():
            nonlocal call_count
            call_count += 1
            raise ApiException(status=401, reason="Unauthorized")
        
        with pytest.raises(ApiException) as exc_info:
            await auth_error_function()
        
        assert exc_info.value.status == 401
        assert call_count == 1  # Should not retry
    
    @pytest.mark.asyncio
    async def test_k8s_api_retry_decorator(self):
        """Test k8s_api_retry decorator."""
        call_count = 0
        
        @k8s_api_retry(max_retries=2, initial_delay=0.01)
        async def k8s_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection failed")
            return "success"
        
        result = await k8s_function()
        assert result == "success"
        assert call_count == 2


class TestPrometheusMetrics:
    """Test Prometheus metrics functionality."""
    
    def test_record_query_metric(self):
        """Test recording query metrics."""
        # Should not raise any exceptions
        record_query(status="success", user_id="test-user")
        record_query(status="error", user_id="test-user")
        record_query(status="rate_limited")
    
    def test_record_error_metric(self):
        """Test recording error metrics."""
        record_error(error_type="ValueError", component="enrichment")
        record_error(error_type="ApiException", component="k8s")
    
    def test_record_aws_api_call_metric(self):
        """Test recording AWS API call metrics."""
        record_aws_api_call(
            operation="ListClusters",
            status="success",
            duration_seconds=0.5
        )
        record_aws_api_call(
            operation="DescribeCluster",
            status="error",
            duration_seconds=1.2
        )
    
    def test_record_k8s_api_call_metric(self):
        """Test recording Kubernetes API call metrics."""
        record_k8s_api_call(
            operation="list_pods",
            status="success",
            duration_seconds=0.3
        )
        record_k8s_api_call(
            operation="read_namespaced_pod",
            status="permission_denied",
            duration_seconds=0.1
        )
    
    def test_record_llm_api_call_metric(self):
        """Test recording LLM API call metrics."""
        record_llm_api_call(
            model="gpt-3.5-turbo",
            status="success",
            duration_seconds=2.5,
            input_tokens=100,
            output_tokens=50
        )
        record_llm_api_call(
            model="claude-sonnet",
            status="rate_limited",
            duration_seconds=0.5
        )
    
    def test_get_metrics_returns_prometheus_format(self):
        """Test that get_metrics returns Prometheus format."""
        metrics_data, content_type = get_metrics()
        
        assert isinstance(metrics_data, bytes)
        # Check for prometheus format (version may vary with prometheus_client version)
        assert content_type.startswith("text/plain") and "version=" in content_type
        
        # Decode and check for expected metric names
        metrics_text = metrics_data.decode('utf-8')
        assert "chatbot_queries_total" in metrics_text
        assert "chatbot_errors_total" in metrics_text
        assert "chatbot_aws_api_calls_total" in metrics_text
        assert "chatbot_k8s_api_calls_total" in metrics_text
        assert "chatbot_llm_api_calls_total" in metrics_text


class TestUserFriendlyErrorMessages:
    """Test that error messages are user-friendly without internal details."""
    
    def test_aws_error_does_not_expose_internal_details(self):
        """Test that AWS errors return user-friendly messages."""
        from utils.error_handler import handle_aws_error
        
        error = ClientError(
            {
                'Error': {
                    'Code': 'InvalidClientTokenId',
                    'Message': 'The security token included in the request is invalid.'
                }
            },
            'GetCallerIdentity'
        )
        
        http_exception = handle_aws_error(error, "validating credentials")
        
        # Should not contain internal error message
        assert "security token" not in http_exception.detail.lower()
        # Should contain user-friendly message
        assert "kion" in http_exception.detail.lower()
        assert "credentials" in http_exception.detail.lower()
    
    def test_k8s_error_does_not_expose_internal_details(self):
        """Test that K8s errors return user-friendly messages."""
        from utils.error_handler import handle_k8s_error
        
        error = ApiException(
            status=403,
            reason="Forbidden: User 'system:serviceaccount:default:chatbot' cannot list resource 'pods' in API group '' at the cluster scope"
        )
        
        http_exception = handle_k8s_error(error, "listing pods")
        
        # Should not contain internal error details
        assert "system:serviceaccount" not in http_exception.detail
        # Should contain user-friendly message
        assert "permission" in http_exception.detail.lower()
        assert "listing pods" in http_exception.detail.lower()
