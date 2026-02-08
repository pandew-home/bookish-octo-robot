"""Kubernetes API client utilities."""

from kubernetes import client, config
from kubernetes.client.rest import ApiException


class K8sClient:
    """Wrapper around Kubernetes Python client for common operations."""

    def __init__(self):
        """Initialize Kubernetes client."""
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self.custom_api = client.CustomObjectsApi()

    def get_pod(self, name: str, namespace: str) -> dict:
        """Get pod by name and namespace.

        Args:
            name: Pod name
            namespace: Namespace name

        Returns:
            Pod object as dictionary
        """
        try:
            pod = self.v1.read_namespaced_pod(name, namespace)
            return pod.to_dict()
        except ApiException as e:
            raise Exception(f"Failed to get pod {name} in namespace {namespace}: {e}")

    def list_pods(self, namespace: str = None) -> list:
        """List pods in namespace or all namespaces.

        Args:
            namespace: Namespace name (None for all namespaces)

        Returns:
            List of pod objects as dictionaries
        """
        try:
            if namespace:
                pods = self.v1.list_namespaced_pod(namespace)
            else:
                pods = self.v1.list_pod_for_all_namespaces()
            return [pod.to_dict() for pod in pods.items]
        except ApiException as e:
            raise Exception(f"Failed to list pods: {e}")

    def get_deployment(self, name: str, namespace: str) -> dict:
        """Get deployment by name and namespace.

        Args:
            name: Deployment name
            namespace: Namespace name

        Returns:
            Deployment object as dictionary
        """
        try:
            deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
            return deployment.to_dict()
        except ApiException as e:
            raise Exception(f"Failed to get deployment {name} in namespace {namespace}: {e}")

    def list_deployments(self, namespace: str = None) -> list:
        """List deployments in namespace or all namespaces.

        Args:
            namespace: Namespace name (None for all namespaces)

        Returns:
            List of deployment objects as dictionaries
        """
        try:
            if namespace:
                deployments = self.apps_v1.list_namespaced_deployment(namespace)
            else:
                deployments = self.apps_v1.list_deployment_for_all_namespaces()
            return [deployment.to_dict() for deployment in deployments.items]
        except ApiException as e:
            raise Exception(f"Failed to list deployments: {e}")

    def get_service(self, name: str, namespace: str) -> dict:
        """Get service by name and namespace.

        Args:
            name: Service name
            namespace: Namespace name

        Returns:
            Service object as dictionary
        """
        try:
            service = self.v1.read_namespaced_service(name, namespace)
            return service.to_dict()
        except ApiException as e:
            raise Exception(f"Failed to get service {name} in namespace {namespace}: {e}")

    def list_services(self, namespace: str = None) -> list:
        """List services in namespace or all namespaces.

        Args:
            namespace: Namespace name (None for all namespaces)

        Returns:
            List of service objects as dictionaries
        """
        try:
            if namespace:
                services = self.v1.list_namespaced_service(namespace)
            else:
                services = self.v1.list_service_for_all_namespaces()
            return [service.to_dict() for service in services.items]
        except ApiException as e:
            raise Exception(f"Failed to list services: {e}")

    def get_namespace(self, name: str) -> dict:
        """Get namespace by name.

        Args:
            name: Namespace name

        Returns:
            Namespace object as dictionary
        """
        try:
            namespace = self.v1.read_namespace(name)
            return namespace.to_dict()
        except ApiException as e:
            raise Exception(f"Failed to get namespace {name}: {e}")

    def list_namespaces(self) -> list:
        """List all namespaces.

        Returns:
            List of namespace objects as dictionaries
        """
        try:
            namespaces = self.v1.list_namespace()
            return [ns.to_dict() for ns in namespaces.items]
        except ApiException as e:
            raise Exception(f"Failed to list namespaces: {e}")

    def get_pod_logs(self, name: str, namespace: str, tail_lines: int = 100) -> str:
        """Get pod logs.

        Args:
            name: Pod name
            namespace: Namespace name
            tail_lines: Number of lines to retrieve

        Returns:
            Pod logs as string
        """
        try:
            logs = self.v1.read_namespaced_pod_log(name, namespace, tail_lines=tail_lines)
            return logs
        except ApiException as e:
            raise Exception(f"Failed to get logs for pod {name} in namespace {namespace}: {e}")

    def list_nodes(self) -> list:
        """List all nodes in the cluster.

        Returns:
            List of node objects as dictionaries
        """
        try:
            nodes = self.v1.list_node()
            return [node.to_dict() for node in nodes.items]
        except ApiException as e:
            raise Exception(f"Failed to list nodes: {e}")

    def list_events(self, namespace: str, involved_kind: str | None = None, involved_name: str | None = None) -> list:
        """List events in a namespace, optionally filtered by involved object.

        Args:
            namespace: Namespace name
            involved_kind: Optional kind of involved object (e.g., Pod, Deployment)
            involved_name: Optional name of involved object

        Returns:
            List of event objects as dictionaries
        """
        try:
            events = self.v1.list_namespaced_event(namespace)
            items = [evt.to_dict() for evt in events.items]
            if involved_kind or involved_name:
                filtered = []
                for evt in items:
                    obj = evt.get("involved_object") or evt.get("involvedObject")
                    if not obj:
                        continue
                    if involved_kind and (obj.get("kind") != involved_kind):
                        continue
                    if involved_name and (obj.get("name") != involved_name):
                        continue
                    filtered.append(evt)
                return filtered
            return items
        except ApiException as e:
            raise Exception(f"Failed to list events in namespace {namespace}: {e}")
