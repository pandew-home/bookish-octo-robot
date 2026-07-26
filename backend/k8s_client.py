"""
In-cluster Kubernetes client singleton.

The pod ServiceAccount is intentionally limited to reading K8sGPT Result CRDs
(`core.k8sgpt.ai/results`). Live diagnostics (pods, events, generic API) must
use per-session user clients from `api.clusters.get_k8s_clients_for_session`.
"""
import logging
from typing import Any, Dict

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

logger = logging.getLogger(__name__)


class InClusterK8sClient:
    """Singleton in-cluster Kubernetes client (SA = K8sGPT Results only)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config (SA / K8sGPT)")
            except ConfigException:
                logger.warning(
                    "In-cluster config not available, falling back to kubeconfig"
                )
                try:
                    config.load_kubeconfig()
                    logger.info("Loaded kubeconfig (local fallback for K8sGPT)")
                except ConfigException:
                    logger.error("No Kubernetes config available")
                    raise RuntimeError(
                        "Cannot initialize K8s client: "
                        "no in-cluster config or kubeconfig found"
                    )
            cls._instance = super().__new__(cls)
            # Only CustomObjectsApi is needed for Result CRDs; keep a thin set
            # for version probes used in diagnostics metadata.
            cls._instance.custom_objects = client.CustomObjectsApi()
            cls._instance.version_api = client.VersionApi()
        return cls._instance

    def get_clients(self) -> Dict[str, Any]:
        """Return clients appropriate for SA scope (K8sGPT Results).

        Does not expose core_v1/apps_v1 so agent tools cannot accidentally
        use the pod SA for live cluster inspection.
        """
        return {
            "custom_objects": self.custom_objects,
        }

    def get_cluster_version(self) -> str:
        """Get host cluster version string (e.g. 'v1.34.2')."""
        try:
            version = self.version_api.get_code()
            return f"v{version.major}.{version.minor}"
        except Exception as e:
            logger.warning(f"Failed to get cluster version: {e}")
            return "unknown"


def get_k8s_client() -> InClusterK8sClient:
    """Get the singleton in-cluster K8s client (K8sGPT SA path)."""
    return InClusterK8sClient()
