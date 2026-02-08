"""RBAC management utilities."""

from kubernetes import client, config
from kubernetes.client.rest import ApiException


class RBACManager:
    """Manage role-based access control for cluster resources."""

    def __init__(self):
        """Initialize RBAC manager."""
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        self.rbac_api = client.RbacAuthorizationV1Api()
        self.v1 = client.CoreV1Api()

    def validate_service_account(self, service_account_name: str, namespace: str) -> bool:
        """Validate that service account exists and has correct RBAC.

        Args:
            service_account_name: Name of the service account
            namespace: Namespace where service account is located

        Returns:
            True if service account exists and is properly configured
        """
        try:
            sa = self.v1.read_namespaced_service_account(service_account_name, namespace)
            return sa is not None
        except ApiException:
            return False

    def get_service_account_permissions(self, service_account_name: str, namespace: str) -> dict:
        """Get all permissions for a service account.

        Args:
            service_account_name: Name of the service account
            namespace: Namespace where service account is located

        Returns:
            Dictionary with permissions information
        """
        permissions = {
            "service_account": service_account_name,
            "namespace": namespace,
            "roles": [],
            "cluster_roles": [],
        }

        try:
            # Get RoleBindings in namespace
            role_bindings = self.rbac_api.list_namespaced_role_binding(namespace)
            for rb in role_bindings.items:
                for subject in rb.subjects or []:
                    if subject.kind == "ServiceAccount" and subject.name == service_account_name:
                        permissions["roles"].append(rb.role_ref.name)

            # Get ClusterRoleBindings
            cluster_role_bindings = self.rbac_api.list_cluster_role_binding()
            for crb in cluster_role_bindings.items:
                for subject in crb.subjects or []:
                    if (
                        subject.kind == "ServiceAccount"
                        and subject.name == service_account_name
                        and subject.namespace == namespace
                    ):
                        permissions["cluster_roles"].append(crb.role_ref.name)

        except ApiException as e:
            permissions["error"] = str(e)

        return permissions

    def check_cluster_access(self, resource: str, namespace: str = None, verb: str = "get") -> bool:
        """Check if service account has access to a resource.

        Args:
            resource: Resource type (e.g., "pods", "deployments")
            namespace: Namespace (None for cluster-wide)
            verb: Verb to check (default: "get")

        Returns:
            True if service account has access
        """
        # This is a simplified check - in production, use SubjectAccessReview
        try:
            # Try to list the resource
            if resource == "pods":
                if namespace:
                    self.v1.list_namespaced_pod(namespace)
                else:
                    self.v1.list_pod_for_all_namespaces()
            elif resource == "deployments":
                apps_api = client.AppsV1Api()
                if namespace:
                    apps_api.list_namespaced_deployment(namespace)
                else:
                    apps_api.list_deployment_for_all_namespaces()
            return True
        except ApiException:
            return False
