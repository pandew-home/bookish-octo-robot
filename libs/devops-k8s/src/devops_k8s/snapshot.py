"""Cluster snapshot models and comparison logic."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ClusterToolInfo:
    """Information about a detected cluster tool."""

    name: str
    version: str
    category: str
    deployment_age_days: int
    status: str  # "healthy" | "degraded" | "unknown"


@dataclass
class ClusterMetrics:
    """Current cluster metrics snapshot."""

    pod_failures: int
    cpu_usage: float  # percentage 0-100
    memory_usage: float  # percentage 0-100
    critical_events: int
    unhealthy_nodes: int
    failed_deployments: int
    failed_statefulsets: int
    failed_daemonsets: int
    pvc_issues: int
    ingress_issues: int
    argocd_apps_out_of_sync: int
    argocd_apps_degraded: int


@dataclass
class ClusterSnapshot:
    """Complete cluster state snapshot at a point in time."""

    id: str
    timestamp: datetime
    cluster_name: str
    cluster_version: str
    metrics: ClusterMetrics
    cluster_tools: List[ClusterToolInfo]
    total_pods: int
    total_nodes: int
    total_namespaces: int
    api_server_latency_ms: float
    previous_snapshot_id: Optional[str] = None
    snapshot_sequence: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotDiff:
    """Differences between two cluster snapshots."""

    snapshot1_id: str
    snapshot2_id: str
    timestamp: datetime
    time_delta_seconds: float
    new_pod_failures: int
    resolved_pod_failures: int
    cpu_usage_increase: float  # percentage points
    memory_usage_increase: float  # percentage points
    new_critical_events: int
    new_unhealthy_nodes: int
    new_failed_deployments: int
    new_failed_statefulsets: int
    new_failed_daemonsets: int
    new_pvc_issues: int
    new_ingress_issues: int
    new_argocd_out_of_sync: int
    new_argocd_degraded: int
    tools_added: List[ClusterToolInfo] = field(default_factory=list)
    tools_removed: List[ClusterToolInfo] = field(default_factory=list)
    tools_version_changed: List[tuple] = field(default_factory=list)  # (tool_name, old_version, new_version)
