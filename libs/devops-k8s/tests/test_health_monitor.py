"""Unit tests for HealthMonitor class."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from devops_k8s.health_monitor import HealthMonitor
from devops_k8s.snapshot import ClusterSnapshot, ClusterMetrics, ClusterToolInfo


@pytest.fixture
def health_monitor():
    """Create a HealthMonitor instance for testing."""
    with patch("devops_k8s.health_monitor.client"):
        monitor = HealthMonitor()
        return monitor


@pytest.fixture
def sample_metrics():
    """Create sample cluster metrics."""
    return ClusterMetrics(
        pod_failures=2,
        cpu_usage=45.0,
        memory_usage=60.0,
        critical_events=1,
        unhealthy_nodes=0,
        failed_deployments=0,
        failed_statefulsets=0,
        failed_daemonsets=0,
        pvc_issues=0,
        ingress_issues=0,
        argocd_apps_out_of_sync=0,
        argocd_apps_degraded=0,
    )


@pytest.fixture
def sample_snapshot(sample_metrics):
    """Create a sample cluster snapshot."""
    return ClusterSnapshot(
        id="snap-001",
        timestamp=datetime.utcnow(),
        cluster_name="test-cluster",
        cluster_version="v1.28.5",
        metrics=sample_metrics,
        cluster_tools=[
            ClusterToolInfo(
                name="ArgoCD",
                version="v2.9.3",
                category="gitops",
                deployment_age_days=45,
                status="healthy",
            )
        ],
        total_pods=100,
        total_nodes=5,
        total_namespaces=10,
        api_server_latency_ms=50.0,
    )


class TestHealthMonitorInitialization:
    """Test HealthMonitor initialization."""

    def test_init_creates_instance(self, health_monitor):
        """Test that HealthMonitor initializes correctly."""
        assert health_monitor is not None
        assert health_monitor.max_snapshots == 10
        assert health_monitor.snapshot_history == []
        assert health_monitor.baseline_snapshot is None

    def test_get_cluster_name_from_env(self):
        """Test getting cluster name from environment variable."""
        with patch.dict("os.environ", {"CLUSTER_NAME": "my-cluster"}):
            with patch("devops_k8s.health_monitor.client"):
                monitor = HealthMonitor()
                assert monitor.cluster_name == "my-cluster"

    def test_get_cluster_name_default(self):
        """Test getting default cluster name when env var not set."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("devops_k8s.health_monitor.client"):
                with patch("devops_k8s.health_monitor.config"):
                    monitor = HealthMonitor()
                    assert monitor.cluster_name in ["kubernetes-cluster", "unknown-cluster"]


class TestWeatherCalculation:
    """Test weather calculation logic."""

    def test_sunny_weather(self, health_monitor, sample_metrics):
        """Test sunny weather calculation for healthy cluster."""
        snapshot = ClusterSnapshot(
            id="snap-001",
            timestamp=datetime.utcnow(),
            cluster_name="test-cluster",
            cluster_version="v1.28.5",
            metrics=ClusterMetrics(
                pod_failures=0,
                cpu_usage=30.0,
                memory_usage=40.0,
                critical_events=0,
                unhealthy_nodes=0,
                failed_deployments=0,
                failed_statefulsets=0,
                failed_daemonsets=0,
                pvc_issues=0,
                ingress_issues=0,
                argocd_apps_out_of_sync=0,
                argocd_apps_degraded=0,
            ),
            cluster_tools=[],
            total_pods=100,
            total_nodes=5,
            total_namespaces=10,
            api_server_latency_ms=50.0,
        )

        weather = health_monitor.calculate_weather(snapshot)
        assert weather == "sunny"

    def test_partly_cloudy_weather(self, health_monitor):
        """Test partly-cloudy weather calculation."""
        snapshot = ClusterSnapshot(
            id="snap-001",
            timestamp=datetime.utcnow(),
            cluster_name="test-cluster",
            cluster_version="v1.28.5",
            metrics=ClusterMetrics(
                pod_failures=2,
                cpu_usage=60.0,
                memory_usage=60.0,
                critical_events=2,
                unhealthy_nodes=0,
                failed_deployments=0,
                failed_statefulsets=0,
                failed_daemonsets=0,
                pvc_issues=0,
                ingress_issues=0,
                argocd_apps_out_of_sync=0,
                argocd_apps_degraded=0,
            ),
            cluster_tools=[],
            total_pods=100,
            total_nodes=5,
            total_namespaces=10,
            api_server_latency_ms=50.0,
        )

        weather = health_monitor.calculate_weather(snapshot)
        assert weather == "partly-cloudy"

    def test_cloudy_weather(self, health_monitor):
        """Test cloudy weather calculation."""
        snapshot = ClusterSnapshot(
            id="snap-001",
            timestamp=datetime.utcnow(),
            cluster_name="test-cluster",
            cluster_version="v1.28.5",
            metrics=ClusterMetrics(
                pod_failures=5,
                cpu_usage=78.0,
                memory_usage=78.0,
                critical_events=3,
                unhealthy_nodes=0,
                failed_deployments=1,
                failed_statefulsets=0,
                failed_daemonsets=0,
                pvc_issues=1,
                ingress_issues=1,
                argocd_apps_out_of_sync=1,
                argocd_apps_degraded=0,
            ),
            cluster_tools=[],
            total_pods=100,
            total_nodes=5,
            total_namespaces=10,
            api_server_latency_ms=50.0,
        )

        weather = health_monitor.calculate_weather(snapshot)
        assert weather == "cloudy"

    def test_rainy_weather(self, health_monitor):
        """Test rainy weather calculation."""
        snapshot = ClusterSnapshot(
            id="snap-001",
            timestamp=datetime.utcnow(),
            cluster_name="test-cluster",
            cluster_version="v1.28.5",
            metrics=ClusterMetrics(
                pod_failures=8,
                cpu_usage=85.0,
                memory_usage=85.0,
                critical_events=4,
                unhealthy_nodes=1,
                failed_deployments=2,
                failed_statefulsets=1,
                failed_daemonsets=0,
                pvc_issues=2,
                ingress_issues=1,
                argocd_apps_out_of_sync=2,
                argocd_apps_degraded=1,
            ),
            cluster_tools=[],
            total_pods=100,
            total_nodes=5,
            total_namespaces=10,
            api_server_latency_ms=50.0,
        )

        weather = health_monitor.calculate_weather(snapshot)
        assert weather == "rainy"

    def test_stormy_weather(self, health_monitor):
        """Test stormy weather calculation."""
        snapshot = ClusterSnapshot(
            id="snap-001",
            timestamp=datetime.utcnow(),
            cluster_name="test-cluster",
            cluster_version="v1.28.5",
            metrics=ClusterMetrics(
                pod_failures=15,
                cpu_usage=95.0,
                memory_usage=95.0,
                critical_events=10,
                unhealthy_nodes=3,
                failed_deployments=5,
                failed_statefulsets=2,
                failed_daemonsets=1,
                pvc_issues=4,
                ingress_issues=3,
                argocd_apps_out_of_sync=5,
                argocd_apps_degraded=2,
            ),
            cluster_tools=[],
            total_pods=100,
            total_nodes=5,
            total_namespaces=10,
            api_server_latency_ms=50.0,
        )

        weather = health_monitor.calculate_weather(snapshot)
        assert weather == "stormy"


class TestSnapshotComparison:
    """Test snapshot comparison logic."""

    def test_compare_snapshots_no_changes(self, health_monitor, sample_snapshot):
        """Test comparing identical snapshots."""
        snapshot2 = ClusterSnapshot(
            id="snap-002",
            timestamp=sample_snapshot.timestamp + timedelta(minutes=5),
            cluster_name=sample_snapshot.cluster_name,
            cluster_version=sample_snapshot.cluster_version,
            metrics=sample_snapshot.metrics,
            cluster_tools=sample_snapshot.cluster_tools,
            total_pods=sample_snapshot.total_pods,
            total_nodes=sample_snapshot.total_nodes,
            total_namespaces=sample_snapshot.total_namespaces,
            api_server_latency_ms=sample_snapshot.api_server_latency_ms,
            previous_snapshot_id=sample_snapshot.id,
        )

        diff = health_monitor.compare_snapshots(snapshot2, sample_snapshot)

        assert diff.new_pod_failures == 0
        assert diff.resolved_pod_failures == 0
        assert diff.cpu_usage_increase == 0.0
        assert diff.memory_usage_increase == 0.0
        assert diff.new_critical_events == 0

    def test_compare_snapshots_with_degradation(self, health_monitor, sample_snapshot):
        """Test comparing snapshots with cluster degradation."""
        snapshot2 = ClusterSnapshot(
            id="snap-002",
            timestamp=sample_snapshot.timestamp + timedelta(minutes=5),
            cluster_name=sample_snapshot.cluster_name,
            cluster_version=sample_snapshot.cluster_version,
            metrics=ClusterMetrics(
                pod_failures=5,
                cpu_usage=75.0,
                memory_usage=80.0,
                critical_events=3,
                unhealthy_nodes=1,
                failed_deployments=1,
                failed_statefulsets=0,
                failed_daemonsets=0,
                pvc_issues=1,
                ingress_issues=0,
                argocd_apps_out_of_sync=1,
                argocd_apps_degraded=0,
            ),
            cluster_tools=sample_snapshot.cluster_tools,
            total_pods=sample_snapshot.total_pods,
            total_nodes=sample_snapshot.total_nodes,
            total_namespaces=sample_snapshot.total_namespaces,
            api_server_latency_ms=sample_snapshot.api_server_latency_ms,
            previous_snapshot_id=sample_snapshot.id,
        )

        diff = health_monitor.compare_snapshots(snapshot2, sample_snapshot)

        assert diff.new_pod_failures == 3
        assert diff.cpu_usage_increase == 30.0
        assert diff.memory_usage_increase == 20.0
        assert diff.new_critical_events == 2

    def test_compare_snapshots_tool_changes(self, health_monitor, sample_snapshot):
        """Test detecting tool version changes."""
        snapshot2 = ClusterSnapshot(
            id="snap-002",
            timestamp=sample_snapshot.timestamp + timedelta(minutes=5),
            cluster_name=sample_snapshot.cluster_name,
            cluster_version=sample_snapshot.cluster_version,
            metrics=sample_snapshot.metrics,
            cluster_tools=[
                ClusterToolInfo(
                    name="ArgoCD",
                    version="v2.10.0",  # Version changed
                    category="gitops",
                    deployment_age_days=45,
                    status="healthy",
                ),
                ClusterToolInfo(
                    name="Kyverno",  # New tool
                    version="v1.11.0",
                    category="security",
                    deployment_age_days=30,
                    status="healthy",
                ),
            ],
            total_pods=sample_snapshot.total_pods,
            total_nodes=sample_snapshot.total_nodes,
            total_namespaces=sample_snapshot.total_namespaces,
            api_server_latency_ms=sample_snapshot.api_server_latency_ms,
            previous_snapshot_id=sample_snapshot.id,
        )

        diff = health_monitor.compare_snapshots(snapshot2, sample_snapshot)

        assert len(diff.tools_added) == 1
        assert diff.tools_added[0].name == "Kyverno"
        assert len(diff.tools_version_changed) == 1
        assert diff.tools_version_changed[0] == ("ArgoCD", "v2.9.3", "v2.10.0")


class TestSnapshotHistory:
    """Test snapshot history management."""

    def test_snapshot_history_max_size(self, health_monitor):
        """Test that snapshot history respects max size limit."""
        with patch.object(health_monitor, "collect_metrics") as mock_metrics:
            with patch.object(health_monitor, "_detect_cluster_tools") as mock_tools:
                with patch.object(health_monitor, "_get_cluster_version") as mock_version:
                    mock_metrics.return_value = ClusterMetrics(
                        pod_failures=0,
                        cpu_usage=0.0,
                        memory_usage=0.0,
                        critical_events=0,
                        unhealthy_nodes=0,
                        failed_deployments=0,
                        failed_statefulsets=0,
                        failed_daemonsets=0,
                        pvc_issues=0,
                        ingress_issues=0,
                        argocd_apps_out_of_sync=0,
                        argocd_apps_degraded=0,
                    )
                    mock_tools.return_value = []
                    mock_version.return_value = "v1.28.5"

                    # Take more snapshots than max
                    for i in range(15):
                        health_monitor.take_snapshot()

                    # Should only keep last 10
                    assert len(health_monitor.snapshot_history) == 10

    def test_baseline_snapshot_set_on_first_snapshot(self, health_monitor):
        """Test that baseline snapshot is set on first snapshot."""
        with patch.object(health_monitor, "collect_metrics") as mock_metrics:
            with patch.object(health_monitor, "_detect_cluster_tools") as mock_tools:
                with patch.object(health_monitor, "_get_cluster_version") as mock_version:
                    mock_metrics.return_value = ClusterMetrics(
                        pod_failures=0,
                        cpu_usage=0.0,
                        memory_usage=0.0,
                        critical_events=0,
                        unhealthy_nodes=0,
                        failed_deployments=0,
                        failed_statefulsets=0,
                        failed_daemonsets=0,
                        pvc_issues=0,
                        ingress_issues=0,
                        argocd_apps_out_of_sync=0,
                        argocd_apps_degraded=0,
                    )
                    mock_tools.return_value = []
                    mock_version.return_value = "v1.28.5"

                    assert health_monitor.baseline_snapshot is None

                    snapshot = health_monitor.take_snapshot()

                    assert health_monitor.baseline_snapshot is not None
                    assert health_monitor.baseline_snapshot.id == snapshot.id


class TestWeatherCaching:
    """Test weather state caching."""

    def test_weather_cache_ttl(self, health_monitor):
        """Test that weather cache respects TTL."""
        with patch.object(health_monitor, "take_snapshot") as mock_snapshot:
            with patch.object(health_monitor, "calculate_weather") as mock_weather:
                mock_snapshot.return_value = ClusterSnapshot(
                    id="snap-001",
                    timestamp=datetime.utcnow(),
                    cluster_name="test-cluster",
                    cluster_version="v1.28.5",
                    metrics=ClusterMetrics(
                        pod_failures=0,
                        cpu_usage=0.0,
                        memory_usage=0.0,
                        critical_events=0,
                        unhealthy_nodes=0,
                        failed_deployments=0,
                        failed_statefulsets=0,
                        failed_daemonsets=0,
                        pvc_issues=0,
                        ingress_issues=0,
                        argocd_apps_out_of_sync=0,
                        argocd_apps_degraded=0,
                    ),
                    cluster_tools=[],
                    total_pods=100,
                    total_nodes=5,
                    total_namespaces=10,
                    api_server_latency_ms=50.0,
                )
                mock_weather.return_value = "sunny"

                # First call should compute weather
                _ = health_monitor.get_current_weather()
                assert mock_snapshot.call_count == 1

                # Second call should use cache
                _ = health_monitor.get_current_weather()
                assert mock_snapshot.call_count == 1  # Not called again

                # Expire cache
                health_monitor.weather_cache_time = datetime.utcnow() - timedelta(seconds=400)

                # Third call should recompute
                _ = health_monitor.get_current_weather()
                assert mock_snapshot.call_count == 2  # Called again
