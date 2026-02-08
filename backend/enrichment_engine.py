"""
Enrichment Engine for gathering Kubernetes and AWS context.
"""
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import boto3
from kubernetes.client.exceptions import ApiException
from botocore.exceptions import ClientError, BotoCoreError

from query_router import EnrichmentPlan, QueryCategory
from credential_store import StoredCredentials
from utils.error_handler import handle_k8s_error, handle_aws_error, k8s_api_retry

logger = logging.getLogger(__name__)


@dataclass
class EnrichedContext:
    """Enriched context gathered from Kubernetes and AWS APIs."""
    k8sgpt_results: List[Dict[str, Any]] = field(default_factory=list)
    pod_data: Optional[Dict[str, Any]] = None
    deployment_data: Optional[Dict[str, Any]] = None
    service_data: Optional[Dict[str, Any]] = None
    node_data: Optional[Dict[str, Any]] = None
    storage_data: Optional[Dict[str, Any]] = None
    argocd_data: Optional[Dict[str, Any]] = None
    security_data: Optional[Dict[str, Any]] = None
    aws_data: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    
    def merge(self, other: 'EnrichedContext') -> None:
        """Merge another context into this one."""
        if other.k8sgpt_results:
            self.k8sgpt_results.extend(other.k8sgpt_results)
        if other.pod_data:
            self.pod_data = other.pod_data
        if other.deployment_data:
            self.deployment_data = other.deployment_data
        if other.service_data:
            self.service_data = other.service_data
        if other.node_data:
            self.node_data = other.node_data
        if other.storage_data:
            self.storage_data = other.storage_data
        if other.argocd_data:
            self.argocd_data = other.argocd_data
        if other.security_data:
            self.security_data = other.security_data
        if other.aws_data:
            self.aws_data = other.aws_data
        if other.errors:
            self.errors.extend(other.errors)


class EnrichmentEngine:
    """
    Main enrichment engine that coordinates all enrichment operations.
    
    Gathers relevant context from Kubernetes and AWS APIs based on query classification.
    Uses parallel execution for performance and graceful degradation for reliability.
    """
    
    def __init__(self, k8s_clients: Dict[str, Any], aws_creds: Optional[StoredCredentials] = None):
        """
        Initialize enrichment engine.
        
        Args:
            k8s_clients: Dictionary of Kubernetes API clients
            aws_creds: Optional AWS credentials for AWS enrichment
        """
        self.k8s = k8s_clients
        self.aws_creds = aws_creds
        self.timeout = 10  # seconds per enrichment
        self.aws_call_limit = 3  # Maximum AWS API calls per query
    
    def _get_namespace(self, plan: EnrichmentPlan) -> str:
        """
        Get namespace from plan or return default.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Namespace string
        """
        return plan.namespaces[0] if plan.namespaces else 'default'
    
    async def execute(self, plan: EnrichmentPlan) -> EnrichedContext:
        """
        Execute enrichment plan and gather all relevant context.
        
        Args:
            plan: Enrichment plan from query router
            
        Returns:
            EnrichedContext with gathered data and any errors
        """
        logger.info(f"Executing enrichment plan: {[c.value for c in plan.categories]}")
        
        tasks = []
        
        # Create tasks based on categories
        for category in plan.categories:
            if category == QueryCategory.POD_ISSUE:
                tasks.append(self._enrich_pods(plan))
            elif category == QueryCategory.DEPLOYMENT_STATUS:
                tasks.append(self._enrich_deployments(plan))
            elif category == QueryCategory.SERVICE_NETWORKING:
                tasks.append(self._enrich_services(plan))
            elif category == QueryCategory.NODE_HEALTH:
                tasks.append(self._enrich_nodes(plan))
            elif category == QueryCategory.STORAGE:
                tasks.append(self._enrich_storage(plan))
            elif category == QueryCategory.ARGOCD:
                tasks.append(self._enrich_argocd(plan))
            elif category == QueryCategory.SECURITY:
                tasks.append(self._enrich_security(plan))
            elif category == QueryCategory.GENERAL_HEALTH:
                tasks.append(self._enrich_general_health(plan))
            elif category == QueryCategory.KB_SEARCH:
                # KB_SEARCH doesn't need cluster enrichment, just K8sGPT results
                logger.info("KB_SEARCH category - skipping cluster enrichment")
        
        # If no enrichment tasks were created (e.g., only KB_SEARCH), add default enrichment
        if not tasks and QueryCategory.KB_SEARCH not in plan.categories:
            logger.info("No specific enrichment tasks - adding default cluster context")
            tasks.append(self._enrich_general_health(plan))
        
        # Always include K8sGPT results if requested
        if plan.include_k8sgpt_results:
            tasks.append(self._read_k8sgpt_results())
        
        # Add AWS enrichment if requested
        if plan.include_aws_context and self.aws_creds:
            tasks.append(self._enrich_aws(plan))
        
        # Execute all tasks in parallel with timeout protection
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error executing enrichment tasks: {e}")
            results = []
        
        # Combine results and handle errors
        context = EnrichedContext()
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = f"Enrichment task {i} failed: {str(result)}"
                logger.warning(error_msg)
                context.errors.append(error_msg)
            elif isinstance(result, dict):
                # Merge dict results into context
                if 'error' in result:
                    context.errors.append(result['error'])
                else:
                    # Determine which field to populate based on result keys
                    if 'pods' in result:
                        context.pod_data = result
                    elif 'deployments' in result:
                        context.deployment_data = result
                    elif 'services' in result:
                        context.service_data = result
                    elif 'nodes' in result:
                        context.node_data = result
                    elif 'pvcs' in result or 'storage' in result:
                        context.storage_data = result
                    elif 'applications' in result:
                        context.argocd_data = result
                    elif 'roles' in result or 'service_accounts' in result:
                        context.security_data = result
                    elif 'ec2_instances' in result or 'load_balancers' in result:
                        context.aws_data = result
                    elif 'k8sgpt_results' in result:
                        context.k8sgpt_results = result['k8sgpt_results']
        
        logger.info(f"Enrichment complete. Errors: {len(context.errors)}")
        return context

    
    async def _enrich_pods(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with pod status, events, and logs.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with pod data
        """
        try:
            core_v1 = self.k8s['core_v1']
            namespace = self._get_namespace(plan)
            
            pods_data = []
            
            # If specific pod names provided, get those pods
            if plan.resource_names:
                for pod_name in plan.resource_names:
                    try:
                        pod = core_v1.read_namespaced_pod(pod_name, namespace)
                        events = core_v1.list_namespaced_event(
                            namespace,
                            field_selector=f"involvedObject.name={pod_name}",
                            limit=50
                        )
                        
                        # Get logs (last 100 lines)
                        logs = ""
                        try:
                            logs = core_v1.read_namespaced_pod_log(
                                pod_name,
                                namespace,
                                tail_lines=100
                            )
                        except ApiException as e:
                            if e.status != 404:  # Pod might not have logs yet
                                logger.warning(f"Failed to get logs for pod {pod_name}: {e}")
                        
                        pods_data.append(self._format_pod_data(pod, events.items, logs, plan.time_range))
                        
                    except ApiException as e:
                        if e.status == 404:
                            return {
                                'error': f"Pod '{pod_name}' not found in namespace '{namespace}'. It may have been deleted."
                            }
                        elif e.status == 403:
                            return {
                                'error': f"You don't have permission to view pods in namespace '{namespace}'"
                            }
                        raise
            else:
                # Get all pods in namespace (limit to 20)
                pods = core_v1.list_namespaced_pod(namespace, limit=20)
                
                for pod in pods.items:
                    # Get events for this pod
                    events = core_v1.list_namespaced_event(
                        namespace,
                        field_selector=f"involvedObject.name={pod.metadata.name}",
                        limit=50
                    )
                    
                    pods_data.append(self._format_pod_data(pod, events.items, "", plan.time_range))
            
            summary = self._generate_pod_summary(pods_data)
            
            return {
                'pods': pods_data,
                'summary': summary
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching pods: {e}")
            if e.status == 403:
                return {'error': f"Permission denied: You don't have access to view pods in namespace '{namespace}'"}
            elif e.status == 408:
                return {'error': "Cluster is slow to respond. Showing partial pod data."}
            return {'error': f"Failed to retrieve pod data: {e.reason}"}
        except asyncio.TimeoutError:
            return {'error': "Timeout retrieving pod data. Cluster may be slow."}
        except Exception as e:
            logger.error(f"Error enriching pods: {e}")
            return {'error': f"Failed to retrieve pod data: {str(e)}"}
    
    def _format_pod_data(self, pod: Any, events: List[Any], logs: str, time_range: Optional[timedelta]) -> Dict[str, Any]:
        """Format pod data into structured dictionary."""
        # Filter events by time range if specified
        filtered_events = []
        if time_range:
            cutoff_time = datetime.now() - time_range
            for event in events:
                if event.last_timestamp and event.last_timestamp.replace(tzinfo=None) >= cutoff_time:
                    filtered_events.append(event)
        else:
            filtered_events = events[:10]  # Limit to 10 most recent
        
        # Extract container statuses
        containers = []
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                container_data = {
                    'name': container.name,
                    'ready': container.ready,
                    'restart_count': container.restart_count,
                    'state': 'unknown'
                }
                
                if container.state.running:
                    container_data['state'] = 'running'
                elif container.state.waiting:
                    container_data['state'] = 'waiting'
                    container_data['reason'] = container.state.waiting.reason
                    container_data['message'] = container.state.waiting.message
                elif container.state.terminated:
                    container_data['state'] = 'terminated'
                    container_data['reason'] = container.state.terminated.reason
                    container_data['exit_code'] = container.state.terminated.exit_code
                
                # Last termination info
                if container.last_state and container.last_state.terminated:
                    container_data['last_termination'] = {
                        'reason': container.last_state.terminated.reason,
                        'exit_code': container.last_state.terminated.exit_code,
                        'message': container.last_state.terminated.message
                    }
                
                containers.append(container_data)
        
        return {
            'name': pod.metadata.name,
            'namespace': pod.metadata.namespace,
            'phase': pod.status.phase,
            'restart_count': sum(c.restart_count for c in pod.status.container_statuses) if pod.status.container_statuses else 0,
            'containers': containers,
            'events': [
                {
                    'type': event.type,
                    'reason': event.reason,
                    'message': event.message,
                    'timestamp': event.last_timestamp.isoformat() if event.last_timestamp else None
                }
                for event in filtered_events
            ],
            'logs': logs[:1000] if logs else ""  # Limit log size
        }
    
    def _generate_pod_summary(self, pods_data: List[Dict[str, Any]]) -> str:
        """Generate summary of pod data."""
        if not pods_data:
            return "No pods found"
        
        total = len(pods_data)
        running = sum(1 for p in pods_data if p['phase'] == 'Running')
        pending = sum(1 for p in pods_data if p['phase'] == 'Pending')
        failed = sum(1 for p in pods_data if p['phase'] in ['Failed', 'CrashLoopBackOff'])
        
        return f"Found {total} pod(s): {running} running, {pending} pending, {failed} failed"

    
    async def _enrich_deployments(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with deployment status, replicas, and rollout information.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with deployment data
        """
        try:
            apps_v1 = self.k8s['apps_v1']
            core_v1 = self.k8s['core_v1']
            namespace = self._get_namespace(plan)
            
            deployments_data = []
            
            # If specific deployment names provided
            if plan.resource_names:
                for deploy_name in plan.resource_names:
                    try:
                        deployment = apps_v1.read_namespaced_deployment(deploy_name, namespace)
                        
                        # Get events
                        events = core_v1.list_namespaced_event(
                            namespace,
                            field_selector=f"involvedObject.name={deploy_name}",
                            limit=20
                        )
                        
                        deployments_data.append(self._format_deployment_data(deployment, events.items))
                        
                    except ApiException as e:
                        if e.status == 404:
                            return {'error': f"Deployment '{deploy_name}' not found in namespace '{namespace}'"}
                        elif e.status == 403:
                            return {'error': f"Permission denied: You don't have access to view deployments in namespace '{namespace}'"}
                        raise
            else:
                # Get all deployments in namespace
                deployments = apps_v1.list_namespaced_deployment(namespace, limit=20)
                
                for deployment in deployments.items:
                    events = core_v1.list_namespaced_event(
                        namespace,
                        field_selector=f"involvedObject.name={deployment.metadata.name}",
                        limit=20
                    )
                    deployments_data.append(self._format_deployment_data(deployment, events.items))
            
            return {
                'deployments': deployments_data,
                'summary': f"Found {len(deployments_data)} deployment(s)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching deployments: {e}")
            if e.status == 403:
                return {'error': "Permission denied: You don't have access to view deployments"}
            return {'error': f"Failed to retrieve deployment data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching deployments: {e}")
            return {'error': f"Failed to retrieve deployment data: {str(e)}"}
    
    def _format_deployment_data(self, deployment: Any, events: List[Any]) -> Dict[str, Any]:
        """Format deployment data into structured dictionary."""
        spec = deployment.spec
        status = deployment.status
        
        # Extract conditions
        conditions = []
        if status.conditions:
            for condition in status.conditions:
                conditions.append({
                    'type': condition.type,
                    'status': condition.status,
                    'reason': condition.reason if condition.reason else None,
                    'message': condition.message if condition.message else None
                })
        
        return {
            'name': deployment.metadata.name,
            'namespace': deployment.metadata.namespace,
            'replicas': {
                'desired': spec.replicas,
                'current': status.replicas if status.replicas else 0,
                'available': status.available_replicas if status.available_replicas else 0,
                'unavailable': status.unavailable_replicas if status.unavailable_replicas else 0,
                'updated': status.updated_replicas if status.updated_replicas else 0
            },
            'conditions': conditions,
            'strategy': spec.strategy.type if spec.strategy else 'Unknown',
            'events': [
                {
                    'type': event.type,
                    'reason': event.reason,
                    'message': event.message,
                    'timestamp': event.last_timestamp.isoformat() if event.last_timestamp else None
                }
                for event in events[:10]
            ]
        }

    
    async def _enrich_services(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with service endpoints, ingress rules, and networking info.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with service data
        """
        try:
            core_v1 = self.k8s['core_v1']
            networking_v1 = self.k8s['networking_v1']
            namespace = self._get_namespace(plan)
            
            services_data = []
            
            # If specific service names provided
            if plan.resource_names:
                for svc_name in plan.resource_names:
                    try:
                        service = core_v1.read_namespaced_service(svc_name, namespace)
                        
                        # Get endpoints
                        try:
                            endpoints = core_v1.read_namespaced_endpoints(svc_name, namespace)
                        except ApiException:
                            endpoints = None
                        
                        services_data.append(self._format_service_data(service, endpoints))
                        
                    except ApiException as e:
                        if e.status == 404:
                            return {'error': f"Service '{svc_name}' not found in namespace '{namespace}'"}
                        elif e.status == 403:
                            return {'error': f"Permission denied: You don't have access to view services in namespace '{namespace}'"}
                        raise
            else:
                # Get all services in namespace
                services = core_v1.list_namespaced_service(namespace, limit=20)
                
                for service in services.items:
                    try:
                        endpoints = core_v1.read_namespaced_endpoints(service.metadata.name, namespace)
                    except ApiException:
                        endpoints = None
                    
                    services_data.append(self._format_service_data(service, endpoints))
            
            # Get ingresses
            ingresses_data = []
            try:
                ingresses = networking_v1.list_namespaced_ingress(namespace, limit=20)
                for ingress in ingresses.items:
                    ingresses_data.append(self._format_ingress_data(ingress))
            except ApiException as e:
                logger.warning(f"Failed to get ingresses: {e}")
            
            return {
                'services': services_data,
                'ingresses': ingresses_data,
                'summary': f"Found {len(services_data)} service(s) and {len(ingresses_data)} ingress(es)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching services: {e}")
            if e.status == 403:
                return {'error': "Permission denied: You don't have access to view services"}
            return {'error': f"Failed to retrieve service data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching services: {e}")
            return {'error': f"Failed to retrieve service data: {str(e)}"}
    
    def _format_service_data(self, service: Any, endpoints: Any) -> Dict[str, Any]:
        """Format service data into structured dictionary."""
        # Extract endpoints
        ready_endpoints = []
        not_ready_endpoints = []
        
        if endpoints and endpoints.subsets:
            for subset in endpoints.subsets:
                # Ready addresses
                if subset.addresses:
                    for addr in subset.addresses:
                        for port in subset.ports:
                            ready_endpoints.append(f"{addr.ip}:{port.port}")
                
                # Not ready addresses
                if subset.not_ready_addresses:
                    for addr in subset.not_ready_addresses:
                        for port in subset.ports:
                            not_ready_endpoints.append(f"{addr.ip}:{port.port}")
        
        # Extract ports
        ports = []
        if service.spec.ports:
            for port in service.spec.ports:
                ports.append({
                    'port': port.port,
                    'target_port': str(port.target_port) if port.target_port else None,
                    'protocol': port.protocol
                })
        
        # External IPs
        external_ips = []
        if service.status.load_balancer and service.status.load_balancer.ingress:
            for ingress in service.status.load_balancer.ingress:
                if ingress.ip:
                    external_ips.append(ingress.ip)
                elif ingress.hostname:
                    external_ips.append(ingress.hostname)
        
        return {
            'name': service.metadata.name,
            'namespace': service.metadata.namespace,
            'type': service.spec.type,
            'cluster_ip': service.spec.cluster_ip,
            'external_ips': external_ips,
            'ports': ports,
            'endpoints': {
                'ready': ready_endpoints[:10],  # Limit to 10
                'not_ready': not_ready_endpoints[:10]
            }
        }
    
    def _format_ingress_data(self, ingress: Any) -> Dict[str, Any]:
        """Format ingress data into structured dictionary."""
        rules = []
        if ingress.spec.rules:
            for rule in ingress.spec.rules:
                if rule.http:
                    for path in rule.http.paths:
                        rules.append({
                            'host': rule.host if rule.host else '*',
                            'path': path.path if path.path else '/',
                            'backend': f"{path.backend.service.name}:{path.backend.service.port.number}"
                        })
        
        return {
            'name': ingress.metadata.name,
            'namespace': ingress.metadata.namespace,
            'rules': rules
        }

    
    async def _enrich_nodes(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with node conditions, capacity, and resource usage.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with node data
        """
        try:
            core_v1 = self.k8s['core_v1']
            
            nodes = core_v1.list_node()
            nodes_data = []
            
            for node in nodes.items:
                # Get pods on this node
                pods = core_v1.list_pod_for_all_namespaces(
                    field_selector=f"spec.nodeName={node.metadata.name}"
                )
                
                nodes_data.append(self._format_node_data(node, len(pods.items)))
            
            return {
                'nodes': nodes_data,
                'summary': f"Found {len(nodes_data)} node(s)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching nodes: {e}")
            if e.status == 403:
                return {'error': "Permission denied: You don't have access to view nodes"}
            return {'error': f"Failed to retrieve node data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching nodes: {e}")
            return {'error': f"Failed to retrieve node data: {str(e)}"}
    
    def _format_node_data(self, node: Any, pod_count: int) -> Dict[str, Any]:
        """Format node data into structured dictionary."""
        # Extract conditions
        conditions = []
        status = 'Unknown'
        if node.status.conditions:
            for condition in node.status.conditions:
                conditions.append({
                    'type': condition.type,
                    'status': condition.status
                })
                if condition.type == 'Ready':
                    status = 'Ready' if condition.status == 'True' else 'NotReady'
        
        # Extract taints
        taints = []
        if node.spec.taints:
            for taint in node.spec.taints:
                taints.append({
                    'key': taint.key,
                    'effect': taint.effect,
                    'value': taint.value if taint.value else None
                })
        
        return {
            'name': node.metadata.name,
            'status': status,
            'conditions': conditions,
            'capacity': {
                'cpu': node.status.capacity.get('cpu', 'unknown'),
                'memory': node.status.capacity.get('memory', 'unknown'),
                'pods': node.status.capacity.get('pods', 'unknown')
            },
            'allocatable': {
                'cpu': node.status.allocatable.get('cpu', 'unknown'),
                'memory': node.status.allocatable.get('memory', 'unknown'),
                'pods': node.status.allocatable.get('pods', 'unknown')
            },
            'pod_count': pod_count,
            'taints': taints
        }
    
    async def _enrich_storage(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with PVC status and storage information.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with storage data
        """
        try:
            core_v1 = self.k8s['core_v1']
            namespace = self._get_namespace(plan)
            
            # Get PVCs
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace, limit=20)
            pvcs_data = []
            
            for pvc in pvcs.items:
                pvcs_data.append({
                    'name': pvc.metadata.name,
                    'namespace': pvc.metadata.namespace,
                    'status': pvc.status.phase,
                    'volume_name': pvc.spec.volume_name if pvc.spec.volume_name else None,
                    'storage_class': pvc.spec.storage_class_name,
                    'capacity': pvc.status.capacity.get('storage') if pvc.status.capacity else None,
                    'access_modes': pvc.spec.access_modes
                })
            
            return {
                'pvcs': pvcs_data,
                'summary': f"Found {len(pvcs_data)} PVC(s)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching storage: {e}")
            if e.status == 403:
                return {'error': "Permission denied: You don't have access to view storage resources"}
            return {'error': f"Failed to retrieve storage data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching storage: {e}")
            return {'error': f"Failed to retrieve storage data: {str(e)}"}

    
    async def _enrich_argocd(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with ArgoCD Application CRD status.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with ArgoCD data
        """
        try:
            custom_objects = self.k8s['custom_objects']
            
            # Try to get ArgoCD applications
            try:
                applications = custom_objects.list_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace="argocd",
                    plural="applications"
                )
            except ApiException as e:
                if e.status == 404:
                    return {'error': "ArgoCD is not installed in this cluster"}
                elif e.status == 403:
                    return {'error': "Permission denied: You don't have access to view ArgoCD applications"}
                raise
            
            apps_data = []
            for app in applications.get('items', []):
                apps_data.append(self._format_argocd_app(app))
            
            return {
                'applications': apps_data,
                'summary': f"Found {len(apps_data)} ArgoCD application(s)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching ArgoCD: {e}")
            return {'error': f"Failed to retrieve ArgoCD data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching ArgoCD: {e}")
            return {'error': f"Failed to retrieve ArgoCD data: {str(e)}"}
    
    def _format_argocd_app(self, app: Dict[str, Any]) -> Dict[str, Any]:
        """Format ArgoCD application data."""
        metadata = app.get('metadata', {})
        spec = app.get('spec', {})
        status = app.get('status', {})
        
        # Extract sync status
        sync_status = status.get('sync', {}).get('status', 'Unknown')
        
        # Extract health status
        health_status = status.get('health', {}).get('status', 'Unknown')
        
        # Extract out-of-sync resources
        out_of_sync = []
        if sync_status == 'OutOfSync':
            for resource in status.get('resources', []):
                if resource.get('status') == 'OutOfSync':
                    out_of_sync.append({
                        'kind': resource.get('kind'),
                        'name': resource.get('name'),
                        'namespace': resource.get('namespace')
                    })
        
        return {
            'name': metadata.get('name'),
            'namespace': metadata.get('namespace'),
            'sync_status': sync_status,
            'health_status': health_status,
            'last_sync': status.get('operationState', {}).get('finishedAt'),
            'source': {
                'repo': spec.get('source', {}).get('repoURL'),
                'path': spec.get('source', {}).get('path'),
                'target_revision': spec.get('source', {}).get('targetRevision')
            },
            'out_of_sync_resources': out_of_sync[:10]  # Limit to 10
        }
    
    async def _enrich_security(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with RBAC roles and service account information.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with security data
        """
        try:
            rbac_v1 = self.k8s['rbac_v1']
            core_v1 = self.k8s['core_v1']
            namespace = self._get_namespace(plan)
            
            # Get roles
            roles = rbac_v1.list_namespaced_role(namespace, limit=20)
            roles_data = []
            for role in roles.items:
                roles_data.append({
                    'name': role.metadata.name,
                    'namespace': role.metadata.namespace,
                    'rules_count': len(role.rules) if role.rules else 0
                })
            
            # Get service accounts
            service_accounts = core_v1.list_namespaced_service_account(namespace, limit=20)
            sa_data = []
            for sa in service_accounts.items:
                sa_data.append({
                    'name': sa.metadata.name,
                    'namespace': sa.metadata.namespace,
                    'secrets_count': len(sa.secrets) if sa.secrets else 0
                })
            
            return {
                'roles': roles_data,
                'service_accounts': sa_data,
                'summary': f"Found {len(roles_data)} role(s) and {len(sa_data)} service account(s)"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching security: {e}")
            if e.status == 403:
                return {'error': "Permission denied: You don't have access to view RBAC resources"}
            return {'error': f"Failed to retrieve security data: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching security: {e}")
            return {'error': f"Failed to retrieve security data: {str(e)}"}
    
    async def _enrich_general_health(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with general cluster health information.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with general health data
        """
        try:
            # Get a summary of key resources
            core_v1 = self.k8s['core_v1']
            namespace = self._get_namespace(plan)
            
            # Get pod summary
            pods = core_v1.list_namespaced_pod(namespace, limit=50)
            pod_phases = {}
            for pod in pods.items:
                phase = pod.status.phase
                pod_phases[phase] = pod_phases.get(phase, 0) + 1
            
            # Get node summary
            nodes = core_v1.list_node()
            node_statuses = {'Ready': 0, 'NotReady': 0}
            for node in nodes.items:
                if node.status.conditions:
                    for condition in node.status.conditions:
                        if condition.type == 'Ready':
                            if condition.status == 'True':
                                node_statuses['Ready'] += 1
                            else:
                                node_statuses['NotReady'] += 1
            
            return {
                'pods': pod_phases,
                'nodes': node_statuses,
                'summary': f"Cluster health: {node_statuses['Ready']} ready nodes, {pod_phases.get('Running', 0)} running pods"
            }
            
        except ApiException as e:
            logger.error(f"K8s API error enriching general health: {e}")
            return {'error': f"Failed to retrieve cluster health: {e.reason}"}
        except Exception as e:
            logger.error(f"Error enriching general health: {e}")
            return {'error': f"Failed to retrieve cluster health: {str(e)}"}

    
    async def _enrich_aws(self, plan: EnrichmentPlan) -> Dict[str, Any]:
        """
        Enrich with AWS context (EC2, ELB, etc.) with 3-call limit.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Dictionary with AWS data
        """
        if not self.aws_creds:
            return {'error': "AWS credentials not available"}
        
        try:
            aws_data = {}
            calls_made = 0
            
            # Determine priority based on query category
            if QueryCategory.SERVICE_NETWORKING in plan.categories:
                # Priority 1: Load balancers
                if calls_made < self.aws_call_limit:
                    lb_data = await self._get_load_balancers()
                    if lb_data:
                        aws_data['load_balancers'] = lb_data
                        calls_made += 1
                
                # Priority 2: Security groups
                if calls_made < self.aws_call_limit:
                    sg_data = await self._get_security_groups()
                    if sg_data:
                        aws_data['security_groups'] = sg_data
                        calls_made += 1
            
            elif QueryCategory.NODE_HEALTH in plan.categories:
                # Priority 1: EC2 instances
                if calls_made < self.aws_call_limit:
                    ec2_data = await self._get_ec2_instances()
                    if ec2_data:
                        aws_data['ec2_instances'] = ec2_data
                        calls_made += 1
            
            aws_data['calls_made'] = calls_made
            return aws_data
            
        except (ClientError, BotoCoreError) as e:
            logger.error(f"AWS error during enrichment: {e}")
            return {'error': f"Failed to retrieve AWS data: {str(e)}"}
        except Exception as e:
            logger.error(f"Error enriching AWS: {e}")
            return {'error': f"Failed to retrieve AWS data: {str(e)}"}
    
    async def _get_load_balancers(self) -> Optional[List[Dict[str, Any]]]:
        """Get load balancer information."""
        try:
            elb_client = boto3.client(
                'elbv2',
                aws_access_key_id=self.aws_creds.access_key,
                aws_secret_access_key=self.aws_creds.secret_key,
                aws_session_token=self.aws_creds.session_token,
                region_name=self.aws_creds.region
            )
            
            response = elb_client.describe_load_balancers()
            lbs = []
            
            for lb in response.get('LoadBalancers', [])[:5]:  # Limit to 5
                lbs.append({
                    'name': lb.get('LoadBalancerName'),
                    'dns_name': lb.get('DNSName'),
                    'state': lb.get('State', {}).get('Code'),
                    'type': lb.get('Type'),
                    'scheme': lb.get('Scheme')
                })
            
            return lbs
            
        except Exception as e:
            logger.warning(f"Failed to get load balancers: {e}")
            return None
    
    async def _get_security_groups(self) -> Optional[List[Dict[str, Any]]]:
        """Get security group information."""
        try:
            ec2_client = boto3.client(
                'ec2',
                aws_access_key_id=self.aws_creds.access_key,
                aws_secret_access_key=self.aws_creds.secret_key,
                aws_session_token=self.aws_creds.session_token,
                region_name=self.aws_creds.region
            )
            
            response = ec2_client.describe_security_groups(MaxResults=10)
            sgs = []
            
            for sg in response.get('SecurityGroups', []):
                sgs.append({
                    'id': sg.get('GroupId'),
                    'name': sg.get('GroupName'),
                    'description': sg.get('Description'),
                    'vpc_id': sg.get('VpcId')
                })
            
            return sgs
            
        except Exception as e:
            logger.warning(f"Failed to get security groups: {e}")
            return None
    
    async def _get_ec2_instances(self) -> Optional[List[Dict[str, Any]]]:
        """Get EC2 instance information."""
        try:
            ec2_client = boto3.client(
                'ec2',
                aws_access_key_id=self.aws_creds.access_key,
                aws_secret_access_key=self.aws_creds.secret_key,
                aws_session_token=self.aws_creds.session_token,
                region_name=self.aws_creds.region
            )
            
            response = ec2_client.describe_instances(MaxResults=10)
            instances = []
            
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instances.append({
                        'id': instance.get('InstanceId'),
                        'type': instance.get('InstanceType'),
                        'state': instance.get('State', {}).get('Name'),
                        'private_ip': instance.get('PrivateIpAddress'),
                        'public_ip': instance.get('PublicIpAddress')
                    })
            
            return instances
            
        except Exception as e:
            logger.warning(f"Failed to get EC2 instances: {e}")
            return None
    
    async def _read_k8sgpt_results(self) -> Dict[str, Any]:
        """
        Read K8sGPT Result CRDs from the cluster.
        
        Returns:
            Dictionary with K8sGPT results
        """
        try:
            custom_objects = self.k8s['custom_objects']
            
            # Try to get K8sGPT results
            try:
                results = custom_objects.list_cluster_custom_object(
                    group="core.k8sgpt.ai",
                    version="v1alpha1",
                    plural="results"
                )
            except ApiException as e:
                if e.status == 404:
                    logger.info("K8sGPT is not installed in this cluster")
                    return {'k8sgpt_results': []}
                elif e.status == 403:
                    logger.warning("Permission denied to read K8sGPT results")
                    return {'k8sgpt_results': []}
                raise
            
            k8sgpt_data = []
            for result in results.get('items', []):
                k8sgpt_data.append(self._format_k8sgpt_result(result))
            
            logger.info(f"Retrieved {len(k8sgpt_data)} K8sGPT result(s)")
            return {'k8sgpt_results': k8sgpt_data}
            
        except ApiException as e:
            logger.error(f"K8s API error reading K8sGPT results: {e}")
            return {'k8sgpt_results': []}
        except Exception as e:
            logger.error(f"Error reading K8sGPT results: {e}")
            return {'k8sgpt_results': []}
    
    def _format_k8sgpt_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format K8sGPT result data into structured dictionary.
        
        Parses CRD structure to extract:
        - name: Result CRD name
        - kind: Resource kind (Pod, Deployment, etc.)
        - namespace: Resource namespace
        - severity: Issue severity (low, medium, high)
        - problem: Problem description
        - solution: Suggested solution
        - analyzer: K8sGPT analyzer name
        - timestamp: Result creation time
        - details: Additional metadata
        
        Args:
            result: K8sGPT Result CRD object
            
        Returns:
            Formatted result dictionary
        """
        metadata = result.get('metadata', {})
        spec = result.get('spec', {})
        status = result.get('status', {})
        
        # Extract basic info
        kind = spec.get('kind', 'Unknown')
        resource_name = spec.get('name', 'Unknown')
        
        # Extract error details - K8sGPT stores issues in the 'error' field
        error_list = spec.get('error', [])
        
        # Parse problem and solution from error list
        # K8sGPT typically formats errors as text descriptions
        problem = spec.get('details', '')
        solution = ''
        
        if isinstance(error_list, list) and error_list:
            # Combine error messages into problem description
            if not problem:
                problem = ' '.join(str(e) for e in error_list)
            # K8sGPT may provide solutions in the error text
            # Look for solution indicators
            for error_text in error_list:
                if isinstance(error_text, str) and ('solution' in error_text.lower() or 'fix' in error_text.lower()):
                    solution = error_text
                    break
        
        # Determine severity based on error content and kind
        # Default to 'medium' if not specified
        severity = 'medium'
        problem_lower = problem.lower()
        
        # High severity indicators
        if any(indicator in problem_lower for indicator in [
            'crashloopbackoff', 'imagepullbackoff', 'oomkilled', 
            'failed', 'error', 'critical', 'down', 'unavailable'
        ]):
            severity = 'high'
        # Low severity indicators
        elif any(indicator in problem_lower for indicator in [
            'warning', 'pending', 'info', 'notice'
        ]):
            severity = 'low'
        
        # Extract namespace - may be in metadata or spec
        namespace = metadata.get('namespace', spec.get('namespace', 'default'))
        
        # Extract analyzer name - K8sGPT uses 'backend' field
        analyzer = spec.get('backend', 'Unknown')
        
        # Extract timestamp - use creation timestamp from metadata
        timestamp = metadata.get('creationTimestamp', '')
        if timestamp:
            try:
                # Parse ISO format timestamp
                from datetime import datetime
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                # Keep as string if parsing fails
                pass
        
        return {
            'name': metadata.get('name', 'unknown'),
            'kind': kind,
            'namespace': namespace,
            'severity': severity,
            'problem': problem if problem else 'No problem description available',
            'solution': solution if solution else 'No solution provided',
            'analyzer': analyzer,
            'timestamp': timestamp,
            'details': {
                'resource_name': resource_name,
                'error': error_list,
                'backend': spec.get('backend', 'Unknown')
            }
        }
