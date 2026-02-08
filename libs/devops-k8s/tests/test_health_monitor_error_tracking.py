"""Test HealthMonitor error tracking and exponential backoff."""

import pytest
from unittest.mock import Mock, patch
from kubernetes.client.rest import ApiException

from devops_k8s.health_monitor import HealthMonitor


@pytest.fixture
def health_monitor():
    """Create a HealthMonitor instance for testing."""
    with patch("devops_k8s.health_monitor.client"):
        monitor = HealthMonitor(max_retries=3)
        return monitor


def test_exponential_backoff_success_on_retry(health_monitor):
    """Test that exponential backoff succeeds on retry."""
    # Mock API call that fails once then succeeds
    mock_api_call = Mock()
    mock_api_call.side_effect = [
        ApiException(status=500, reason="Internal Server Error"),
        "success"
    ]
    
    with patch("time.sleep") as mock_sleep:
        result = health_monitor._call_k8s_api_with_backoff(
            mock_api_call, "test_operation"
        )
    
    # Should succeed on second attempt
    assert result == "success"
    assert mock_api_call.call_count == 2
    
    # Should have slept once with 1 second delay
    mock_sleep.assert_called_once_with(1.0)
    
    # Should have tracked one warning error
    errors = health_monitor.get_errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "k8s_api_call"
    assert errors[0]["severity"] == "warning"
    assert "test_operation attempt 1 failed" in errors[0]["message"]


def test_exponential_backoff_all_retries_fail(health_monitor):
    """Test that exponential backoff fails after all retries."""
    # Mock API call that always fails
    mock_api_call = Mock()
    mock_api_call.side_effect = ApiException(status=500, reason="Internal Server Error")
    
    with patch("time.sleep") as mock_sleep:
        result = health_monitor._call_k8s_api_with_backoff(
            mock_api_call, "test_operation"
        )
    
    # Should return None after all retries
    assert result is None
    assert mock_api_call.call_count == 3  # max_retries
    
    # Should have slept with exponential backoff: 1s, 2s
    expected_calls = [pytest.approx(1.0), pytest.approx(2.0)]
    actual_calls = [call[0][0] for call in mock_sleep.call_args_list]
    assert actual_calls == expected_calls
    
    # Should have tracked warning errors and final error
    errors = health_monitor.get_errors()
    assert len(errors) == 3  # 2 warnings + 1 final error
    
    # Check warning errors
    assert errors[0]["severity"] == "warning"
    assert "attempt 1 failed" in errors[0]["message"]
    assert errors[1]["severity"] == "warning"
    assert "attempt 2 failed" in errors[1]["message"]
    
    # Check final error
    assert errors[2]["severity"] == "error"
    assert "failed after 3 attempts" in errors[2]["message"]


def test_exponential_backoff_max_delay_cap(health_monitor):
    """Test that exponential backoff respects maximum delay cap."""
    # Create monitor with more retries to test delay cap
    with patch("devops_k8s.health_monitor.client"):
        monitor = HealthMonitor(max_retries=6)
    
    # Mock API call that always fails
    mock_api_call = Mock()
    mock_api_call.side_effect = ApiException(status=500, reason="Internal Server Error")
    
    with patch("time.sleep") as mock_sleep:
        result = monitor._call_k8s_api_with_backoff(
            mock_api_call, "test_operation"
        )
    
    # Should return None after all retries
    assert result is None
    
    # Check that delays follow exponential backoff with 32s cap
    # Expected: 1, 2, 4, 8, 16, 32 (capped at 32)
    expected_delays = [1.0, 2.0, 4.0, 8.0, 16.0]
    actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
    
    for i, (expected, actual) in enumerate(zip(expected_delays, actual_delays)):
        assert actual == pytest.approx(expected), f"Delay {i+1} should be {expected}s, got {actual}s"


def test_collect_metrics_with_api_failures(health_monitor):
    """Test that collect_metrics handles API failures gracefully."""
    # Mock some API calls to fail
    health_monitor.k8s_client.list_pod_for_all_namespaces = Mock()
    health_monitor.k8s_client.list_pod_for_all_namespaces.side_effect = ApiException(
        status=500, reason="Internal Server Error"
    )
    
    health_monitor.k8s_client.list_node = Mock()
    health_monitor.k8s_client.list_node.return_value = Mock(items=[])
    
    health_monitor.k8s_client.list_event_for_all_namespaces = Mock()
    health_monitor.k8s_client.list_event_for_all_namespaces.return_value = Mock(items=[])
    
    health_monitor.apps_client.list_deployment_for_all_namespaces = Mock()
    health_monitor.apps_client.list_deployment_for_all_namespaces.return_value = Mock(items=[])
    
    health_monitor.apps_client.list_stateful_set_for_all_namespaces = Mock()
    health_monitor.apps_client.list_stateful_set_for_all_namespaces.return_value = Mock(items=[])
    
    health_monitor.apps_client.list_daemon_set_for_all_namespaces = Mock()
    health_monitor.apps_client.list_daemon_set_for_all_namespaces.return_value = Mock(items=[])
    
    health_monitor.k8s_client.list_persistent_volume_claim_for_all_namespaces = Mock()
    health_monitor.k8s_client.list_persistent_volume_claim_for_all_namespaces.return_value = Mock(items=[])
    
    health_monitor.networking_client.list_ingress_for_all_namespaces = Mock()
    health_monitor.networking_client.list_ingress_for_all_namespaces.return_value = Mock(items=[])
    
    with patch("time.sleep"):
        metrics = health_monitor.collect_metrics()
    
    # Should return metrics even with some API failures
    assert metrics is not None
    assert metrics.pod_failures == 0  # Failed to get pods, so 0
    
    # Should have tracked errors for failed API calls
    errors = health_monitor.get_errors()
    assert len(errors) > 0
    
    # Should have errors related to list_pods failure
    pod_errors = [e for e in errors if "list_pods" in e["message"]]
    assert len(pod_errors) > 0


def test_error_tracking_methods(health_monitor):
    """Test error tracking methods."""
    # Track some errors
    health_monitor._track_error("test_type", "Test message 1", "warning")
    health_monitor._track_error("test_type", "Test message 2", "error")
    
    # Get errors
    errors = health_monitor.get_errors()
    
    assert len(errors) == 2
    
    # Check first error
    assert errors[0]["type"] == "test_type"
    assert errors[0]["message"] == "Test message 1"
    assert errors[0]["severity"] == "warning"
    assert "timestamp" in errors[0]
    
    # Check second error
    assert errors[1]["type"] == "test_type"
    assert errors[1]["message"] == "Test message 2"
    assert errors[1]["severity"] == "error"
    assert "timestamp" in errors[1]


def test_error_reset_on_collect_metrics(health_monitor):
    """Test that errors are reset on each collect_metrics call."""
    # Track an error
    health_monitor._track_error("old_error", "Old error message", "warning")
    assert len(health_monitor.get_errors()) == 1
    
    # Mock successful API calls
    health_monitor.k8s_client.list_pod_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.k8s_client.list_node = Mock(return_value=Mock(items=[]))
    health_monitor.k8s_client.list_event_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.apps_client.list_deployment_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.apps_client.list_stateful_set_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.apps_client.list_daemon_set_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.k8s_client.list_persistent_volume_claim_for_all_namespaces = Mock(return_value=Mock(items=[]))
    health_monitor.networking_client.list_ingress_for_all_namespaces = Mock(return_value=Mock(items=[]))
    
    # Collect metrics (should reset errors)
    _ = health_monitor.collect_metrics()
    
    # Errors should be reset (empty since all API calls succeeded)
    errors = health_monitor.get_errors()
    assert len(errors) == 0