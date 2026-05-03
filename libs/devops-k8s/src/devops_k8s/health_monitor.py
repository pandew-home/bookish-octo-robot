"""Cluster health monitoring and weather calculation."""

import logging
import os
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from devops_k8s.snapshot import (
    ClusterSnapshot,
    ClusterMetrics,
    ClusterToolInfo,
    SnapshotDiff,
)
from devops_k8s.circuit_breaker import CircuitBreaker


class HealthMonitor:
    """Monitor cluster health and calculate weather state based on metrics and changes."""

    def __init__(self, max_snapshots: int = 10, max_retries: int = 3):
        """Initialize health monitor.

        Args:
            max_snapshots: Maximum number of snapshots to keep in history (default: 10)
            max_retries: Maximum number of retries for Kubernetes API calls (default: 3)
        """
        self.k8s_client = client.CoreV1Api()
        self.apps_client = client.AppsV1Api()
        self.batch_client = client.BatchV1Api()
        self.networking_client = client.NetworkingV1Api()
        self.custom_client = client.CustomObjectsApi()
        self.api_client = client.ApiClient()

        self.weather_cache: Optional[Dict[str, Any]] = None
        self.weather_cache_time: Optional[datetime] = None
        self.weather_cache_ttl_seconds = 60  # 1 minute (reduced from 300)

        self.snapshot_history: List[ClusterSnapshot] = []
        self.max_snapshots = max_snapshots
        self.baseline_snapshot: Optional[ClusterSnapshot] = None
        self.cluster_name = self._get_cluster_name()

        # Error tracking and retry configuration
        self.max_retries = max_retries
        self.errors: List[Dict[str, Any]] = []

        # Performance monitoring
        self.performance_threshold_ms = 1500  # Performance warning threshold

        self.circuit_breaker = CircuitBreaker()
        self.logger = logging.getLogger("health_monitor")

    def _get_cluster_name(self) -> str:
        """Get cluster name from environment variable or kubeconfig context.

        Returns:
            Cluster name string
        """
        # Try environment variable first
        cluster_name = os.getenv("CLUSTER_NAME")
        if cluster_name:
            return cluster_name

        # Try to get from kubeconfig context
        try:
            config.load_incluster_config()
            # When running in-cluster, use namespace or default name
            return os.getenv("CLUSTER_NAME", "kubernetes-cluster")
        except Exception:
            # When running locally, get from kubeconfig
            try:
                contexts, active_context = config.list_kube_config_contexts()
                if active_context:
                    return active_context["name"]
            except Exception:
                pass

        return "unknown-cluster"

    def _call_k8s_api_with_backoff(self, api_call: Callable, operation_name: str, *args, **kwargs) -> Any:
        """Call Kubernetes API with exponential backoff retry logic and circuit breaker.

        Args:
            api_call: The Kubernetes API method to call
            operation_name: Name of the operation for error tracking
            *args: Arguments to pass to the API call
            **kwargs: Keyword arguments to pass to the API call

        Returns:
            API call result or None if all retries failed
        """
        delay = 1.0  # Start with 1 second
        max_delay = 32.0  # Maximum 32 seconds
        for attempt in range(self.max_retries):
            try:
                # Use circuit breaker for all K8s API calls
                return self.circuit_breaker.call(api_call, *args, **kwargs)
            except Exception as e:
                if self.circuit_breaker.get_state() == "CLOSED":
                    self.logger.warning("K8s API circuit breaker is CLOSED. Skipping API call for %s.", operation_name)
                    self._track_error(
                        "k8s_api_call",
                        f"{operation_name} blocked by circuit breaker: {str(e)}",
                        "error",
                    )
                    break
                if attempt < self.max_retries - 1:
                    self._track_error(
                        "k8s_api_call",
                        f"{operation_name} attempt {attempt + 1} failed: {str(e)}",
                        "warning",
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)  # Exponential backoff
                else:
                    self._track_error(
                        "k8s_api_call",
                        f"{operation_name} failed after {self.max_retries} attempts: {str(e)}",
                        "error",
                    )
        return None

    def _track_error(self, error_type: str, message: str, severity: str = "warning") -> None:
        """Track non-critical errors during monitoring.

        Args:
            error_type: Type of error
            message: Error message
            severity: Error severity ("warning" or "error")
        """
        self.errors.append(
            {
                "type": error_type,
                "message": message,
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get tracked errors.

        Returns:
            List of error dictionaries
        """
        return self.errors

    def _get_cluster_version(self) -> str:
        """Get Kubernetes cluster version.

        Returns:
            Version string (e.g., "v1.28.5")
        """
        try:
            version_info = client.VersionApi().get_code()
            return version_info.git_version
        except Exception:
            return "unknown"

    def collect_metrics(self) -> ClusterMetrics:
        """Gather pod, resource, and event metrics from cluster.

        Returns:
            ClusterMetrics object with current metrics
        """
        # Reset errors for this collection cycle
        self.errors = []

        pod_failures = 0
        cpu_usage = 0.0
        memory_usage = 0.0
        critical_events = 0
        unhealthy_nodes = 0
        failed_deployments = 0
        failed_statefulsets = 0
        failed_daemonsets = 0
        pvc_issues = 0
        ingress_issues = 0
        argocd_apps_out_of_sync = 0
        argocd_apps_degraded = 0

        # Count pod failures
        pods = self._call_k8s_api_with_backoff(
            self.k8s_client.list_pod_for_all_namespaces,
            "list_pods"
        )
        if pods:
            for pod in pods.items:
                if pod.status.phase not in ["Running", "Succeeded"]:
                    pod_failures += 1

        # Count unhealthy nodes
        nodes = self._call_k8s_api_with_backoff(
            self.k8s_client.list_node,
            "list_nodes"
        )
        if nodes:
            for node in nodes.items:
                if node.status.conditions:
                    for condition in node.status.conditions:
                        if condition.type == "Ready" and condition.status != "True":
                            unhealthy_nodes += 1
                            break

        # Count critical events
        events = self._call_k8s_api_with_backoff(
            self.k8s_client.list_event_for_all_namespaces,
            "list_events"
        )
        if events:
            for event in events.items:
                if event.type == "Warning" or event.type == "Error":
                    critical_events += 1

        # Count failed deployments
        deployments = self._call_k8s_api_with_backoff(
            self.apps_client.list_deployment_for_all_namespaces,
            "list_deployments"
        )
        if deployments:
            for deployment in deployments.items:
                if deployment.status.replicas and deployment.status.ready_replicas:
                    if deployment.status.ready_replicas < deployment.status.replicas:
                        failed_deployments += 1

        # Count failed statefulsets
        statefulsets = self._call_k8s_api_with_backoff(
            self.apps_client.list_stateful_set_for_all_namespaces,
            "list_statefulsets"
        )
        if statefulsets:
            for statefulset in statefulsets.items:
                if statefulset.status.replicas and statefulset.status.ready_replicas:
                    if statefulset.status.ready_replicas < statefulset.status.replicas:
                        failed_statefulsets += 1

        # Count failed daemonsets
        daemonsets = self._call_k8s_api_with_backoff(
            self.apps_client.list_daemon_set_for_all_namespaces,
            "list_daemonsets"
        )
        if daemonsets:
            for daemonset in daemonsets.items:
                if daemonset.status.desired_number_scheduled and daemonset.status.number_ready:
                    if daemonset.status.number_ready < daemonset.status.desired_number_scheduled:
                        failed_daemonsets += 1

        # Count PVC issues
        pvcs = self._call_k8s_api_with_backoff(
            self.k8s_client.list_persistent_volume_claim_for_all_namespaces,
            "list_pvcs"
        )
        if pvcs:
            for pvc in pvcs.items:
                if pvc.status.phase not in ["Bound"]:
                    pvc_issues += 1

        # Count ingress issues
        ingresses = self._call_k8s_api_with_backoff(
            self.networking_client.list_ingress_for_all_namespaces,
            "list_ingresses"
        )
        if ingresses:
            for ingress in ingresses.items:
                if not ingress.status.load_balancer or not ingress.status.load_balancer.ingress:
                    ingress_issues += 1

        # Count ArgoCD issues (if installed)
        try:
            argocd_apps = self._call_k8s_api_with_backoff(
                self.custom_client.list_namespaced_custom_object,
                "list_argocd_apps",
                group="argoproj.io",
                version="v1alpha1",
                namespace="argocd",
                plural="applications",
            )
            if argocd_apps:
                for app in argocd_apps.get("items", []):
                    status = app.get("status", {})
                    sync_status = status.get("sync", {}).get("status", "Unknown")
                    health_status = status.get("health", {}).get("status", "Unknown")

                    if sync_status == "OutOfSync":
                        argocd_apps_out_of_sync += 1
                    if health_status == "Degraded":
                        argocd_apps_degraded += 1
        except Exception:
            # ArgoCD might not be installed, this is not an error
            pass

        return ClusterMetrics(
            pod_failures=pod_failures,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            critical_events=critical_events,
            unhealthy_nodes=unhealthy_nodes,
            failed_deployments=failed_deployments,
            failed_statefulsets=failed_statefulsets,
            failed_daemonsets=failed_daemonsets,
            pvc_issues=pvc_issues,
            ingress_issues=ingress_issues,
            argocd_apps_out_of_sync=argocd_apps_out_of_sync,
            argocd_apps_degraded=argocd_apps_degraded,
        )

    async def collect_metrics_async(self) -> ClusterMetrics:
        """Gather metrics asynchronously for better performance.

        Collects pods, nodes, events, deployments, statefulsets, and daemonsets in parallel.
        Skips PVC, Ingress, and ArgoCD checks for performance optimization.

        Returns:
            ClusterMetrics object with current metrics
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        # Reset errors for this collection cycle
        self.errors = []

        # Use thread pool for K8s API calls (K8s client is synchronous)
        with ThreadPoolExecutor(max_workers=6) as executor:
            loop = asyncio.get_event_loop()

            # Collect metrics in parallel
            pods_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.k8s_client.list_pod_for_all_namespaces,
                "list_pods"
            )

            nodes_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.k8s_client.list_node,
                "list_nodes"
            )

            events_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.k8s_client.list_event_for_all_namespaces,
                "list_events"
            )

            deployments_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.apps_client.list_deployment_for_all_namespaces,
                "list_deployments"
            )

            statefulsets_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.apps_client.list_stateful_set_for_all_namespaces,
                "list_statefulsets"
            )

            daemonsets_task = loop.run_in_executor(
                executor,
                self._call_k8s_api_with_backoff,
                self.apps_client.list_daemon_set_for_all_namespaces,
                "list_daemonsets"
            )

            # Wait for all tasks to complete
            results = await asyncio.gather(
                pods_task,
                nodes_task,
                events_task,
                deployments_task,
                statefulsets_task,
                daemonsets_task,
                return_exceptions=True
            )

            pods, nodes, events, deployments, statefulsets, daemonsets = results

        # Process results and calculate metrics
        pod_failures = 0
        if pods and not isinstance(pods, Exception):
            for pod in pods.items:
                if pod.status.phase not in ["Running", "Succeeded"]:
                    pod_failures += 1

        unhealthy_nodes = 0
        if nodes and not isinstance(nodes, Exception):
            for node in nodes.items:
                if node.status.conditions:
                    for condition in node.status.conditions:
                        if condition.type == "Ready" and condition.status != "True":
                            unhealthy_nodes += 1
                            break

        critical_events = 0
        if events and not isinstance(events, Exception):
            for event in events.items:
                if event.type in ["Warning", "Error"]:
                    critical_events += 1

        failed_deployments = 0
        if deployments and not isinstance(deployments, Exception):
            for deployment in deployments.items:
                if deployment.status.replicas and deployment.status.ready_replicas:
                    if deployment.status.ready_replicas < deployment.status.replicas:
                        failed_deployments += 1

        failed_statefulsets = 0
        if statefulsets and not isinstance(statefulsets, Exception):
            for statefulset in statefulsets.items:
                if statefulset.status.replicas and statefulset.status.ready_replicas:
                    if statefulset.status.ready_replicas < statefulset.status.replicas:
                        failed_statefulsets += 1

        failed_daemonsets = 0
        if daemonsets and not isinstance(daemonsets, Exception):
            for daemonset in daemonsets.items:
                if daemonset.status.desired_number_scheduled and daemonset.status.number_ready:
                    if daemonset.status.number_ready < daemonset.status.desired_number_scheduled:
                        failed_daemonsets += 1

        # Skip PVC, Ingress, and ArgoCD checks for performance
        # These can be added back if needed with separate caching

        return ClusterMetrics(
            pod_failures=pod_failures,
            cpu_usage=0.0,  # Skip CPU/memory for now (requires metrics-server)
            memory_usage=0.0,
            critical_events=critical_events,
            unhealthy_nodes=unhealthy_nodes,
            failed_deployments=failed_deployments,
            failed_statefulsets=failed_statefulsets,
            failed_daemonsets=failed_daemonsets,
            pvc_issues=0,  # Skip for performance
            ingress_issues=0,  # Skip for performance
            argocd_apps_out_of_sync=0,  # Skip for performance
            argocd_apps_degraded=0,  # Skip for performance
        )

    def _detect_cluster_tools(self) -> List[ClusterToolInfo]:
        """Detect installed cluster tools by checking CRDs, namespaces, and Helm releases.

        Returns:
            List of detected ClusterToolInfo objects
        """
        tools: List[ClusterToolInfo] = []

        # Check for ArgoCD
        argocd_ns = self._call_k8s_api_with_backoff(
            self.k8s_client.read_namespace,
            "read_argocd_namespace",
            "argocd"
        )
        if argocd_ns:
            # Try to get ArgoCD version from deployment
            deployments = self._call_k8s_api_with_backoff(
                self.apps_client.list_namespaced_deployment,
                "list_argocd_deployments",
                "argocd"
            )
            if deployments:
                for deployment in deployments.items:
                    if "argocd-server" in deployment.metadata.name:
                        version = "unknown"
                        if deployment.spec.template.spec.containers:
                            image = deployment.spec.template.spec.containers[0].image
                            if ":" in image:
                                version = image.split(":")[-1]
                        age_days = (
                            datetime.utcnow() - deployment.metadata.creation_timestamp.replace(tzinfo=None)
                        ).days
                        tools.append(
                            ClusterToolInfo(
                                name="ArgoCD",
                                version=version,
                                category="gitops",
                                deployment_age_days=age_days,
                                status="healthy",
                            )
                        )
                        break

        # Check for Kyverno
        kyverno_ns = self._call_k8s_api_with_backoff(
            self.k8s_client.read_namespace,
            "read_kyverno_namespace",
            "kyverno"
        )
        if kyverno_ns:
            deployments = self._call_k8s_api_with_backoff(
                self.apps_client.list_namespaced_deployment,
                "list_kyverno_deployments",
                "kyverno"
            )
            if deployments:
                for deployment in deployments.items:
                    if "kyverno" in deployment.metadata.name and "controller" in deployment.metadata.name:
                        version = "unknown"
                        if deployment.spec.template.spec.containers:
                            image = deployment.spec.template.spec.containers[0].image
                            if ":" in image:
                                version = image.split(":")[-1]
                        age_days = (
                            datetime.utcnow() - deployment.metadata.creation_timestamp.replace(tzinfo=None)
                        ).days
                        tools.append(
                            ClusterToolInfo(
                                name="Kyverno",
                                version=version,
                                category="security",
                                deployment_age_days=age_days,
                                status="healthy",
                            )
                        )
                        break

        # Check for Cilium
        kube_system_ns = self._call_k8s_api_with_backoff(
            self.k8s_client.read_namespace,
            "read_kube_system_namespace",
            "kube-system"
        )
        if kube_system_ns:
            daemonsets = self._call_k8s_api_with_backoff(
                self.apps_client.list_namespaced_daemon_set,
                "list_cilium_daemonsets",
                "kube-system"
            )
            if daemonsets:
                for daemonset in daemonsets.items:
                    if "cilium" in daemonset.metadata.name:
                        version = "unknown"
                        if daemonset.spec.template.spec.containers:
                            image = daemonset.spec.template.spec.containers[0].image
                            if ":" in image:
                                version = image.split(":")[-1]
                        age_days = (
                            datetime.utcnow() - daemonset.metadata.creation_timestamp.replace(tzinfo=None)
                        ).days
                        tools.append(
                            ClusterToolInfo(
                                name="Cilium",
                                version=version,
                                category="networking",
                                deployment_age_days=age_days,
                                status="healthy",
                            )
                        )
                        break

        # Check for cert-manager
        cert_manager_ns = self._call_k8s_api_with_backoff(
            self.k8s_client.read_namespace,
            "read_cert_manager_namespace",
            "cert-manager"
        )
        if cert_manager_ns:
            deployments = self._call_k8s_api_with_backoff(
                self.apps_client.list_namespaced_deployment,
                "list_cert_manager_deployments",
                "cert-manager"
            )
            if deployments:
                for deployment in deployments.items:
                    if "cert-manager" in deployment.metadata.name and "webhook" not in deployment.metadata.name:
                        version = "unknown"
                        if deployment.spec.template.spec.containers:
                            image = deployment.spec.template.spec.containers[0].image
                            if ":" in image:
                                version = image.split(":")[-1]
                        age_days = (
                            datetime.utcnow() - deployment.metadata.creation_timestamp.replace(tzinfo=None)
                        ).days
                        tools.append(
                            ClusterToolInfo(
                                name="cert-manager",
                                version=version,
                                category="security",
                                deployment_age_days=age_days,
                                status="healthy",
                            )
                        )
                        break

        return tools

    def take_snapshot(self) -> ClusterSnapshot:
        """Capture current cluster state as a snapshot.

        Returns:
            ClusterSnapshot object with current state
        """
        snapshot_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Collect metrics
        metrics = self.collect_metrics()

        # Detect cluster tools
        cluster_tools = self._detect_cluster_tools()

        # Get cluster info
        cluster_version = self._get_cluster_version()

        # Count resources
        pods = self._call_k8s_api_with_backoff(
            self.k8s_client.list_pod_for_all_namespaces,
            "count_pods"
        )
        total_pods = len(pods.items) if pods else 0

        nodes = self._call_k8s_api_with_backoff(
            self.k8s_client.list_node,
            "count_nodes"
        )
        total_nodes = len(nodes.items) if nodes else 0

        namespaces = self._call_k8s_api_with_backoff(
            self.k8s_client.list_namespace,
            "count_namespaces"
        )
        total_namespaces = len(namespaces.items) if namespaces else 0

        # Get API server latency (simplified)
        api_server_latency_ms = 0.0

        # Determine sequence number
        sequence = len(self.snapshot_history) + 1

        # Get previous snapshot ID
        previous_snapshot_id = None
        if self.snapshot_history:
            previous_snapshot_id = self.snapshot_history[-1].id

        snapshot = ClusterSnapshot(
            id=snapshot_id,
            timestamp=timestamp,
            cluster_name=self.cluster_name,
            cluster_version=cluster_version,
            metrics=metrics,
            cluster_tools=cluster_tools,
            total_pods=total_pods,
            total_nodes=total_nodes,
            total_namespaces=total_namespaces,
            api_server_latency_ms=api_server_latency_ms,
            previous_snapshot_id=previous_snapshot_id,
            snapshot_sequence=sequence,
        )

        # Add to history and maintain max size
        self.snapshot_history.append(snapshot)
        if len(self.snapshot_history) > self.max_snapshots:
            self.snapshot_history.pop(0)

        # Set as baseline if first snapshot
        if self.baseline_snapshot is None:
            self.baseline_snapshot = snapshot

        return snapshot

    def compare_snapshots(self, current: ClusterSnapshot, previous: ClusterSnapshot) -> SnapshotDiff:
        """Compare two snapshots to compute differences.

        Args:
            current: Current cluster snapshot
            previous: Previous cluster snapshot

        Returns:
            SnapshotDiff object with computed differences
        """
        time_delta = (current.timestamp - previous.timestamp).total_seconds()

        # Calculate metric changes
        new_pod_failures = max(0, current.metrics.pod_failures - previous.metrics.pod_failures)
        resolved_pod_failures = max(0, previous.metrics.pod_failures - current.metrics.pod_failures)
        cpu_usage_increase = current.metrics.cpu_usage - previous.metrics.cpu_usage
        memory_usage_increase = current.metrics.memory_usage - previous.metrics.memory_usage
        new_critical_events = max(0, current.metrics.critical_events - previous.metrics.critical_events)
        new_unhealthy_nodes = max(0, current.metrics.unhealthy_nodes - previous.metrics.unhealthy_nodes)
        new_failed_deployments = max(0, current.metrics.failed_deployments - previous.metrics.failed_deployments)
        new_failed_statefulsets = max(0, current.metrics.failed_statefulsets - previous.metrics.failed_statefulsets)
        new_failed_daemonsets = max(0, current.metrics.failed_daemonsets - previous.metrics.failed_daemonsets)
        new_pvc_issues = max(0, current.metrics.pvc_issues - previous.metrics.pvc_issues)
        new_ingress_issues = max(0, current.metrics.ingress_issues - previous.metrics.ingress_issues)
        new_argocd_out_of_sync = max(0, current.metrics.argocd_apps_out_of_sync - previous.metrics.argocd_apps_out_of_sync)
        new_argocd_degraded = max(0, current.metrics.argocd_apps_degraded - previous.metrics.argocd_apps_degraded)

        # Detect tool changes
        current_tools = {tool.name: tool for tool in current.cluster_tools}
        previous_tools = {tool.name: tool for tool in previous.cluster_tools}

        tools_added = [tool for name, tool in current_tools.items() if name not in previous_tools]
        tools_removed = [tool for name, tool in previous_tools.items() if name not in current_tools]

        tools_version_changed = []
        for name in current_tools:
            if name in previous_tools:
                if current_tools[name].version != previous_tools[name].version:
                    tools_version_changed.append(
                        (name, previous_tools[name].version, current_tools[name].version)
                    )

        return SnapshotDiff(
            snapshot1_id=previous.id,
            snapshot2_id=current.id,
            timestamp=current.timestamp,
            time_delta_seconds=time_delta,
            new_pod_failures=new_pod_failures,
            resolved_pod_failures=resolved_pod_failures,
            cpu_usage_increase=cpu_usage_increase,
            memory_usage_increase=memory_usage_increase,
            new_critical_events=new_critical_events,
            new_unhealthy_nodes=new_unhealthy_nodes,
            new_failed_deployments=new_failed_deployments,
            new_failed_statefulsets=new_failed_statefulsets,
            new_failed_daemonsets=new_failed_daemonsets,
            new_pvc_issues=new_pvc_issues,
            new_ingress_issues=new_ingress_issues,
            new_argocd_out_of_sync=new_argocd_out_of_sync,
            new_argocd_degraded=new_argocd_degraded,
            tools_added=tools_added,
            tools_removed=tools_removed,
            tools_version_changed=tools_version_changed,
        )

    def calculate_weather(self, current: ClusterSnapshot, diff: Optional[SnapshotDiff] = None) -> str:
        """Calculate weather state based on current metrics and changes.

        Args:
            current: Current cluster snapshot
            diff: Optional snapshot diff for change-based scoring

        Returns:
            Weather state string: "sunny", "partly-cloudy", "cloudy", "rainy", or "stormy"
        """
        score = 0

        # Current state metrics (0-60 points)

        # Pod failures (0-12 points)
        if current.metrics.pod_failures > 10:
            score += 12
        elif current.metrics.pod_failures > 5:
            score += 8
        elif current.metrics.pod_failures > 0:
            score += 4

        # Resource usage (0-12 points)
        if current.metrics.cpu_usage > 90 or current.metrics.memory_usage > 90:
            score += 12
        elif current.metrics.cpu_usage > 75 or current.metrics.memory_usage > 75:
            score += 6

        # Critical events (0-8 points)
        if current.metrics.critical_events > 5:
            score += 8
        elif current.metrics.critical_events > 2:
            score += 4
        elif current.metrics.critical_events > 0:
            score += 2

        # Node health (0-8 points)
        if current.metrics.unhealthy_nodes > 2:
            score += 8
        elif current.metrics.unhealthy_nodes > 0:
            score += 4

        # Workload failures (0-8 points)
        total_workload_failures = (
            current.metrics.failed_deployments
            + current.metrics.failed_statefulsets
            + current.metrics.failed_daemonsets
        )
        if total_workload_failures > 5:
            score += 8
        elif total_workload_failures > 2:
            score += 4
        elif total_workload_failures > 0:
            score += 2

        # Storage issues (0-4 points)
        if current.metrics.pvc_issues > 3:
            score += 4
        elif current.metrics.pvc_issues > 0:
            score += 2

        # Networking issues (0-4 points)
        if current.metrics.ingress_issues > 2:
            score += 4
        elif current.metrics.ingress_issues > 0:
            score += 2

        # ArgoCD issues (0-4 points)
        if current.metrics.argocd_apps_out_of_sync > 3 or current.metrics.argocd_apps_degraded > 1:
            score += 4
        elif current.metrics.argocd_apps_out_of_sync > 0 or current.metrics.argocd_apps_degraded > 0:
            score += 2

        # Changes from previous snapshot (0-40 points)
        if diff:
            # New pod failures (0-12 points)
            if diff.new_pod_failures > 5:
                score += 12
            elif diff.new_pod_failures > 2:
                score += 6
            elif diff.new_pod_failures > 0:
                score += 3

            # Resource usage increase (0-8 points)
            if diff.cpu_usage_increase > 20 or diff.memory_usage_increase > 20:
                score += 8
            elif diff.cpu_usage_increase > 10 or diff.memory_usage_increase > 10:
                score += 4

            # New critical events (0-8 points)
            if diff.new_critical_events > 3:
                score += 8
            elif diff.new_critical_events > 0:
                score += 4

            # New workload failures (0-6 points)
            total_new_workload_failures = (
                diff.new_failed_deployments + diff.new_failed_statefulsets + diff.new_failed_daemonsets
            )
            if total_new_workload_failures > 2:
                score += 6
            elif total_new_workload_failures > 0:
                score += 3

            # New networking/storage issues (0-6 points)
            if diff.new_ingress_issues > 1 or diff.new_pvc_issues > 1:
                score += 6
            elif diff.new_ingress_issues > 0 or diff.new_pvc_issues > 0:
                score += 3

        # Map score to weather state
        if score >= 50:
            return "stormy"
        elif score >= 32:
            return "rainy"
        elif score >= 18:
            return "cloudy"
        elif score >= 6:
            return "partly-cloudy"
        else:
            return "sunny"

    def _calculate_weather_from_metrics(self, metrics: ClusterMetrics) -> str:
        """Calculate weather state from metrics only (no diff).
        Simplified for performance.

        Args:
            metrics: Current cluster metrics

        Returns:
            Weather state string
        """
        score = 0

        # Pod failures (0-12 points)
        if metrics.pod_failures > 10:
            score += 12
        elif metrics.pod_failures > 5:
            score += 8
        elif metrics.pod_failures > 0:
            score += 4

        # Critical events (0-8 points)
        if metrics.critical_events > 5:
            score += 8
        elif metrics.critical_events > 2:
            score += 4
        elif metrics.critical_events > 0:
            score += 2

        # Node health (0-8 points)
        if metrics.unhealthy_nodes > 2:
            score += 8
        elif metrics.unhealthy_nodes > 0:
            score += 4

        # Workload failures (0-8 points)
        total_workload_failures = (
            metrics.failed_deployments
            + metrics.failed_statefulsets
            + metrics.failed_daemonsets
        )
        if total_workload_failures > 5:
            score += 8
        elif total_workload_failures > 2:
            score += 4
        elif total_workload_failures > 0:
            score += 2

        # Map score to weather state
        if score >= 30:
            return "stormy"
        elif score >= 20:
            return "rainy"
        elif score >= 12:
            return "cloudy"
        elif score >= 6:
            return "partly-cloudy"
        else:
            return "sunny"

    async def get_current_weather_async(self) -> Dict[str, Any]:
        """Get current weather state asynchronously with performance tracking.

        Returns:
            Dictionary with weather state and cluster info
        """
        import logging

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Check cache
        if self.weather_cache and self.weather_cache_time:
            cache_age = (datetime.utcnow() - self.weather_cache_time).total_seconds()
            if cache_age < self.weather_cache_ttl_seconds:
                return self.weather_cache

        # Collect metrics asynchronously
        metrics = await self.collect_metrics_async()

        # Get cluster info (fast operations)
        cluster_version = self._get_cluster_version()
        cluster_tools = []  # Skip tool detection for performance

        # Calculate weather (fast operation)
        weather_state = self._calculate_weather_from_metrics(metrics)

        # Build weather response
        weather_response = {
            "state": weather_state,
            "cluster_name": self.cluster_name,
            "cluster_version": cluster_version,
            "metrics": {
                "pod_failures": metrics.pod_failures,
                "cpu_usage": metrics.cpu_usage,
                "memory_usage": metrics.memory_usage,
                "critical_events": metrics.critical_events,
            },
            "cluster_tools": cluster_tools,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Cache the result
        self.weather_cache = weather_response
        self.weather_cache_time = datetime.utcnow()

        # Track performance
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > self.performance_threshold_ms:
            logger.warning(
                f"Weather endpoint performance warning: {elapsed_ms:.0f}ms "
                f"(threshold: {self.performance_threshold_ms}ms)"
            )

        return weather_response

    def get_current_weather(self) -> Dict[str, Any]:
        """Get current weather state (cached or fresh).

        Returns:
            Dictionary with weather state and cluster info
        """
        # Check cache
        if self.weather_cache and self.weather_cache_time:
            if (datetime.utcnow() - self.weather_cache_time).total_seconds() < self.weather_cache_ttl_seconds:
                return self.weather_cache

        # Take fresh snapshot
        current_snapshot = self.take_snapshot()

        # Calculate weather
        diff = None
        if self.snapshot_history and len(self.snapshot_history) > 1:
            diff = self.compare_snapshots(current_snapshot, self.snapshot_history[-2])

        weather_state = self.calculate_weather(current_snapshot, diff)

        # Build weather response
        weather_response = {
            "state": weather_state,
            "cluster_name": self.cluster_name,
            "cluster_version": current_snapshot.cluster_version,
            "metrics": {
                "pod_failures": current_snapshot.metrics.pod_failures,
                "cpu_usage": current_snapshot.metrics.cpu_usage,
                "memory_usage": current_snapshot.metrics.memory_usage,
                "critical_events": current_snapshot.metrics.critical_events,
            },
            "cluster_tools": [
                {
                    "name": tool.name,
                    "version": tool.version,
                    "category": tool.category,
                    "deployment_age_days": tool.deployment_age_days,
                    "status": tool.status,
                }
                for tool in current_snapshot.cluster_tools
            ],
            "timestamp": current_snapshot.timestamp.isoformat(),
        }

        # Cache the result
        self.weather_cache = weather_response
        self.weather_cache_time = datetime.utcnow()

        return weather_response
