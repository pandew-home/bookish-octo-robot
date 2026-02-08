"""Event correlation and dependency analysis for Kubernetes resources."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
from kubernetes import client
from kubernetes.client.rest import ApiException

from devops_k8s.client import K8sClient


@dataclass
class K8sEvent:
    """Kubernetes event with metadata."""

    name: str
    namespace: str
    resource_kind: str
    resource_name: str
    reason: str
    message: str
    timestamp: datetime
    count: int
    type: str  # "Normal" | "Warning"
    first_timestamp: datetime
    last_timestamp: datetime
    involved_object_uid: str


@dataclass
class ResourceDependency:
    """Dependency relationship between resources."""

    source_kind: str
    source_name: str
    source_namespace: str
    target_kind: str
    target_name: str
    target_namespace: str
    dependency_type: str  # "owner", "selector", "reference", "service_mesh"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventTimeline:
    """Timeline of events for a resource and related resources."""

    resource_kind: str
    resource_name: str
    resource_namespace: str
    events: List[K8sEvent] = field(default_factory=list)
    related_resources: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[ResourceDependency] = field(default_factory=list)
    timeline_start: Optional[datetime] = None
    timeline_end: Optional[datetime] = None


class EventCorrelator:
    """Correlate events across Kubernetes resources and trace dependencies."""

    def __init__(self):
        """Initialize event correlator with Kubernetes client."""
        self.client = K8sClient()
        self.v1 = client.CoreV1Api()

    def get_event_timeline(
        self, 
        resource_name: str, 
        namespace: str, 
        resource_kind: str = "Pod",
        hours_back: int = 24
    ) -> EventTimeline:
        """Get events for a specific resource.

        Args:
            resource_name: Name of the resource
            namespace: Namespace of the resource
            resource_kind: Kind of resource (Pod, Deployment, etc.)
            hours_back: How many hours back to look for events

        Returns:
            EventTimeline with events for the resource
        """
        timeline = EventTimeline(
            resource_kind=resource_kind,
            resource_name=resource_name,
            resource_namespace=namespace
        )

        try:
            # Get events for the resource
            events = self.v1.list_namespaced_event(namespace)
            
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            
            for event in events.items:
                # Filter events for this resource
                if (event.involved_object.name == resource_name and 
                    event.involved_object.kind == resource_kind):
                    
                    # Parse event timestamps
                    event_time = event.last_timestamp or event.first_timestamp
                    if event_time and event_time.replace(tzinfo=None) > cutoff_time:
                        k8s_event = K8sEvent(
                            name=event.metadata.name,
                            namespace=event.metadata.namespace,
                            resource_kind=event.involved_object.kind,
                            resource_name=event.involved_object.name,
                            reason=event.reason,
                            message=event.message,
                            timestamp=event_time.replace(tzinfo=None) if event_time else datetime.utcnow(),
                            count=event.count or 1,
                            type=event.type,
                            first_timestamp=event.first_timestamp.replace(tzinfo=None) if event.first_timestamp else datetime.utcnow(),
                            last_timestamp=event.last_timestamp.replace(tzinfo=None) if event.last_timestamp else datetime.utcnow(),
                            involved_object_uid=event.involved_object.uid
                        )
                        timeline.events.append(k8s_event)
            
            # Sort events by timestamp
            timeline.events.sort(key=lambda e: e.timestamp)
            
            # Set timeline bounds
            if timeline.events:
                timeline.timeline_start = timeline.events[0].timestamp
                timeline.timeline_end = timeline.events[-1].timestamp
            
        except ApiException as e:
            raise Exception(f"Failed to get events for {resource_kind} {resource_name}: {e}")
        
        return timeline

    def correlate_events(
        self,
        resource_name: str,
        namespace: str,
        resource_kind: str = "Pod",
        hours_back: int = 24
    ) -> EventTimeline:
        """Build correlated timeline across related resources.

        For a Pod, this traces: Deployment → ReplicaSet → Pod
        For a Deployment, this traces: Deployment → ReplicaSets → Pods

        Args:
            resource_name: Name of the resource
            namespace: Namespace of the resource
            resource_kind: Kind of resource (Pod, Deployment, etc.)
            hours_back: How many hours back to look for events

        Returns:
            EventTimeline with correlated events across related resources
        """
        # Get initial timeline for the resource
        timeline = self.get_event_timeline(resource_name, namespace, resource_kind, hours_back)
        
        # Trace dependencies and collect related resources
        dependencies = self.trace_dependency_chain(resource_name, namespace, resource_kind)
        timeline.dependencies = dependencies
        
        # Collect events from all related resources
        all_events = list(timeline.events)
        related_resources_set: Set[tuple] = set()
        
        for dep in dependencies:
            # Add related resource info
            related_resources_set.add((dep.target_kind, dep.target_name, dep.target_namespace))
            
            # Get events for related resource
            try:
                related_timeline = self.get_event_timeline(
                    dep.target_name,
                    dep.target_namespace,
                    dep.target_kind,
                    hours_back
                )
                all_events.extend(related_timeline.events)
            except Exception:
                # Continue if we can't get events for a related resource
                pass
        
        # Add related resource details
        for kind, name, ns in related_resources_set:
            try:
                resource_data = self._get_resource_data(kind, name, ns)
                if resource_data:
                    timeline.related_resources.append({
                        "kind": kind,
                        "name": name,
                        "namespace": ns,
                        "status": resource_data.get("status", {}),
                        "metadata": resource_data.get("metadata", {})
                    })
            except Exception:
                # Continue if we can't get resource data
                pass
        
        # Sort all events chronologically
        all_events.sort(key=lambda e: e.timestamp)
        timeline.events = all_events
        
        # Update timeline bounds
        if timeline.events:
            timeline.timeline_start = timeline.events[0].timestamp
            timeline.timeline_end = timeline.events[-1].timestamp
        
        return timeline

    def trace_dependency_chain(
        self,
        resource_name: str,
        namespace: str,
        resource_kind: str = "Pod"
    ) -> List[ResourceDependency]:
        """Identify pod dependencies and ownership chain.

        Traces: Deployment → ReplicaSet → Pod
        Also identifies: ConfigMaps, Secrets, Services, PVCs used by the pod

        Args:
            resource_name: Name of the resource
            namespace: Namespace of the resource
            resource_kind: Kind of resource

        Returns:
            List of ResourceDependency objects representing the dependency chain
        """
        dependencies: List[ResourceDependency] = []
        
        try:
            if resource_kind == "Pod":
                # Get pod details
                pod = self.client.get_pod(resource_name, namespace)
                pod_dict = pod if isinstance(pod, dict) else pod.to_dict()
                
                # Check for owner references (ReplicaSet, StatefulSet, DaemonSet, etc.)
                owner_refs = pod_dict.get("metadata", {}).get("owner_references", [])
                for owner in owner_refs:
                    dep = ResourceDependency(
                        source_kind="Pod",
                        source_name=resource_name,
                        source_namespace=namespace,
                        target_kind=owner.get("kind"),
                        target_name=owner.get("name"),
                        target_namespace=namespace,
                        dependency_type="owner",
                        metadata={"uid": owner.get("uid")}
                    )
                    dependencies.append(dep)
                    
                    # If owner is ReplicaSet, trace to Deployment
                    if owner.get("kind") == "ReplicaSet":
                        deployment_deps = self._trace_replicaset_to_deployment(
                            owner.get("name"), namespace
                        )
                        dependencies.extend(deployment_deps)
                
                # Identify ConfigMaps and Secrets used by pod
                volumes = pod_dict.get("spec", {}).get("volumes", [])
                for volume in volumes:
                    if "configMap" in volume:
                        cm_name = volume["configMap"].get("name")
                        dep = ResourceDependency(
                            source_kind="Pod",
                            source_name=resource_name,
                            source_namespace=namespace,
                            target_kind="ConfigMap",
                            target_name=cm_name,
                            target_namespace=namespace,
                            dependency_type="reference"
                        )
                        dependencies.append(dep)
                    
                    if "secret" in volume:
                        secret_name = volume["secret"].get("secretName")
                        dep = ResourceDependency(
                            source_kind="Pod",
                            source_name=resource_name,
                            source_namespace=namespace,
                            target_kind="Secret",
                            target_name=secret_name,
                            target_namespace=namespace,
                            dependency_type="reference"
                        )
                        dependencies.append(dep)
                    
                    if "persistentVolumeClaim" in volume:
                        pvc_name = volume["persistentVolumeClaim"].get("claimName")
                        dep = ResourceDependency(
                            source_kind="Pod",
                            source_name=resource_name,
                            source_namespace=namespace,
                            target_kind="PersistentVolumeClaim",
                            target_name=pvc_name,
                            target_namespace=namespace,
                            dependency_type="reference"
                        )
                        dependencies.append(dep)
                
                # Identify Service mesh sidecars (Istio/Linkerd)
                containers = pod_dict.get("spec", {}).get("containers", [])
                init_containers = pod_dict.get("spec", {}).get("initContainers", [])
                
                for container in containers + init_containers:
                    image = container.get("image", "")
                    if "istio" in image.lower() or "envoy" in image.lower():
                        dep = ResourceDependency(
                            source_kind="Pod",
                            source_name=resource_name,
                            source_namespace=namespace,
                            target_kind="ServiceMesh",
                            target_name="Istio",
                            target_namespace=namespace,
                            dependency_type="service_mesh"
                        )
                        dependencies.append(dep)
                    elif "linkerd" in image.lower():
                        dep = ResourceDependency(
                            source_kind="Pod",
                            source_name=resource_name,
                            source_namespace=namespace,
                            target_kind="ServiceMesh",
                            target_name="Linkerd",
                            target_namespace=namespace,
                            dependency_type="service_mesh"
                        )
                        dependencies.append(dep)
            
            elif resource_kind == "Deployment":
                # Find ReplicaSets owned by this Deployment
                replicasets = self.client.apps_v1.list_namespaced_replica_set(namespace)
                for rs in replicasets.items:
                    rs_dict = rs.to_dict()
                    owner_refs = rs_dict.get("metadata", {}).get("owner_references", [])
                    for owner in owner_refs:
                        if owner.get("kind") == "Deployment" and owner.get("name") == resource_name:
                            dep = ResourceDependency(
                                source_kind="Deployment",
                                source_name=resource_name,
                                source_namespace=namespace,
                                target_kind="ReplicaSet",
                                target_name=rs_dict["metadata"]["name"],
                                target_namespace=namespace,
                                dependency_type="owner"
                            )
                            dependencies.append(dep)
                            
                            # Find Pods owned by this ReplicaSet
                            pods = self.client.list_pods(namespace)
                            for pod in pods:
                                pod_dict = pod if isinstance(pod, dict) else pod.to_dict()
                                pod_owner_refs = pod_dict.get("metadata", {}).get("owner_references", [])
                                for pod_owner in pod_owner_refs:
                                    if (pod_owner.get("kind") == "ReplicaSet" and 
                                        pod_owner.get("name") == rs_dict["metadata"]["name"]):
                                        pod_dep = ResourceDependency(
                                            source_kind="ReplicaSet",
                                            source_name=rs_dict["metadata"]["name"],
                                            source_namespace=namespace,
                                            target_kind="Pod",
                                            target_name=pod_dict["metadata"]["name"],
                                            target_namespace=namespace,
                                            dependency_type="owner"
                                        )
                                        dependencies.append(pod_dep)
        
        except Exception as e:
            raise Exception(f"Failed to trace dependencies for {resource_kind} {resource_name}: {e}")
        
        return dependencies

    def _trace_replicaset_to_deployment(
        self, 
        replicaset_name: str, 
        namespace: str
    ) -> List[ResourceDependency]:
        """Trace ReplicaSet to its owning Deployment.

        Args:
            replicaset_name: Name of the ReplicaSet
            namespace: Namespace of the ReplicaSet

        Returns:
            List of dependencies from ReplicaSet to Deployment
        """
        dependencies: List[ResourceDependency] = []
        
        try:
            rs = self.client.apps_v1.read_namespaced_replica_set(replicaset_name, namespace)
            rs_dict = rs.to_dict()
            
            owner_refs = rs_dict.get("metadata", {}).get("owner_references", [])
            for owner in owner_refs:
                if owner.get("kind") == "Deployment":
                    dep = ResourceDependency(
                        source_kind="ReplicaSet",
                        source_name=replicaset_name,
                        source_namespace=namespace,
                        target_kind="Deployment",
                        target_name=owner.get("name"),
                        target_namespace=namespace,
                        dependency_type="owner",
                        metadata={"uid": owner.get("uid")}
                    )
                    dependencies.append(dep)
        except ApiException:
            pass
        
        return dependencies

    def _get_resource_data(
        self, 
        kind: str, 
        name: str, 
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Get resource data by kind and name.

        Args:
            kind: Resource kind (Pod, Deployment, etc.)
            name: Resource name
            namespace: Resource namespace

        Returns:
            Resource data as dictionary or None if not found
        """
        try:
            if kind == "Pod":
                return self.client.get_pod(name, namespace)
            elif kind == "Deployment":
                return self.client.get_deployment(name, namespace)
            elif kind == "ReplicaSet":
                rs = self.client.apps_v1.read_namespaced_replica_set(name, namespace)
                return rs.to_dict()
            elif kind == "Service":
                return self.client.get_service(name, namespace)
            elif kind == "ConfigMap":
                cm = self.v1.read_namespaced_config_map(name, namespace)
                return cm.to_dict()
            elif kind == "Secret":
                secret = self.v1.read_namespaced_secret(name, namespace)
                return secret.to_dict()
            elif kind == "PersistentVolumeClaim":
                pvc = self.v1.read_namespaced_persistent_volume_claim(name, namespace)
                return pvc.to_dict()
        except ApiException:
            return None
        
        return None
