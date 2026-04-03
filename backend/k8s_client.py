"""
In-cluster Kubernetes client singleton.

Uses the pod's ServiceAccount for authentication — no user credentials needed.
"""
import logging
from typing import Dict, Any

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

logger = logging.getLogger(__name__)


class InClusterK8sClient:
    """Singleton in-cluster Kubernetes client."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except ConfigException:
                logger.warning(
                    "In-cluster config not available, falling back to kubeconfig"
                )
                try:
                    config.load_kubeconfig()
                    logger.info("Loaded kubeconfig")
                except ConfigException:
                    logger.error("No Kubernetes config available")
                    raise RuntimeError(
                        "Cannot initialize K8s client: "
                        "no in-cluster config or kubeconfig found"
                    )
            cls._instance = super().__new__(cls)
            cls._instance.core_v1 = client.CoreV1Api()
            cls._instance.apps_v1 = client.AppsV1Api()
            cls._instance.networking_v1 = client.NetworkingV1Api()
            cls._instance.custom_objects = client.CustomObjectsApi()
            cls._instance.version_api = client.VersionApi()
        return cls._instance

    def get_clients(self) -> Dict[str, Any]:
        """Return dict of K8s API clients."""
        return {
            "core_v1": self.core_v1,
            "apps_v1": self.apps_v1,
            "networking_v1": self.networking_v1,
            "custom_objects": self.custom_objects,
        }

    def get_cluster_version(self) -> str:
        """Get cluster version string (e.g. 'v1.34.2')."""
        try:
            version = self.version_api.get_code()
            return f"v{version.major}.{version.minor}"
        except Exception as e:
            logger.warning(f"Failed to get cluster version: {e}")
            return "unknown"


def get_k8s_client() -> InClusterK8sClient:
    """Get the singleton in-cluster K8s client."""
    return InClusterK8sClient()
