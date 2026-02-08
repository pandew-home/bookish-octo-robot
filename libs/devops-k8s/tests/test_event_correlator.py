"""Tests for EventCorrelator class."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from kubernetes.client.rest import ApiException

from devops_k8s.event_correlator import (
    EventCorrelator,
    EventTimeline,
    K8sEvent,
    ResourceDependency,
)


@pytest.fixture
def mock_k8s_client():
    """Create a mock Kubernetes client."""
    with patch("devops_k8s.event_correlator.K8sClient") as mock:
        yield mock.return_value


@pytest.fixture
def mock_core_api():
    """Create a mock CoreV1Api."""
    with patch("devops_k8s.event_correlator.client.CoreV1Api") as mock:
        yield mock.return_value


@pytest.fixture
def event_correlator(mock_k8s_client, mock_core_api):
    """Create an EventCorrelator instance with mocked clients."""
    correlator = EventCorrelator()
    correlator.client = mock_k8s_client
    correlator.v1 = mock_core_api
    return correlator


class TestGetEventTimeline:
    """Tests for get_event_timeline method."""

    def test_get_event_timeline_returns_events_for_pod(self, event_correlator, mock_core_api):
        """Test getting event timeline for a pod."""
        # Create mock events
        now = datetime.utcnow()
        mock_event1 = Mock()
        mock_event1.metadata.name = "pod-event-1"
        mock_event1.metadata.namespace = "default"
        mock_event1.involved_object.name = "test-pod"
        mock_event1.involved_object.kind = "Pod"
        mock_event1.involved_object.uid = "uid-1"
        mock_event1.reason = "Started"
        mock_event1.message = "Pod started successfully"
        mock_event1.last_timestamp = now
        mock_event1.first_timestamp = now - timedelta(seconds=10)
        mock_event1.count = 1
        mock_event1.type = "Normal"

        mock_event2 = Mock()
        mock_event2.metadata.name = "pod-event-2"
        mock_event2.metadata.namespace = "default"
        mock_event2.involved_object.name = "test-pod"
        mock_event2.involved_object.kind = "Pod"
        mock_event2.involved_object.uid = "uid-1"
        mock_event2.reason = "Ready"
        mock_event2.message = "Pod is ready"
        mock_event2.last_timestamp = now + timedelta(seconds=5)
        mock_event2.first_timestamp = now + timedelta(seconds=5)
        mock_event2.count = 1
        mock_event2.type = "Normal"

        # Mock the list_namespaced_event call
        mock_events_list = Mock()
        mock_events_list.items = [mock_event1, mock_event2]
        mock_core_api.list_namespaced_event.return_value = mock_events_list

        # Get timeline
        timeline = event_correlator.get_event_timeline(
            resource_name="test-pod",
            namespace="default",
            resource_kind="Pod",
            hours_back=24
        )

        # Verify results
        assert timeline.resource_kind == "Pod"
        assert timeline.resource_name == "test-pod"
        assert timeline.resource_namespace == "default"
        assert len(timeline.events) == 2
        assert timeline.events[0].reason == "Started"
        assert timeline.events[1].reason == "Ready"
        assert timeline.timeline_start is not None
        assert timeline.timeline_end is not None

    def test_get_event_timeline_filters_by_time(self, event_correlator, mock_core_api):
        """Test that get_event_timeline filters events by time."""
        now = datetime.utcnow()
        old_time = now - timedelta(hours=48)

        # Create old event (should be filtered out)
        mock_old_event = Mock()
        mock_old_event.metadata.name = "old-event"
        mock_old_event.metadata.namespace = "default"
        mock_old_event.involved_object.name = "test-pod"
        mock_old_event.involved_object.kind = "Pod"
        mock_old_event.involved_object.uid = "uid-1"
        mock_old_event.reason = "OldReason"
        mock_old_event.message = "Old event"
        mock_old_event.last_timestamp = old_time
        mock_old_event.first_timestamp = old_time
        mock_old_event.count = 1
        mock_old_event.type = "Normal"

        # Create recent event (should be included)
        mock_recent_event = Mock()
        mock_recent_event.metadata.name = "recent-event"
        mock_recent_event.metadata.namespace = "default"
        mock_recent_event.involved_object.name = "test-pod"
        mock_recent_event.involved_object.kind = "Pod"
        mock_recent_event.involved_object.uid = "uid-1"
        mock_recent_event.reason = "RecentReason"
        mock_recent_event.message = "Recent event"
        mock_recent_event.last_timestamp = now
        mock_recent_event.first_timestamp = now
        mock_recent_event.count = 1
        mock_recent_event.type = "Normal"

        mock_events_list = Mock()
        mock_events_list.items = [mock_old_event, mock_recent_event]
        mock_core_api.list_namespaced_event.return_value = mock_events_list

        # Get timeline with 24 hour lookback
        timeline = event_correlator.get_event_timeline(
            resource_name="test-pod",
            namespace="default",
            resource_kind="Pod",
            hours_back=24
        )

        # Only recent event should be included
        assert len(timeline.events) == 1
        assert timeline.events[0].reason == "RecentReason"

    def test_get_event_timeline_handles_api_exception(self, event_correlator, mock_core_api):
        """Test that get_event_timeline handles API exceptions."""
        mock_core_api.list_namespaced_event.side_effect = ApiException(500, "API Error")

        with pytest.raises(Exception) as exc_info:
            event_correlator.get_event_timeline(
                resource_name="test-pod",
                namespace="default",
                resource_kind="Pod"
            )

        assert "Failed to get events" in str(exc_info.value)


class TestTraceDependencyChain:
    """Tests for trace_dependency_chain method."""

    def test_trace_pod_dependencies(self, event_correlator, mock_k8s_client):
        """Test tracing dependencies for a pod."""
        # Create mock pod with owner reference
        mock_pod = {
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
                "owner_references": [
                    {
                        "kind": "ReplicaSet",
                        "name": "test-rs",
                        "uid": "rs-uid"
                    }
                ]
            },
            "spec": {
                "volumes": [
                    {
                        "name": "config",
                        "configMap": {"name": "app-config"}
                    },
                    {
                        "name": "secret",
                        "secret": {"secretName": "app-secret"}
                    },
                    {
                        "name": "data",
                        "persistentVolumeClaim": {"claimName": "app-pvc"}
                    }
                ],
                "containers": [
                    {
                        "name": "app",
                        "image": "app:latest"
                    }
                ],
                "initContainers": []
            }
        }

        mock_k8s_client.get_pod.return_value = mock_pod

        # Mock ReplicaSet to Deployment tracing
        with patch.object(
            event_correlator, 
            "_trace_replicaset_to_deployment",
            return_value=[
                ResourceDependency(
                    source_kind="ReplicaSet",
                    source_name="test-rs",
                    source_namespace="default",
                    target_kind="Deployment",
                    target_name="test-deployment",
                    target_namespace="default",
                    dependency_type="owner"
                )
            ]
        ):
            dependencies = event_correlator.trace_dependency_chain(
                resource_name="test-pod",
                namespace="default",
                resource_kind="Pod"
            )

        # Verify dependencies
        assert len(dependencies) >= 4  # ReplicaSet, Deployment, ConfigMap, Secret, PVC
        
        # Check for ReplicaSet owner
        rs_deps = [d for d in dependencies if d.target_kind == "ReplicaSet"]
        assert len(rs_deps) == 1
        assert rs_deps[0].target_name == "test-rs"
        
        # Check for ConfigMap reference
        cm_deps = [d for d in dependencies if d.target_kind == "ConfigMap"]
        assert len(cm_deps) == 1
        assert cm_deps[0].target_name == "app-config"
        
        # Check for Secret reference
        secret_deps = [d for d in dependencies if d.target_kind == "Secret"]
        assert len(secret_deps) == 1
        assert secret_deps[0].target_name == "app-secret"
        
        # Check for PVC reference
        pvc_deps = [d for d in dependencies if d.target_kind == "PersistentVolumeClaim"]
        assert len(pvc_deps) == 1
        assert pvc_deps[0].target_name == "app-pvc"

    def test_trace_pod_with_istio_sidecar(self, event_correlator, mock_k8s_client):
        """Test tracing dependencies for a pod with Istio sidecar."""
        mock_pod = {
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
                "owner_references": []
            },
            "spec": {
                "volumes": [],
                "containers": [
                    {
                        "name": "app",
                        "image": "app:latest"
                    },
                    {
                        "name": "istio-proxy",
                        "image": "istio/proxyv2:1.14.0"
                    }
                ],
                "initContainers": []
            }
        }

        mock_k8s_client.get_pod.return_value = mock_pod

        dependencies = event_correlator.trace_dependency_chain(
            resource_name="test-pod",
            namespace="default",
            resource_kind="Pod"
        )

        # Check for service mesh dependency
        mesh_deps = [d for d in dependencies if d.dependency_type == "service_mesh"]
        assert len(mesh_deps) == 1
        assert mesh_deps[0].target_name == "Istio"

    def test_trace_deployment_dependencies(self, event_correlator, mock_k8s_client):
        """Test tracing dependencies for a deployment."""
        # Create mock ReplicaSets
        mock_rs = Mock()
        mock_rs.to_dict.return_value = {
            "metadata": {
                "name": "test-deployment-abc123",
                "namespace": "default",
                "owner_references": [
                    {
                        "kind": "Deployment",
                        "name": "test-deployment",
                        "uid": "deploy-uid"
                    }
                ]
            }
        }

        # Create mock Pods
        mock_pod = Mock()
        mock_pod.to_dict.return_value = {
            "metadata": {
                "name": "test-deployment-abc123-xyz",
                "namespace": "default",
                "owner_references": [
                    {
                        "kind": "ReplicaSet",
                        "name": "test-deployment-abc123",
                        "uid": "rs-uid"
                    }
                ]
            }
        }

        mock_k8s_client.get_deployment.return_value = {
            "metadata": {"name": "test-deployment"},
            "spec": {}
        }
        
        mock_replicasets_list = Mock()
        mock_replicasets_list.items = [mock_rs]
        mock_k8s_client.apps_v1.list_namespaced_replica_set.return_value = mock_replicasets_list
        
        mock_pods_list = [mock_pod]
        mock_k8s_client.list_pods.return_value = mock_pods_list

        dependencies = event_correlator.trace_dependency_chain(
            resource_name="test-deployment",
            namespace="default",
            resource_kind="Deployment"
        )

        # Verify dependencies
        assert len(dependencies) >= 2  # ReplicaSet and Pod
        
        # Check for ReplicaSet dependency
        rs_deps = [d for d in dependencies if d.target_kind == "ReplicaSet"]
        assert len(rs_deps) == 1
        
        # Check for Pod dependency
        pod_deps = [d for d in dependencies if d.target_kind == "Pod"]
        assert len(pod_deps) == 1


class TestCorrelateEvents:
    """Tests for correlate_events method."""

    def test_correlate_events_includes_related_resources(self, event_correlator):
        """Test that correlate_events includes events from related resources."""
        # Mock get_event_timeline to return events
        mock_timeline = EventTimeline(
            resource_kind="Pod",
            resource_name="test-pod",
            resource_namespace="default",
            events=[
                K8sEvent(
                    name="event-1",
                    namespace="default",
                    resource_kind="Pod",
                    resource_name="test-pod",
                    reason="Started",
                    message="Pod started",
                    timestamp=datetime.utcnow(),
                    count=1,
                    type="Normal",
                    first_timestamp=datetime.utcnow(),
                    last_timestamp=datetime.utcnow(),
                    involved_object_uid="uid-1"
                )
            ]
        )

        # Mock trace_dependency_chain
        mock_dependencies = [
            ResourceDependency(
                source_kind="Pod",
                source_name="test-pod",
                source_namespace="default",
                target_kind="ReplicaSet",
                target_name="test-rs",
                target_namespace="default",
                dependency_type="owner"
            )
        ]

        with patch.object(
            event_correlator,
            "get_event_timeline",
            return_value=mock_timeline
        ), patch.object(
            event_correlator,
            "trace_dependency_chain",
            return_value=mock_dependencies
        ), patch.object(
            event_correlator,
            "_get_resource_data",
            return_value={"metadata": {"name": "test-rs"}, "status": {}}
        ):
            timeline = event_correlator.correlate_events(
                resource_name="test-pod",
                namespace="default",
                resource_kind="Pod"
            )

        # Verify correlated timeline
        assert timeline.resource_kind == "Pod"
        assert len(timeline.dependencies) == 1
        assert len(timeline.related_resources) >= 1


class TestEventTimeline:
    """Tests for EventTimeline data structure."""

    def test_event_timeline_initialization(self):
        """Test EventTimeline initialization."""
        timeline = EventTimeline(
            resource_kind="Pod",
            resource_name="test-pod",
            resource_namespace="default"
        )

        assert timeline.resource_kind == "Pod"
        assert timeline.resource_name == "test-pod"
        assert timeline.resource_namespace == "default"
        assert timeline.events == []
        assert timeline.dependencies == []
        assert timeline.related_resources == []

    def test_event_timeline_with_events(self):
        """Test EventTimeline with events."""
        now = datetime.utcnow()
        event = K8sEvent(
            name="test-event",
            namespace="default",
            resource_kind="Pod",
            resource_name="test-pod",
            reason="Started",
            message="Pod started",
            timestamp=now,
            count=1,
            type="Normal",
            first_timestamp=now,
            last_timestamp=now,
            involved_object_uid="uid-1"
        )

        timeline = EventTimeline(
            resource_kind="Pod",
            resource_name="test-pod",
            resource_namespace="default",
            events=[event]
        )

        assert len(timeline.events) == 1
        assert timeline.events[0].reason == "Started"


class TestResourceDependency:
    """Tests for ResourceDependency data structure."""

    def test_resource_dependency_initialization(self):
        """Test ResourceDependency initialization."""
        dep = ResourceDependency(
            source_kind="Pod",
            source_name="test-pod",
            source_namespace="default",
            target_kind="ReplicaSet",
            target_name="test-rs",
            target_namespace="default",
            dependency_type="owner"
        )

        assert dep.source_kind == "Pod"
        assert dep.target_kind == "ReplicaSet"
        assert dep.dependency_type == "owner"

    def test_resource_dependency_with_metadata(self):
        """Test ResourceDependency with metadata."""
        dep = ResourceDependency(
            source_kind="Pod",
            source_name="test-pod",
            source_namespace="default",
            target_kind="ConfigMap",
            target_name="app-config",
            target_namespace="default",
            dependency_type="reference",
            metadata={"volume_name": "config"}
        )

        assert dep.metadata["volume_name"] == "config"
