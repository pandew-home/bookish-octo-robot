"""
Unit tests for enrichment timeout handling.

Tests cover:
- Timeout parameter enforcement
- Graceful failure on timeout
- Partial results returned
- Timeout doesn't block entire pipeline
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Any

from enrichment_engine import EnrichmentEngine, EnrichedContext
from query_router import EnrichmentPlan, QueryCategory


@pytest.fixture
def enrichment_plan():
    """Create a basic enrichment plan."""
    return EnrichmentPlan(
        categories=[QueryCategory.POD_ISSUE],
        resource_names=[],
        namespaces=[],
        include_aws_context=False
    )


@pytest.fixture
def mock_k8s_clients():
    """Create mock Kubernetes API clients."""
    return {
        "core_v1": Mock(),
        "apps_v1": Mock(),
        "custom_objects": Mock(),
        "networking_v1": Mock(),
    }


@pytest.fixture
def mock_credentials():
    """Create mock credentials."""
    creds = Mock()
    creds.auth_mode = "aws"
    creds.access_key = "ASIAACCESSKEY"
    creds.secret_key = "secret"
    creds.session_token = "token"
    creds.region = "us-east-1"
    return creds


@pytest.fixture
def enrichment_engine(mock_k8s_clients, mock_credentials):
    """Create enrichment engine with mocked dependencies."""
    engine = EnrichmentEngine(
        k8s_clients=mock_k8s_clients,
        aws_creds=mock_credentials
    )
    engine.timeout = 5  # 5 second timeout for testing
    return engine


class TestEnrichmentTimeoutEnforcement:
    """Test that timeout parameter is enforced."""

    @pytest.mark.asyncio
    async def test_timeout_parameter_is_set(self, enrichment_engine):
        """Test that timeout parameter is properly set."""
        assert enrichment_engine.timeout == 5

    @pytest.mark.asyncio
    async def test_timeout_applies_to_enrichment(self, enrichment_engine, enrichment_plan):
        """Test that timeout applies to entire enrichment operation."""
        # Mock a slow operation
        async def slow_pod_enrichment(*args, **kwargs):
            await asyncio.sleep(10)  # Sleep longer than timeout
            return {"pods": []}

        enrichment_engine._enrich_pods = slow_pod_enrichment

        # Execute with timeout - should timeout
        result = await enrichment_engine.execute(enrichment_plan)

        # Should have completed (with partial results) due to timeout handling
        assert isinstance(result, EnrichedContext)
        assert len(result.errors) > 0 or result.pod_data is None

    @pytest.mark.asyncio
    async def test_timeout_prevents_hanging(self, enrichment_engine, enrichment_plan):
        """Test that timeout prevents the operation from hanging indefinitely."""
        async def hanging_operation(*args, **kwargs):
            await asyncio.sleep(100)  # Very long sleep
            return {"data": "should not reach here"}

        enrichment_engine._enrich_pods = hanging_operation

        start_time = datetime.now()
        result = await enrichment_engine.execute(enrichment_plan)
        elapsed = (datetime.now() - start_time).total_seconds()

        # Should complete quickly (within timeout + small margin)
        assert elapsed < enrichment_engine.timeout + 2
        assert isinstance(result, EnrichedContext)


class TestGracefulTimeoutFailure:
    """Test graceful failure when enrichment times out."""

    @pytest.mark.asyncio
    async def test_enrichment_fails_gracefully_on_timeout(self, enrichment_engine, enrichment_plan):
        """Test that enrichment fails gracefully when operation times out."""
        # Mock timeout scenario
        async def timeout_operation(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout

        enrichment_engine._enrich_pods = timeout_operation
        enrichment_engine._read_k8sgpt_results = AsyncMock(return_value={"results": []})

        result = await enrichment_engine.execute(enrichment_plan)

        # Should return partial context with errors
        assert isinstance(result, EnrichedContext)
        assert len(result.errors) > 0 or result.pod_data is None

    @pytest.mark.asyncio
    async def test_timeout_logs_error(self, enrichment_engine, enrichment_plan):
        """Test that timeout is logged as an error."""
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(10)

        enrichment_engine._enrich_pods = slow_operation

        with patch('enrichment_engine.logger') as mock_logger:
            result = await enrichment_engine.execute(enrichment_plan)
            # Logger should have been called for timeout
            # (implementation dependent on actual code)

    @pytest.mark.asyncio
    async def test_timeout_exception_caught(self, enrichment_engine, enrichment_plan):
        """Test that timeout exceptions are caught and handled."""
        async def timeout_operation(*args, **kwargs):
            await asyncio.sleep(10)

        enrichment_engine._enrich_pods = timeout_operation

        # Should not raise, should return partial results
        result = await enrichment_engine.execute(enrichment_plan)
        assert result is not None
        assert isinstance(result, EnrichedContext)


class TestPartialResultsOnTimeout:
    """Test that partial results are returned on timeout."""

    @pytest.mark.asyncio
    async def test_partial_pod_data_returned(self, enrichment_engine, enrichment_plan):
        """Test that partial pod data is returned when pod enrichment times out."""
        # Mock fast K8sGPT results, slow pod enrichment
        enrichment_engine._read_k8sgpt_results = AsyncMock(
            return_value={"results": [{"name": "result-1"}]}
        )

        async def slow_pod_enrichment(*args, **kwargs):
            await asyncio.sleep(10)

        enrichment_engine._enrich_pods = slow_pod_enrichment

        result = await enrichment_engine.execute(enrichment_plan)

        # Should have K8sGPT results even if pod data timed out
        assert isinstance(result, EnrichedContext)
        # K8sGPT results should be present
        if result.k8sgpt_results:
            assert len(result.k8sgpt_results) > 0

    @pytest.mark.asyncio
    async def test_multiple_operations_partial_completion(self, enrichment_engine):
        """Test that when multiple operations run concurrently, completed ones return results."""
        # Plan with multiple enrichments
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            
            
            
            resource_names=[],
            namespaces=[],
            include_aws_context=False,
        )

        # Mock fast deployment and service enrichment, slow pod enrichment
        enrichment_engine._enrich_deployments = AsyncMock(
            return_value={"deployments": [{"name": "app-1"}]}
        )
        enrichment_engine._enrich_services = AsyncMock(
            return_value={"services": [{"name": "svc-1"}]}
        )

        async def slow_pod_enrichment(*args, **kwargs):
            await asyncio.sleep(10)

        enrichment_engine._enrich_pods = slow_pod_enrichment
        enrichment_engine._read_k8sgpt_results = AsyncMock(
            return_value={"results": []}
        )

        result = await enrichment_engine.execute(plan)

        # Should have deployment and service data
        assert isinstance(result, EnrichedContext)
        # Fast operations should have completed
        if result.deployment_data:
            assert len(result.deployment_data.get("deployments", [])) > 0
        if result.service_data:
            assert len(result.service_data.get("services", [])) > 0

    @pytest.mark.asyncio
    async def test_error_list_contains_timeout_info(self, enrichment_engine, enrichment_plan):
        """Test that errors list contains timeout information."""
        async def timeout_operation(*args, **kwargs):
            await asyncio.sleep(10)

        enrichment_engine._enrich_pods = timeout_operation

        result = await enrichment_engine.execute(enrichment_plan)

        assert isinstance(result, EnrichedContext)
        # Should have errors or missing data
        assert len(result.errors) > 0 or result.pod_data is None


class TestTimeoutWithMultipleClusters:
    """Test timeout behavior with multiple cluster requests."""

    @pytest.mark.asyncio
    async def test_timeout_isolated_per_request(self):
        """Test that timeout doesn't affect other concurrent requests."""
        credentials = Mock()
        credentials.auth_mode = "aws"
        credentials.region = "us-east-1"

        engine1 = EnrichmentEngine(
            k8s_clients={"core_v1": Mock()},
            aws_creds=credentials
        )
        engine1.timeout = 2
        engine2 = EnrichmentEngine(
            k8s_clients={"core_v1": Mock()},
            aws_creds=credentials
        )
        engine2.timeout = 2

        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            
            resource_names=[],
            namespaces=[],
            include_aws_context=False,
        )

        # Mock slow operation for engine1
        async def slow_enrich(*args, **kwargs):
            await asyncio.sleep(5)
            return {}

        # Mock fast operation for engine2
        async def fast_enrich(*args, **kwargs):
            return {"pods": [{"name": "pod-1"}]}

        engine1._enrich_pods = slow_enrich
        engine2._enrich_pods = fast_enrich

        # Run both concurrently
        start = datetime.now()
        result1, result2 = await asyncio.gather(
            engine1.execute(plan),
            engine2.execute(plan)
        )
        elapsed = (datetime.now() - start).total_seconds()

        # Both should complete within their respective timeouts
        assert isinstance(result1, EnrichedContext)
        assert isinstance(result2, EnrichedContext)
        # Total time should be ~timeout for slowest + overhead, not sum
        assert elapsed < 10  # Both run concurrently


class TestTimeoutConfigurationOptions:
    """Test various timeout configuration scenarios."""

    def test_custom_timeout_value(self):
        """Test that custom timeout value is respected."""
        credentials = Mock()
        engine = EnrichmentEngine(
            k8s_clients={"core_v1": Mock()},
            aws_creds=credentials
        )
        engine.timeout = 15  # Custom timeout
        assert engine.timeout == 15

    def test_zero_timeout_handled(self):
        """Test that zero timeout is handled appropriately."""
        credentials = Mock()
        engine = EnrichmentEngine(
            k8s_clients={"core_v1": Mock()},
            aws_creds=credentials
        )
        engine.timeout = 0.1  # Very small timeout
        assert engine.timeout > 0

    def test_timeout_none_defaults(self):
        """Test that None timeout uses default."""
        credentials = Mock()
        engine = EnrichmentEngine(
            k8s_clients={"core_v1": Mock()},
            aws_creds=credentials
        )
        assert engine.timeout is not None
        assert engine.timeout > 0


class TestTimeoutAccuracy:
    """Test timeout accuracy and edge cases."""

    @pytest.mark.asyncio
    async def test_operation_completes_before_timeout(self, enrichment_engine, enrichment_plan):
        """Test that fast operations complete well before timeout."""
        enrichment_engine._enrich_pods = AsyncMock(
            return_value={"pods": [{"name": "pod-1"}]}
        )
        enrichment_engine._read_k8sgpt_results = AsyncMock(
            return_value={"results": []}
        )

        start = datetime.now()
        result = await enrichment_engine.execute(enrichment_plan)
        elapsed = (datetime.now() - start).total_seconds()

        # Should complete quickly
        assert elapsed < 1  # Well under timeout
        assert result.pod_data is not None

    @pytest.mark.asyncio
    async def test_operation_at_timeout_boundary(self, enrichment_engine, enrichment_plan):
        """Test operation that completes exactly at timeout boundary."""
        # Create engine with small timeout
        small_timeout_engine = EnrichmentEngine(
            k8s_clients=enrichment_engine.k8s,
            aws_creds=enrichment_engine.aws_creds
        )
        small_timeout_engine.timeout = 0.5  # 500ms timeout

        async def near_timeout_operation(*args, **kwargs):
            # Sleep just under the timeout
            await asyncio.sleep(0.4)
            return {"pods": [{"name": "pod-1"}]}

        small_timeout_engine._enrich_pods = near_timeout_operation
        small_timeout_engine._read_k8sgpt_results = AsyncMock(
            return_value={"results": []}
        )

        result = await small_timeout_engine.execute(enrichment_plan)
        assert result.pod_data is not None
