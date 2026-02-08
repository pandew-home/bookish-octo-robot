"""Resource exhaustion detection for Kubernetes clusters."""

import logging
from dataclasses import dataclass
from typing import List, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException

from devops_k8s.client import K8sClient

logger = logging.getLogger(__name__)


@dataclass
class ExhaustionRisk:
    """Resource exhaustion risk for a resource."""

    resource_kind: str
    resource_name: str
    resource_namespace: str
    resource_type: str  # "cpu", "memory", "storage", "pvc", "node"
    current_usage: float  # Percentage (0-100)
    usage_limit: float  # Percentage threshold (e.g., 80)
    risk_level: str  # "low", "medium", "high", "critical"
    estimated_hours_to_exhaustion: Optional[float] = None
    trend: str = "stable"  # "stable", "increasing", "decreasing"
    recommendation: str = ""


class ResourceExhaustionDetector:
    """Detect and predict resource exhaustion in Kubernetes clusters."""

    def __init__(self):
        """Initialize resource exhaustion detector."""
        self.client = K8sClient()
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.storage_v1 = client.StorageV1Api()

    def get_exhaustion_risks(self) -> List[ExhaustionRisk]:
        """Detect at-risk resources across the cluster.

        Returns:
            List of ExhaustionRisk objects for resources at risk
        """
        risks: List[ExhaustionRisk] = []

        # Check pod CPU and memory
        risks.extend(self._check_pod_resources())

        # Check node resources
        risks.extend(self._check_node_resources())

        # Check PVC usage
        risks.extend(self._check_pvc_usage())

        # Check API server load
        risks.extend(self._check_api_server_load())

        return risks

    def _check_pod_resources(self) -> List[ExhaustionRisk]:
        """Check pod CPU and memory usage."""
        risks: List[ExhaustionRisk] = []

        try:
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                pod_dict = pod.to_dict()
                namespace = pod_dict["metadata"]["namespace"]
                pod_name = pod_dict["metadata"]["name"]

                # Check containers
                containers = pod_dict.get("spec", {}).get("containers", [])
                for container in containers:
                    container_name = container.get("name")

                    # Check CPU limits
                    cpu_limit = container.get("resources", {}).get("limits", {}).get("cpu")

                    if cpu_limit:
                        # Estimate CPU usage (simplified - would need metrics server)
                        cpu_usage_percent = self._estimate_cpu_usage(pod_name, namespace, container_name)
                        if cpu_usage_percent > 75:
                            risk = ExhaustionRisk(
                                resource_kind="Pod",
                                resource_name=pod_name,
                                resource_namespace=namespace,
                                resource_type="cpu",
                                current_usage=cpu_usage_percent,
                                usage_limit=80,
                                risk_level=self._calculate_risk_level(cpu_usage_percent),
                                trend="stable",
                                recommendation=f"Consider increasing CPU limit for {container_name} or optimizing application"
                            )
                            risks.append(risk)

                    # Check memory limits
                    memory_limit = container.get("resources", {}).get("limits", {}).get("memory")
                    if memory_limit:
                        memory_usage_percent = self._estimate_memory_usage(pod_name, namespace, container_name)
                        if memory_usage_percent > 75:
                            risk = ExhaustionRisk(
                                resource_kind="Pod",
                                resource_name=pod_name,
                                resource_namespace=namespace,
                                resource_type="memory",
                                current_usage=memory_usage_percent,
                                usage_limit=80,
                                risk_level=self._calculate_risk_level(memory_usage_percent),
                                trend="stable",
                                recommendation=f"Consider increasing memory limit for {container_name} or investigating memory leaks"
                            )
                            risks.append(risk)

        except ApiException as e:
            logger.warning(f"Failed to check pod resources: {e}")

        return risks

    def _check_node_resources(self) -> List[ExhaustionRisk]:
        """Check node CPU and memory availability."""
        risks: List[ExhaustionRisk] = []

        try:
            nodes = self.v1.list_node()

            for node in nodes.items:
                node_dict = node.to_dict()
                node_name = node_dict["metadata"]["name"]

                # Check allocatable resources
                allocatable = node_dict.get("status", {}).get("allocatable", {})
                cpu_allocatable = allocatable.get("cpu")
                memory_allocatable = allocatable.get("memory")

                # Check requested resources
                requested_cpu = 0
                requested_memory = 0

                pods = self.v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
                for pod in pods.items:
                    pod_dict = pod.to_dict()
                    containers = pod_dict.get("spec", {}).get("containers", [])
                    for container in containers:
                        cpu_req = container.get("resources", {}).get("requests", {}).get("cpu")
                        memory_req = container.get("resources", {}).get("requests", {}).get("memory")

                        if cpu_req:
                            requested_cpu += self._parse_resource_value(cpu_req)
                        if memory_req:
                            requested_memory += self._parse_resource_value(memory_req)

                # Calculate usage percentages
                if cpu_allocatable:
                    cpu_allocatable_value = self._parse_resource_value(cpu_allocatable)
                    cpu_usage_percent = (requested_cpu / cpu_allocatable_value * 100) if cpu_allocatable_value > 0 else 0

                    if cpu_usage_percent > 75:
                        risk = ExhaustionRisk(
                            resource_kind="Node",
                            resource_name=node_name,
                            resource_namespace="",
                            resource_type="cpu",
                            current_usage=cpu_usage_percent,
                            usage_limit=80,
                            risk_level=self._calculate_risk_level(cpu_usage_percent),
                            trend="stable",
                            recommendation=f"Node {node_name} is running low on CPU capacity. Consider adding more nodes or optimizing workloads."
                        )
                        risks.append(risk)

                if memory_allocatable:
                    memory_allocatable_value = self._parse_resource_value(memory_allocatable)
                    memory_usage_percent = (requested_memory / memory_allocatable_value * 100) if memory_allocatable_value > 0 else 0

                    if memory_usage_percent > 75:
                        risk = ExhaustionRisk(
                            resource_kind="Node",
                            resource_name=node_name,
                            resource_namespace="",
                            resource_type="memory",
                            current_usage=memory_usage_percent,
                            usage_limit=80,
                            risk_level=self._calculate_risk_level(memory_usage_percent),
                            trend="stable",
                            recommendation=f"Node {node_name} is running low on memory capacity. Consider adding more nodes or reducing workloads."
                        )
                        risks.append(risk)

        except ApiException as e:
            logger.warning(f"Failed to check node resources: {e}")

        return risks

    def _check_pvc_usage(self) -> List[ExhaustionRisk]:
        """Check PersistentVolumeClaim usage."""
        risks: List[ExhaustionRisk] = []

        try:
            pvcs = self.v1.list_persistent_volume_claim_for_all_namespaces()

            for pvc in pvcs.items:
                pvc_dict = pvc.to_dict()
                namespace = pvc_dict["metadata"]["namespace"]
                pvc_name = pvc_dict["metadata"]["name"]

                # Get PVC capacity
                capacity = pvc_dict.get("spec", {}).get("resources", {}).get("requests", {}).get("storage")
                if not capacity:
                    continue

                # Estimate usage (would need actual metrics)
                usage_percent = self._estimate_pvc_usage(pvc_name, namespace)

                if usage_percent > 75:
                    risk = ExhaustionRisk(
                        resource_kind="PersistentVolumeClaim",
                        resource_name=pvc_name,
                        resource_namespace=namespace,
                        resource_type="storage",
                        current_usage=usage_percent,
                        usage_limit=80,
                        risk_level=self._calculate_risk_level(usage_percent),
                        trend="stable",
                        recommendation=f"PVC {pvc_name} is running low on storage. Consider expanding the volume or cleaning up old data."
                    )
                    risks.append(risk)

        except ApiException as e:
            logger.warning(f"Failed to check PVC usage: {e}")

        return risks

    def _check_api_server_load(self) -> List[ExhaustionRisk]:
        """Check API server load and etcd capacity."""
        risks: List[ExhaustionRisk] = []

        try:
            # Count resources in cluster
            pods = self.v1.list_pod_for_all_namespaces()
            services = self.v1.list_service_for_all_namespaces()
            deployments = self.apps_v1.list_deployment_for_all_namespaces()

            total_resources = len(pods.items) + len(services.items) + len(deployments.items)

            # Estimate API server load (simplified)
            # Typical etcd can handle ~100k objects
            api_load_percent = (total_resources / 100000) * 100

            if api_load_percent > 75:
                risk = ExhaustionRisk(
                    resource_kind="APIServer",
                    resource_name="etcd",
                    resource_namespace="",
                    resource_type="etcd",
                    current_usage=api_load_percent,
                    usage_limit=80,
                    risk_level=self._calculate_risk_level(api_load_percent),
                    trend="stable",
                    recommendation="Cluster is approaching etcd capacity. Consider archiving old resources or upgrading etcd."
                )
                risks.append(risk)

        except ApiException as e:
            logger.warning(f"Failed to check API server load: {e}")

        return risks

    def predict_exhaustion(self, risk: ExhaustionRisk) -> Optional[float]:
        """Predict time until resource exhaustion.

        Args:
            risk: ExhaustionRisk object

        Returns:
            Estimated hours until exhaustion or None if not predictable
        """
        # Simplified prediction - would need historical data
        if risk.current_usage >= 95:
            return 1.0  # Critical - exhaustion within 1 hour
        elif risk.current_usage >= 90:
            return 4.0  # High - exhaustion within 4 hours
        elif risk.current_usage >= 80:
            return 24.0  # Medium - exhaustion within 24 hours
        else:
            return None  # Low risk

    def get_usage_trend(self, resource_name: str, namespace: str, resource_type: str) -> str:
        """Determine usage trend direction.

        Args:
            resource_name: Name of the resource
            namespace: Namespace of the resource
            resource_type: Type of resource (cpu, memory, storage)

        Returns:
            Trend direction: "increasing", "decreasing", or "stable"
        """
        # Simplified trend detection - would need historical data
        # For now, return stable
        return "stable"

    def _estimate_cpu_usage(self, pod_name: str, namespace: str, container_name: str) -> float:
        """Estimate CPU usage percentage (simplified)."""
        # In production, would use metrics server
        # For now, return a simulated value
        return 45.0

    def _estimate_memory_usage(self, pod_name: str, namespace: str, container_name: str) -> float:
        """Estimate memory usage percentage (simplified)."""
        # In production, would use metrics server
        # For now, return a simulated value
        return 55.0

    def _estimate_pvc_usage(self, pvc_name: str, namespace: str) -> float:
        """Estimate PVC usage percentage (simplified)."""
        # In production, would query actual filesystem usage
        # For now, return a simulated value
        return 65.0

    def _calculate_risk_level(self, usage_percent: float) -> str:
        """Calculate risk level based on usage percentage."""
        if usage_percent >= 95:
            return "critical"
        elif usage_percent >= 85:
            return "high"
        elif usage_percent >= 75:
            return "medium"
        else:
            return "low"

    def _parse_resource_value(self, value: str) -> float:
        """Parse Kubernetes resource value to float.

        Args:
            value: Resource value (e.g., "100m", "512Mi", "1Gi")

        Returns:
            Numeric value in base units
        """
        if not value:
            return 0.0

        value = str(value).strip()

        # CPU values
        if value.endswith("m"):
            return float(value[:-1]) / 1000  # millicores to cores
        elif value.endswith("n"):
            return float(value[:-1]) / 1e9  # nanocores to cores

        # Memory values
        if value.endswith("Ki"):
            return float(value[:-2]) * 1024
        elif value.endswith("Mi"):
            return float(value[:-2]) * 1024 * 1024
        elif value.endswith("Gi"):
            return float(value[:-2]) * 1024 * 1024 * 1024
        elif value.endswith("Ti"):
            return float(value[:-2]) * 1024 * 1024 * 1024 * 1024

        # Try to parse as plain number
        try:
            return float(value)
        except ValueError:
            return 0.0
