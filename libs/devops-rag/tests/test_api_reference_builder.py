"""Tests for API reference builder."""

import pytest

from devops_rag.api_reference_builder import APIReferenceBuilder


@pytest.fixture
def builder():
    """Create API reference builder instance."""
    return APIReferenceBuilder(cluster_version="v1.28.5")


def test_extract_major_minor_version(builder):
    """Test version extraction."""
    assert builder._extract_major_minor_version("v1.28.5") == "v1.28"
    assert builder._extract_major_minor_version("v1.29.0") == "v1.29"
    assert builder._extract_major_minor_version("1.28.5") == "v1.28"
    assert builder._extract_major_minor_version("v1.30") == "v1.30"


def test_get_api_overview_url(builder):
    """Test API overview URL."""
    url = builder.get_api_overview_url()
    assert url == "https://kubernetes.io/docs/concepts/overview/kubernetes-api/"


def test_get_api_reference_url(builder):
    """Test API reference URL with version."""
    url = builder.get_api_reference_url()
    assert "v1.28" in url
    assert "kubernetes-api" in url


def test_get_api_reference_url_different_versions(builder):
    """Test API reference URL for different versions."""
    builder_v29 = APIReferenceBuilder(cluster_version="v1.29.2")
    url = builder_v29.get_api_reference_url()
    assert "v1.29" in url

    builder_v30 = APIReferenceBuilder(cluster_version="v1.30.0")
    url = builder_v30.get_api_reference_url()
    assert "v1.30" in url


def test_get_resource_url_pod(builder):
    """Test resource URL for Pod."""
    url = builder.get_resource_url("Pod")
    assert url is not None
    assert "pod-v1-core" in url


def test_get_resource_url_deployment(builder):
    """Test resource URL for Deployment."""
    url = builder.get_resource_url("Deployment")
    assert url is not None
    assert "deployment-v1-apps" in url


def test_get_resource_url_service(builder):
    """Test resource URL for Service."""
    url = builder.get_resource_url("Service")
    assert url is not None
    assert "service-v1-core" in url


def test_get_resource_url_unknown(builder):
    """Test resource URL for unknown resource."""
    url = builder.get_resource_url("UnknownResource")
    assert url is None


def test_format_api_call_example_pod_get(builder):
    """Test API call example for Pod get."""
    example = builder.format_api_call_example("Pod", "get")
    assert "read_namespaced_pod" in example
    assert "CoreV1Api" in example


def test_format_api_call_example_pod_list(builder):
    """Test API call example for Pod list."""
    example = builder.format_api_call_example("Pod", "list")
    assert "list_namespaced_pod" in example
    assert "CoreV1Api" in example


def test_format_api_call_example_deployment_patch(builder):
    """Test API call example for Deployment patch."""
    example = builder.format_api_call_example("Deployment", "patch")
    assert "patch_namespaced_deployment" in example
    assert "AppsV1Api" in example


def test_format_api_call_example_default(builder):
    """Test API call example default."""
    example = builder.format_api_call_example("UnknownResource", "get")
    assert "config.load_incluster_config" in example


def test_get_documentation_links(builder):
    """Test getting all documentation links."""
    links = builder.get_documentation_links()
    assert "api_overview" in links
    assert "api_reference" in links
    assert "cluster_version" in links
    assert links["cluster_version"] == "v1.28"
