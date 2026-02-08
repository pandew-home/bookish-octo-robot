"""Tests for query router."""

import pytest

from devops_prompts.query_router import QueryRouter


@pytest.fixture
def router():
    """Create query router instance."""
    return QueryRouter()


def test_detect_query_type_troubleshooting(router):
    """Test troubleshooting query detection."""
    assert router.detect_query_type("Pod is failing") == "troubleshooting"
    assert router.detect_query_type("Help me debug this error") == "troubleshooting"
    assert router.detect_query_type("Deployment crashed") == "troubleshooting"


def test_detect_query_type_analysis(router):
    """Test analysis query detection."""
    assert router.detect_query_type("Analyze cluster performance") == "analysis"
    assert router.detect_query_type("Check resource usage") == "analysis"
    assert router.detect_query_type("Review cluster health") == "analysis"


def test_detect_query_type_deployment(router):
    """Test deployment query detection."""
    assert router.detect_query_type("Deploy with Helm") == "deployment"
    assert router.detect_query_type("Deployment configuration issue") == "deployment"
    assert router.detect_query_type("Rollout strategy") == "deployment"


def test_detect_query_type_gitops(router):
    """Test GitOps query detection."""
    assert router.detect_query_type("ArgoCD sync issue") == "gitops"
    assert router.detect_query_type("Flux reconciliation") == "gitops"
    assert router.detect_query_type("GitOps workflow") == "gitops"


def test_detect_query_type_security(router):
    """Test security query detection."""
    assert router.detect_query_type("RBAC permission issue") == "security"
    assert router.detect_query_type("Pod security policy") == "security"
    assert router.detect_query_type("TLS certificate problem") == "security"


def test_detect_query_type_networking(router):
    """Test networking query detection."""
    assert router.detect_query_type("DNS resolution issue") == "networking"
    assert router.detect_query_type("Service mesh connectivity") == "networking"
    assert router.detect_query_type("Network policy problem") == "networking"


def test_detect_query_type_general(router):
    """Test general query detection."""
    assert router.detect_query_type("Tell me about Kubernetes") == "general"


def test_detect_time_range_last_minutes(router):
    """Test time range detection for 'last X minutes'."""
    time_range = router.detect_time_range("What happened in the last 30 minutes?")
    assert time_range is not None
    start, end = time_range
    assert (end - start).total_seconds() == 30 * 60


def test_detect_time_range_last_hours(router):
    """Test time range detection for 'last X hours'."""
    time_range = router.detect_time_range("Show me events from the last 2 hours")
    assert time_range is not None
    start, end = time_range
    assert (end - start).total_seconds() == 2 * 3600


def test_detect_time_range_last_days(router):
    """Test time range detection for 'last X days'."""
    time_range = router.detect_time_range("Analyze the last 7 days")
    assert time_range is not None
    start, end = time_range
    assert (end - start).total_seconds() == 7 * 86400


def test_detect_time_range_past(router):
    """Test time range detection for 'past X'."""
    time_range = router.detect_time_range("Events in the past 1 hour")
    assert time_range is not None
    start, end = time_range
    assert (end - start).total_seconds() == 3600


def test_detect_time_range_since(router):
    """Test time range detection for 'since X ago'."""
    time_range = router.detect_time_range("Since 5 minutes ago")
    assert time_range is not None
    start, end = time_range
    assert (end - start).total_seconds() == 5 * 60


def test_detect_time_range_none(router):
    """Test time range detection when no time range specified."""
    time_range = router.detect_time_range("What's wrong with my pod?")
    assert time_range is None
