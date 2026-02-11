"""
API endpoints for cluster weather and K8sGPT results.

This module provides endpoints for:
- Weather monitoring (cluster health visualization)
- K8sGPT Result CRD listing and retrieval

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 12.1, 12.2, 12.5
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from api.credentials import get_session_id
from api.clusters import get_selected_cluster, get_k8s_clients_for_session
from k8sgpt_reader import K8sGPTReader, K8sGPTResult
from weather_calculator import WeatherCalculator, WeatherResponse, ClusterToolInfo
from kubernetes.client import CoreV1Api
from kubernetes.client.rest import ApiException
from utils.error_handler import handle_k8s_error, handle_generic_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["weather", "results"])


class WeatherResponseModel(BaseModel):
    """Response model for weather endpoint."""
    weather_state: str
    cluster_name: str
    cluster_version: str
    k8sgpt_result_count: int
    top_issues: List[Dict[str, Any]]
    cluster_tools: List[Dict[str, Any]]
    timestamp: str
    node_count: Optional[int] = None
    pod_summary: Optional[Dict[str, int]] = None


class WeatherDetailsResponse(BaseModel):
    """Response model for detailed weather endpoint."""
    weather_state: str
    cluster_name: str
    cluster_version: str
    k8sgpt_result_count: int
    all_results: List[Dict[str, Any]]
    cluster_tools: List[Dict[str, Any]]
    timestamp: str
    cluster_metadata: Dict[str, Any]


class ResultListResponse(BaseModel):
    """Response model for results list endpoint."""
    results: List[Dict[str, Any]]
    count: int
    filters_applied: Dict[str, Any]


class ResultDetailResponse(BaseModel):
    """Response model for single result detail endpoint."""
    result: Dict[str, Any]
    enrichment: Optional[Dict[str, Any]] = None


@router.get("/weather", response_model=WeatherResponseModel)
async def get_weather(session_id: str = Depends(get_session_id)):
    """
    Get cluster weather (health status) based on K8sGPT Results.
    
    This endpoint:
    1. Reads K8sGPT Result CRDs from the selected cluster
    2. Makes lightweight K8s API calls (node count, pod summary)
    3. Calculates weather state based on result severity and count
    4. Returns top 5 issues sorted by severity
    
    Weather states:
    - Sunny: 0 issues
    - Partly Cloudy: 1-2 low severity issues
    - Cloudy: 3-5 low severity OR 1-2 medium severity issues
    - Rainy: 6+ low severity OR 3+ medium severity OR 1 high severity issue
    - Stormy: 2+ high severity issues OR 10+ total issues
    
    Args:
        session_id: Session ID from header
        
    Returns:
        WeatherResponseModel with weather state and top issues
        
    Raises:
        HTTPException: If weather calculation fails
    """
    try:
        # Get selected cluster and K8s clients
        cluster = get_selected_cluster(session_id)
        k8s_clients = get_k8s_clients_for_session(session_id)
        
        cluster_name = cluster['name']
        cluster_version = cluster.get('version', 'unknown')
        
        logger.info(f"Calculating weather for cluster {cluster_name}")
        
        # Read K8sGPT Result CRDs
        custom_api = k8s_clients['custom_objects']
        k8sgpt_reader = K8sGPTReader(custom_api)
        
        try:
            results = await k8sgpt_reader.read_results()
            logger.info(f"Read {len(results)} K8sGPT Results from cluster {cluster_name}")
        except ApiException as e:
            if e.status == 404:
                # K8sGPT CRD not installed - return sunny weather
                logger.info(f"K8sGPT CRD not found in cluster {cluster_name} - assuming healthy")
                results = []
            else:
                # Other API errors
                error_msg = handle_k8s_error(e, "read K8sGPT Results")
                logger.error(f"Failed to read K8sGPT Results: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Unable to read K8sGPT Results: {error_msg}"
                )
        
        # Get lightweight cluster metadata
        core_api: CoreV1Api = k8s_clients['core_v1']
        
        # Get node count
        node_count = 0
        try:
            nodes = core_api.list_node()
            node_count = len(nodes.items)
        except Exception as e:
            logger.warning(f"Failed to get node count: {e}")
        
        # Get pod summary (count by status)
        pod_summary = {}
        try:
            pods = core_api.list_pod_for_all_namespaces()
            pod_summary = {
                'total': len(pods.items),
                'running': sum(1 for p in pods.items if p.status.phase == 'Running'),
                'pending': sum(1 for p in pods.items if p.status.phase == 'Pending'),
                'failed': sum(1 for p in pods.items if p.status.phase == 'Failed'),
                'succeeded': sum(1 for p in pods.items if p.status.phase == 'Succeeded'),
            }
        except Exception as e:
            logger.warning(f"Failed to get pod summary: {e}")
        
        # Get K8sGPT version (if available)
        cluster_tools = []
        try:
            # Try to get K8sGPT operator deployment
            apps_api = k8s_clients['apps_v1']
            deployments = apps_api.list_namespaced_deployment(namespace='k8sgpt-operator-system')
            for deployment in deployments.items:
                if 'k8sgpt' in deployment.metadata.name.lower():
                    # Extract version from image tag
                    containers = deployment.spec.template.spec.containers
                    if containers:
                        image = containers[0].image
                        version = image.split(':')[-1] if ':' in image else 'unknown'
                        cluster_tools.append(ClusterToolInfo(
                            name='k8sgpt-operator',
                            version=version,
                            status='running' if deployment.status.ready_replicas else 'degraded'
                        ))
        except Exception as e:
            logger.debug(f"Could not get K8sGPT operator info: {e}")
        
        # Calculate weather
        weather_calculator = WeatherCalculator()
        weather_response = weather_calculator.calculate_weather(
            results=results,
            cluster_name=cluster_name,
            cluster_version=cluster_version,
            cluster_tools=cluster_tools
        )
        
        # Convert to response model
        response_dict = weather_response.to_dict()
        response_dict['node_count'] = node_count
        response_dict['pod_summary'] = pod_summary
        
        logger.info(f"Weather calculated for {cluster_name}: {weather_response.weather_state.value}")
        
        return WeatherResponseModel(**response_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating weather: {e}")
        raise handle_generic_error(
            e,
            "calculating cluster weather",
            "Unable to calculate cluster health. Please verify cluster connectivity."
        )


@router.get("/weather/details", response_model=WeatherDetailsResponse)
async def get_weather_details(session_id: str = Depends(get_session_id)):
    """
    Get detailed cluster weather with all K8sGPT Results.
    
    This endpoint provides a comprehensive view of cluster health including:
    - All K8sGPT Result CRDs (not just top 5)
    - Detailed cluster metadata
    - Tool versions and status
    
    Args:
        session_id: Session ID from header
        
    Returns:
        WeatherDetailsResponse with all results and metadata
        
    Raises:
        HTTPException: If weather calculation fails
    """
    try:
        # Get selected cluster and K8s clients
        cluster = get_selected_cluster(session_id)
        k8s_clients = get_k8s_clients_for_session(session_id)
        
        cluster_name = cluster['name']
        cluster_version = cluster.get('version', 'unknown')
        
        logger.info(f"Getting detailed weather for cluster {cluster_name}")
        
        # Read K8sGPT Result CRDs
        custom_api = k8s_clients['custom_objects']
        k8sgpt_reader = K8sGPTReader(custom_api)
        
        try:
            results = await k8sgpt_reader.read_results()
            logger.info(f"Read {len(results)} K8sGPT Results from cluster {cluster_name}")
        except ApiException as e:
            if e.status == 404:
                # K8sGPT CRD not installed
                logger.info(f"K8sGPT CRD not found in cluster {cluster_name}")
                results = []
            else:
                error_msg = handle_k8s_error(e, "read K8sGPT Results")
                logger.error(f"Failed to read K8sGPT Results: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Unable to read K8sGPT Results: {error_msg}"
                )
        
        # Get cluster metadata
        core_api: CoreV1Api = k8s_clients['core_v1']
        
        cluster_metadata = {
            'name': cluster_name,
            'version': cluster_version,
            'endpoint': cluster.get('endpoint', 'unknown'),
            'region': cluster.get('region', 'unknown'),
            'status': cluster.get('status', 'unknown')
        }
        
        # Get node information
        try:
            nodes = core_api.list_node()
            cluster_metadata['node_count'] = len(nodes.items)
            cluster_metadata['nodes'] = [
                {
                    'name': node.metadata.name,
                    'status': 'Ready' if any(
                        c.type == 'Ready' and c.status == 'True'
                        for c in node.status.conditions
                    ) else 'NotReady',
                    'version': node.status.node_info.kubelet_version
                }
                for node in nodes.items
            ]
        except Exception as e:
            logger.warning(f"Failed to get node information: {e}")
            cluster_metadata['node_count'] = 0
            cluster_metadata['nodes'] = []
        
        # Get namespace count
        try:
            namespaces = core_api.list_namespace()
            cluster_metadata['namespace_count'] = len(namespaces.items)
        except Exception as e:
            logger.warning(f"Failed to get namespace count: {e}")
            cluster_metadata['namespace_count'] = 0
        
        # Get K8sGPT version
        cluster_tools = []
        try:
            apps_api = k8s_clients['apps_v1']
            deployments = apps_api.list_namespaced_deployment(namespace='k8sgpt-operator-system')
            for deployment in deployments.items:
                if 'k8sgpt' in deployment.metadata.name.lower():
                    containers = deployment.spec.template.spec.containers
                    if containers:
                        image = containers[0].image
                        version = image.split(':')[-1] if ':' in image else 'unknown'
                        cluster_tools.append(ClusterToolInfo(
                            name='k8sgpt-operator',
                            version=version,
                            status='running' if deployment.status.ready_replicas else 'degraded'
                        ))
        except Exception as e:
            logger.debug(f"Could not get K8sGPT operator info: {e}")
        
        # Calculate weather
        weather_calculator = WeatherCalculator()
        weather_response = weather_calculator.calculate_weather(
            results=results,
            cluster_name=cluster_name,
            cluster_version=cluster_version,
            cluster_tools=cluster_tools
        )
        
        # Convert all results to dict
        all_results = [result.to_dict() for result in results]
        
        return WeatherDetailsResponse(
            weather_state=weather_response.weather_state.value,
            cluster_name=cluster_name,
            cluster_version=cluster_version,
            k8sgpt_result_count=len(results),
            all_results=all_results,
            cluster_tools=[tool.to_dict() for tool in cluster_tools],
            timestamp=weather_response.timestamp.isoformat(),
            cluster_metadata=cluster_metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting detailed weather: {e}")
        raise handle_generic_error(
            e,
            "getting detailed cluster weather",
            "Unable to retrieve detailed cluster health. Please verify cluster connectivity."
        )


@router.get("/results", response_model=ResultListResponse)
async def list_results(
    session_id: str = Depends(get_session_id),
    severity: Optional[str] = Query(None, description="Filter by severity (low, medium, high)"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    kind: Optional[str] = Query(None, description="Filter by resource kind")
):
    """
    List all K8sGPT Result CRDs with optional filtering.
    
    This endpoint provides a filterable list of all K8sGPT diagnostic results
    for the selected cluster. Results can be filtered by:
    - Severity level (low, medium, high)
    - Namespace
    - Resource kind (Pod, Deployment, Service, etc.)
    
    Args:
        session_id: Session ID from header
        severity: Optional severity filter
        namespace: Optional namespace filter
        kind: Optional resource kind filter
        
    Returns:
        ResultListResponse with filtered results
        
    Raises:
        HTTPException: If result reading fails
    """
    try:
        # Get selected cluster and K8s clients
        cluster = get_selected_cluster(session_id)
        k8s_clients = get_k8s_clients_for_session(session_id)
        
        cluster_name = cluster['name']
        
        logger.info(f"Listing K8sGPT Results for cluster {cluster_name}")
        
        # Read K8sGPT Result CRDs
        custom_api = k8s_clients['custom_objects']
        k8sgpt_reader = K8sGPTReader(custom_api)
        
        try:
            # Read results with optional namespace filter
            results = await k8sgpt_reader.read_results(
                namespace=namespace,
                severity_filter=severity
            )
            logger.info(f"Read {len(results)} K8sGPT Results from cluster {cluster_name}")
        except ApiException as e:
            if e.status == 404:
                # K8sGPT CRD not installed
                logger.info(f"K8sGPT CRD not found in cluster {cluster_name}")
                results = []
            else:
                error_msg = handle_k8s_error(e, "read K8sGPT Results")
                logger.error(f"Failed to read K8sGPT Results: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Unable to read K8sGPT Results: {error_msg}"
                )
        
        # Apply kind filter if specified
        if kind:
            results = [r for r in results if r.kind.lower() == kind.lower()]
        
        # Sort by severity (high → medium → low)
        results = k8sgpt_reader.sort_by_severity(results)
        
        # Convert to dict
        results_dict = [result.to_dict() for result in results]
        
        filters_applied = {
            'severity': severity,
            'namespace': namespace,
            'kind': kind
        }
        
        logger.info(f"Returning {len(results)} filtered K8sGPT Results")
        
        return ResultListResponse(
            results=results_dict,
            count=len(results_dict),
            filters_applied=filters_applied
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing results: {e}")
        raise handle_generic_error(
            e,
            "listing K8sGPT results",
            "Unable to retrieve K8sGPT results. Please verify cluster connectivity."
        )


@router.get("/results/{result_id}", response_model=ResultDetailResponse)
async def get_result_detail(
    result_id: str,
    session_id: str = Depends(get_session_id)
):
    """
    Get detailed information about a specific K8sGPT Result.
    
    This endpoint retrieves a single K8sGPT Result by ID and optionally
    enriches it with additional context from the Kubernetes API.
    
    Args:
        result_id: K8sGPT Result CRD name
        session_id: Session ID from header
        
    Returns:
        ResultDetailResponse with result details and enrichment
        
    Raises:
        HTTPException: If result not found or reading fails
    """
    try:
        # Get selected cluster and K8s clients
        cluster = get_selected_cluster(session_id)
        k8s_clients = get_k8s_clients_for_session(session_id)
        
        cluster_name = cluster['name']
        
        logger.info(f"Getting K8sGPT Result {result_id} from cluster {cluster_name}")
        
        # Read all results and find the specific one
        custom_api = k8s_clients['custom_objects']
        k8sgpt_reader = K8sGPTReader(custom_api)
        
        try:
            results = await k8sgpt_reader.read_results()
        except ApiException as e:
            if e.status == 404:
                raise HTTPException(
                    status_code=404,
                    detail="K8sGPT CRD not found in cluster"
                )
            else:
                error_msg = handle_k8s_error(e, "read K8sGPT Results")
                logger.error(f"Failed to read K8sGPT Results: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Unable to read K8sGPT Results: {error_msg}"
                )
        
        # Find the specific result
        result = None
        for r in results:
            if r.name == result_id:
                result = r
                break
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"K8sGPT Result '{result_id}' not found"
            )
        
        # Enrich with additional context
        enrichment: Dict[str, Any] = {}
        
        try:
            core_api: CoreV1Api = k8s_clients['core_v1']
            
            # Get resource details based on kind
            resource_name = result.details.get('resource_name', '')
            
            if result.kind.lower() == 'pod' and resource_name:
                try:
                    pod = core_api.read_namespaced_pod(
                        name=resource_name,
                        namespace=result.namespace
                    )
                    enrichment['pod_status'] = {
                        'phase': pod.status.phase,
                        'conditions': [
                            {
                                'type': c.type,
                                'status': c.status,
                                'reason': c.reason,
                                'message': c.message
                            }
                            for c in (pod.status.conditions or [])
                        ],
                        'container_statuses': [
                            {
                                'name': cs.name,
                                'ready': cs.ready,
                                'restart_count': cs.restart_count,
                                'state': str(cs.state)
                            }
                            for cs in (pod.status.container_statuses or [])
                        ]
                    }
                except Exception as e:
                    logger.debug(f"Could not enrich pod details: {e}")
            
            # Get recent events for the resource
            try:
                events = core_api.list_namespaced_event(
                    namespace=result.namespace,
                    field_selector=f"involvedObject.name={resource_name}"
                )
                enrichment['recent_events'] = [
                    {
                        'type': event.type,
                        'reason': event.reason,
                        'message': event.message,
                        'timestamp': event.last_timestamp.isoformat() if event.last_timestamp else None
                    }
                    for event in events.items[:5]  # Last 5 events
                ]
            except Exception as e:
                logger.debug(f"Could not get events: {e}")
        
        except Exception as e:
            logger.warning(f"Failed to enrich result: {e}")
        
        return ResultDetailResponse(
            result=result.to_dict(),
            enrichment=enrichment if enrichment else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result detail: {e}")
        raise handle_generic_error(
            e,
            "getting K8sGPT result details",
            "Unable to retrieve result details. Please verify cluster connectivity."
        )
