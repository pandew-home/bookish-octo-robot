"""Tests for domain validator."""

import pytest

from devops_prompts.domain_validator import DomainValidator


@pytest.fixture
def validator():
    """Create domain validator instance."""
    return DomainValidator()


def test_is_devops_query_kubernetes(validator):
    """Test DevOps query detection for Kubernetes."""
    assert validator.is_devops_query("My pod is failing")
    assert validator.is_devops_query("How do I deploy with Helm?")
    assert validator.is_devops_query("What's wrong with my deployment?")


def test_is_devops_query_aws(validator):
    """Test DevOps query detection for AWS."""
    assert validator.is_devops_query("EKS cluster issues")
    assert validator.is_devops_query("How do I configure IAM roles?")
    assert validator.is_devops_query("VPC networking problem")


def test_is_devops_query_gitops(validator):
    """Test DevOps query detection for GitOps."""
    assert validator.is_devops_query("ArgoCD app out of sync")
    assert validator.is_devops_query("Flux reconciliation failed")
    assert validator.is_devops_query("GitOps workflow")


def test_is_devops_query_non_devops(validator):
    """Test non-DevOps query detection."""
    assert not validator.is_devops_query("What is the best pizza?")
    assert not validator.is_devops_query("How do I bake bread?")
    assert not validator.is_devops_query("Tell me a funny joke")


def test_validate_query_valid(validator):
    """Test query validation for valid queries."""
    is_valid, message = validator.validate_query("Pod failing in production")
    assert is_valid
    assert message == ""


def test_validate_query_invalid(validator):
    """Test query validation for invalid queries."""
    is_valid, message = validator.validate_query("What is the best pizza?")
    assert not is_valid
    assert "DevOps" in message
    assert "Kubernetes" in message


def test_rejection_message(validator):
    """Test rejection message content."""
    message = validator.get_rejection_message()
    assert "DevOps" in message
    assert "Kubernetes" in message
    assert "AWS" in message
    assert "Helm" in message
    assert "ArgoCD" in message
