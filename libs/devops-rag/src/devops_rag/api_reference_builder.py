"""Kubernetes API reference builder for documentation links."""

import re
from typing import Dict, Optional


class APIReferenceBuilder:
    """Build Kubernetes API documentation links and examples."""

    # Base URLs
    API_OVERVIEW_URL = "https://kubernetes.io/docs/concepts/overview/kubernetes-api/"
    API_REFERENCE_BASE_URL = "https://kubernetes.io/docs/reference/generated/kubernetes-api"

    # Resource documentation paths
    RESOURCE_DOCS = {
        "pod": "pod-v1-core",
        "pods": "pod-v1-core",
        "deployment": "deployment-v1-apps",
        "deployments": "deployment-v1-apps",
        "service": "service-v1-core",
        "services": "service-v1-core",
        "configmap": "configmap-v1-core",
        "configmaps": "configmap-v1-core",
        "secret": "secret-v1-core",
        "secrets": "secret-v1-core",
        "persistentvolume": "persistentvolume-v1-core",
        "persistentvolumeclaim": "persistentvolumeclaim-v1-core",
        "statefulset": "statefulset-v1-apps",
        "statefulsets": "statefulset-v1-apps",
        "daemonset": "daemonset-v1-apps",
        "daemonsets": "daemonset-v1-apps",
        "job": "job-v1-batch",
        "jobs": "job-v1-batch",
        "cronjob": "cronjob-v1-batch",
        "cronjobs": "cronjob-v1-batch",
        "namespace": "namespace-v1-core",
        "namespaces": "namespace-v1-core",
        "node": "node-v1-core",
        "nodes": "node-v1-core",
        "ingress": "ingress-v1-networking-k8s-io",
        "ingresses": "ingress-v1-networking-k8s-io",
        "networkpolicy": "networkpolicy-v1-networking-k8s-io",
        "networkpolicies": "networkpolicy-v1-networking-k8s-io",
        "storageclass": "storageclass-v1-storage-k8s-io",
        "storageclasses": "storageclass-v1-storage-k8s-io",
        "clusterrole": "clusterrole-v1-rbac-authorization-k8s-io",
        "clusterroles": "clusterrole-v1-rbac-authorization-k8s-io",
        "clusterrolebinding": "clusterrolebinding-v1-rbac-authorization-k8s-io",
        "clusterrolebindings": "clusterrolebinding-v1-rbac-authorization-k8s-io",
        "role": "role-v1-rbac-authorization-k8s-io",
        "roles": "role-v1-rbac-authorization-k8s-io",
        "rolebinding": "rolebinding-v1-rbac-authorization-k8s-io",
        "rolebindings": "rolebinding-v1-rbac-authorization-k8s-io",
        "serviceaccount": "serviceaccount-v1-core",
        "serviceaccounts": "serviceaccount-v1-core",
    }

    def __init__(self, cluster_version: str = "v1.34"):
        """Initialize API reference builder.

        Args:
            cluster_version: Kubernetes cluster version (e.g., "v1.34.5")
        """
        self.cluster_version = cluster_version
        self.major_minor_version = self._extract_major_minor_version(cluster_version)

    def _extract_major_minor_version(self, version: str) -> str:
        """Extract major.minor version from full version string.

        Args:
            version: Full version string (e.g., "v1.34.5")

        Returns:
            Major.minor version (e.g., "v1.34")
        """
        # Match pattern like v1.34.5 or 1.34.5
        match = re.match(r"v?(\d+\.\d+)", version)
        if match:
            return f"v{match.group(1)}"
        return "v1.34"  # Default fallback

    def get_api_overview_url(self) -> str:
        """Get Kubernetes API overview URL.

        Returns:
            API overview URL
        """
        return self.API_OVERVIEW_URL

    def get_api_reference_url(self) -> str:
        """Get Kubernetes API reference URL with correct cluster version.

        Returns:
            API reference URL with version (e.g., https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/)
        """
        return f"{self.API_REFERENCE_BASE_URL}/{self.major_minor_version}/"

    def get_resource_url(self, resource_kind: str) -> Optional[str]:
        """Get documentation URL for a specific resource kind.

        Args:
            resource_kind: Kubernetes resource kind (e.g., "Pod", "Deployment")

        Returns:
            Resource documentation URL or None if not found
        """
        resource_key = resource_kind.lower()
        if resource_key not in self.RESOURCE_DOCS:
            return None

        resource_doc = self.RESOURCE_DOCS[resource_key]
        return f"{self.get_api_reference_url()}#{resource_doc}"

    def format_api_call_example(self, resource_kind: str, operation: str = "get") -> str:
        """Format a Python API call example.

        Args:
            resource_kind: Kubernetes resource kind (e.g., "Pod")
            operation: Operation type (e.g., "get", "list", "create", "delete")

        Returns:
            Python API call example string
        """
        resource_lower = resource_kind.lower()

        examples = {
            "pod": {
                "get": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "pod = v1.read_namespaced_pod('pod-name', 'namespace')"
                ),
                "list": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "pods = v1.list_namespaced_pod('namespace')"
                ),
                "delete": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "v1.delete_namespaced_pod('pod-name', 'namespace')"
                ),
            },
            "deployment": {
                "get": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "apps_v1 = client.AppsV1Api()\n"
                    "deployment = apps_v1.read_namespaced_deployment('deployment-name', 'namespace')"
                ),
                "list": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "apps_v1 = client.AppsV1Api()\n"
                    "deployments = apps_v1.list_namespaced_deployment('namespace')"
                ),
                "patch": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "apps_v1 = client.AppsV1Api()\n"
                    "body = {'spec': {'replicas': 3}}\n"
                    "apps_v1.patch_namespaced_deployment('deployment-name', 'namespace', body)"
                ),
            },
            "service": {
                "get": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "service = v1.read_namespaced_service('service-name', 'namespace')"
                ),
                "list": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "services = v1.list_namespaced_service('namespace')"
                ),
            },
            "configmap": {
                "get": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "configmap = v1.read_namespaced_config_map('configmap-name', 'namespace')"
                ),
                "list": (
                    "from kubernetes import client, config\n"
                    "config.load_incluster_config()\n"
                    "v1 = client.CoreV1Api()\n"
                    "configmaps = v1.list_namespaced_config_map('namespace')"
                ),
            },
        }

        # Get example for resource and operation
        if resource_lower in examples and operation in examples[resource_lower]:
            return examples[resource_lower][operation]

        # Default generic example
        return (
            "from kubernetes import client, config\n"
            "config.load_incluster_config()\n"
            "# Use appropriate API client for your resource type"
        )

    def get_documentation_links(self) -> Dict[str, str]:
        """Get all documentation links.

        Returns:
            Dictionary with documentation links
        """
        return {
            "api_overview": self.get_api_overview_url(),
            "api_reference": self.get_api_reference_url(),
            "cluster_version": self.major_minor_version,
        }
