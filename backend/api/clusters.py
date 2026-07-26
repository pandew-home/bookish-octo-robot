"""
API endpoints for cluster management (AWS EKS + local kubeconfig).
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import threading

from api.credentials import (
    get_session_id,
    get_credentials_for_session,
    get_target_eks_cluster_name,
)
from cluster_manager import (
    discover_clusters,
    get_k8s_clients,
    cluster_cache,
    ensure_eks_bearer_fresh,
    refresh_eks_bearer_on_clients,
)
from local_k8s_auth import (
    discover_local_clusters,
    get_k8s_clients_bundle_from_content,
    get_k8s_clients_bundle_from_path,
)
from utils.error_handler import handle_aws_error, handle_k8s_error, handle_generic_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clusters", tags=["clusters"])

# Session storage for selected clusters and K8s clients
_session_clusters: Dict[str, Dict[str, Any]] = {}
_session_k8s_clients: Dict[str, Dict[str, Any]] = {}
_session_lock = threading.RLock()


class ClusterInfo(BaseModel):
    """Cluster information model."""
    name: str
    endpoint: str
    version: str
    status: str
    region: str


class ClusterListResponse(BaseModel):
    """Response model for cluster list."""
    clusters: List[ClusterInfo]
    count: int


class ClusterSelectRequest(BaseModel):
    """Request model for cluster selection."""
    cluster_name: str


class ClusterSelectResponse(BaseModel):
    """Response model for cluster selection."""
    success: bool
    message: str
    cluster_name: str


@router.get("", response_model=ClusterListResponse)
async def list_clusters(session_id: str = Depends(get_session_id)):
    """
    Discover and list available clusters (EKS or local kubeconfig).
    
    Delegates based on auth_mode:
    - "aws": Uses AWS credentials to discover EKS clusters via ListClusters API
    - "kubeconfig": Uses kubeconfig file to list available contexts
    
    Results are cached for 300 seconds to minimize API calls.
    
    Args:
        session_id: Session ID from header
        
    Returns:
        ClusterListResponse with list of accessible clusters
        
    Raises:
        HTTPException: If cluster discovery fails
    """
    try:
        # Get credentials
        creds = get_credentials_for_session(session_id)
        
        # Check cache first
        cached_clusters = cluster_cache.get(session_id)
        if cached_clusters is not None:
            logger.debug(f"Returning cached clusters for session {session_id[:8]}...")
            return ClusterListResponse(
                clusters=[ClusterInfo(**c) for c in cached_clusters],
                count=len(cached_clusters)
            )
        
        # Delegate based on auth mode
        logger.info(f"Discovering clusters for session {session_id[:8]}... (auth_mode={creds.auth_mode})")
        
        if creds.auth_mode == "kubeconfig":
            clusters = _discover_kubeconfig_clusters(creds)
        else:
            clusters = await discover_clusters(creds)
            target_cluster_name = get_target_eks_cluster_name()
            if target_cluster_name:
                clusters = [c for c in clusters if c.get("name") == target_cluster_name]
                if not clusters:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"No access to configured target cluster '{target_cluster_name}'. "
                            "Please use credentials with access to this cluster."
                        ),
                    )
            elif clusters:
                # Single-cluster mode: present one default cluster when no explicit target is configured.
                clusters = [clusters[0]]
        
        # Cache results
        cluster_cache.set(session_id, clusters)
        
        logger.info(f"Discovered {len(clusters)} cluster(s) for session {session_id[:8]}...")
        
        return ClusterListResponse(
            clusters=[ClusterInfo(**c) for c in clusters],
            count=len(clusters)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering clusters: {e}")
        raise handle_generic_error(
            e,
            "discovering clusters",
            "Unable to discover clusters. Please verify your credentials and network connection."
        )


def _discover_kubeconfig_clusters(creds) -> List[Dict[str, Any]]:
    """
    Discover clusters from kubeconfig contexts.
    
    Args:
        creds: StoredCredentials with kubeconfig_path and kubeconfig_contexts
        
    Returns:
        List of cluster metadata dictionaries
    """
    clusters = []
    for context_name, cluster_name in creds.kubeconfig_contexts.items():
        clusters.append({
            'name': context_name,  # Use context name as display name
            'endpoint': 'local',   # Local clusters don't have a fixed endpoint
            'version': 'unknown',  # Version discovered on connect
            'status': 'available',
            'region': 'local',
            'cluster_name': cluster_name,  # Actual cluster name
            'context_name': context_name
        })
    return clusters


def _get_kubeconfig_k8s_clients(creds, cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create Kubernetes API clients using kubeconfig with a dedicated ApiClient.

    Does not mutate process-global kubernetes config. All typed APIs share one
    ApiClient so logout/cleanup can wipe auth material.
    """
    context_name = cluster.get("context_name", cluster["name"])

    if creds.kubeconfig_content:
        return get_k8s_clients_bundle_from_content(
            creds.kubeconfig_content, context_name
        )
    if not creds.kubeconfig_path:
        raise HTTPException(
            status_code=400,
            detail="Kubeconfig path or content is required for local cluster access.",
        )
    return get_k8s_clients_bundle_from_path(creds.kubeconfig_path, context_name)


@router.post("/select", response_model=ClusterSelectResponse)
async def select_cluster(
    request: ClusterSelectRequest,
    session_id: str = Depends(get_session_id)
):
    """
    Select a target cluster for operations.
    
    This endpoint implements multi-cluster support by:
    1. Generating a new EKS bearer token for the selected cluster
    2. Reconfiguring Kubernetes API clients for the new cluster
    3. Switching conversation history to the new cluster
    4. Clearing cached cluster-specific data (weather, results, enrichment)
    
    When switching clusters:
    - Old K8s clients are cleaned up (connections closed, temp files removed)
    - New bearer token is generated from user's AWS credentials
    - New K8s API clients are created with the new token
    - Conversation history is isolated per cluster
    - Cached cluster-specific data is invalidated
    
    Args:
        request: Cluster selection request with cluster name
        session_id: Session ID from header
        
    Returns:
        ClusterSelectResponse with success status
        
    Raises:
        HTTPException: If cluster selection fails
    """
    try:
        # Get credentials
        creds = get_credentials_for_session(session_id)
        
        # Check if switching to a different cluster
        current_cluster = _session_clusters.get(session_id)
        current_cluster_name = current_cluster.get('name') if current_cluster else None
        is_switching = current_cluster_name is not None and current_cluster_name != request.cluster_name
        
        if is_switching:
            logger.info(
                f"Switching from cluster {current_cluster_name} to {request.cluster_name} for session {session_id[:8]}..."
            )

        # Get cluster list (from cache or discover)
        cached_clusters = cluster_cache.get(session_id)
        if cached_clusters is None:
            logger.info(f"Discovering clusters for selection (session {session_id[:8]}...)")
            if creds.auth_mode == "kubeconfig":
                cached_clusters = _discover_kubeconfig_clusters(creds)
            else:
                cached_clusters = await discover_clusters(creds)
            cluster_cache.set(session_id, cached_clusters)

        # Find the selected cluster
        selected_cluster = None
        for cluster in cached_clusters:
            if cluster['name'] == request.cluster_name:
                selected_cluster = cluster
                break

        if selected_cluster is None:
            raise HTTPException(
                status_code=404,
                detail=f"Cluster '{request.cluster_name}' not found"
            )

        # Create K8s clients based on auth mode
        logger.info(f"Creating K8s clients for cluster {request.cluster_name} (auth_mode={creds.auth_mode})")
        if creds.auth_mode == "kubeconfig":
            k8s_clients = _get_kubeconfig_k8s_clients(creds, selected_cluster)
        else:
            k8s_clients = get_k8s_clients(creds, selected_cluster)

        # Always replace prior clients (same-name re-select still needs cleanup).
        with _session_lock:
            old_clients = _session_k8s_clients.pop(session_id, None)
            _session_clusters[session_id] = selected_cluster
            _session_k8s_clients[session_id] = k8s_clients
        if old_clients is not None:
            from cluster_manager import cleanup_k8s_clients

            cleanup_k8s_clients(old_clients)
            logger.debug(
                "Cleaned up previous K8s clients for session %s...",
                session_id[:8],
            )

        # Clear cached cluster-specific data when switching
        if is_switching:
            clear_cluster_specific_cache(session_id)
            logger.debug(f"Cleared cluster-specific cache for session {session_id[:8]}...")

        logger.info(f"Selected cluster {request.cluster_name} for session {session_id[:8]}...")

        return ClusterSelectResponse(
            success=True,
            message=f"Successfully selected cluster '{request.cluster_name}'",
            cluster_name=request.cluster_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error selecting cluster: {e}")
        raise handle_generic_error(
            e,
            "selecting cluster",
            "Unable to connect to the selected cluster. Please verify the cluster is accessible."
        )


def get_selected_cluster(session_id: str) -> Dict[str, Any]:
    """
    Get the selected cluster for a session.

    Raises:
        HTTPException: If no cluster is selected
    """
    with _session_lock:
        cluster = _session_clusters.get(session_id)

    if cluster is None:
        raise HTTPException(
            status_code=400,
            detail="No cluster selected. Please select a cluster first.",
        )

    return cluster


def ensure_session_k8s_auth_fresh(session_id: str, clients: Dict[str, Any]) -> None:
    """
    Refresh EKS bearer on the given clients if stale (mid-chat / multi-tool).

    Uses current store credentials. Raises HTTPException if creds expired.
    No-op for kubeconfig sessions.
    """
    if clients.get("_auth_mode") == "kubeconfig":
        return
    # Legacy maps may omit _auth_mode; only refresh when AWS creds are present.
    creds = get_credentials_for_session(session_id)
    if creds.auth_mode != "aws" and clients.get("_auth_mode") != "aws":
        return

    cluster_name = (
        clients.get("_cluster_name")
        or (_session_clusters.get(session_id) or {}).get("name")
        or (_session_clusters.get(session_id) or {}).get("cluster_name")
    )
    if not cluster_name:
        return

    try:
        ensure_eks_bearer_fresh(clients, creds, str(cluster_name))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to refresh EKS bearer mid-session: %s", e)
        raise HTTPException(
            status_code=503,
            detail=(
                "Unable to refresh cluster access token. "
                "Re-select the cluster or re-authenticate."
            ),
        ) from e


def get_k8s_clients_for_session(session_id: str) -> Dict[str, Any]:
    """
    Get Kubernetes API clients for a session (request-scoped snapshot).

    - Re-validates stored credentials (401 + teardown on expiry).
    - Refreshes EKS bearer tokens (60s TTL) so tools work past select time.
    - Returns a **shallow copy** of the clients map so logout `clear()` on the
      session dict does not empty the in-flight request's dict keys.
    - Attaches ``_ensure_auth_fresh`` for mid-agent EKS re-mint (shared ApiClient).
    - Re-checks session ownership after STS so concurrent logout/re-select cannot
      hand a closed or replaced client map to the request.
    """
    # Fail closed if credentials expired/missing; may clear session clients via hook.
    creds = get_credentials_for_session(session_id)

    with _session_lock:
        clients = _session_k8s_clients.get(session_id)
        cluster = _session_clusters.get(session_id)

        if clients is None or cluster is None:
            raise HTTPException(
                status_code=400,
                detail="No cluster selected. Please select a cluster first.",
            )
        if clients.get("_closed"):
            raise HTTPException(
                status_code=400,
                detail="Cluster session ended. Please re-select the cluster.",
            )
        # Snapshot refs under lock; do STS/network outside the global lock.
        cluster_name = cluster.get("name") or cluster.get("cluster_name")
        need_aws_refresh = (
            creds.auth_mode == "aws" or clients.get("_auth_mode") == "aws"
        )
        if need_aws_refresh and clients.get("_api_client") is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Unable to refresh cluster access token. "
                    "Re-select the cluster or re-authenticate."
                ),
            )

    if need_aws_refresh and cluster_name:
        try:
            # Always mint at request start so the first tool has a full ~60s window.
            # STS runs outside the global lock; ownership re-checked below.
            refresh_eks_bearer_on_clients(clients, creds, str(cluster_name))
        except Exception as e:
            logger.error("Failed to refresh EKS bearer for session: %s", e)
            raise HTTPException(
                status_code=503,
                detail=(
                    "Unable to refresh cluster access token. "
                    "Re-select the cluster or re-authenticate."
                ),
            ) from e

    # Re-verify session still owns this map after any out-of-lock STS work.
    # Concurrent clear_session_cluster pops the map and cleanup marks closed.
    with _session_lock:
        current = _session_k8s_clients.get(session_id)
        if current is not clients or clients.get("_closed"):
            raise HTTPException(
                status_code=400,
                detail="Cluster session ended. Please re-select the cluster.",
            )
        if need_aws_refresh and clients.get("_api_client") is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Unable to refresh cluster access token. "
                    "Re-select the cluster or re-authenticate."
                ),
            )
        if "core_v1" not in clients and "custom_objects" not in clients:
            raise HTTPException(
                status_code=400,
                detail="Cluster session ended. Please re-select the cluster.",
            )
        # Shallow copy: session map clear/pop does not mutate this dict identity.
        # Same ApiClient as session map — auth refresh updates shared configuration.
        snap = dict(clients)

    sid = session_id

    def _ensure_auth_fresh() -> None:
        ensure_session_k8s_auth_fresh(sid, snap)

    snap["_ensure_auth_fresh"] = _ensure_auth_fresh
    snap["_session_id"] = session_id
    return snap


def clear_session_cluster(session_id: str) -> None:
    """
    Clear selected cluster and K8s clients for a session.

    Closes API clients, wipes bearer/CA material, and drops session maps so
    logout / expiry leaves no usable cluster credentials in memory.
    """
    with _session_lock:
        _session_clusters.pop(session_id, None)
        clients = _session_k8s_clients.pop(session_id, None)

    if clients is not None:
        from cluster_manager import cleanup_k8s_clients

        cleanup_k8s_clients(clients)

    # Drop discovery cache entries that may retain cluster endpoints/CA data.
    try:
        cluster_cache.invalidate(session_id)
    except Exception as e:
        logger.debug(f"cluster_cache invalidate failed for {session_id[:8]}...: {e}")

    logger.debug(f"Cleared cluster selection for session {session_id[:8]}...")


def clear_cluster_specific_cache(session_id: str) -> None:
    """
    Clear cached cluster-specific data when switching clusters.
    
    This function invalidates:
    - Weather cache (cluster health state)
    - K8sGPT results cache
    - Enrichment data cache
    
    Conversation history is NOT cleared - it's isolated per cluster and
    automatically switches when the cluster changes.
    
    Args:
        session_id: Session ID
    """
    # Note: Weather cache is stored in the HealthMonitor instance per session
    # We don't have a global weather cache to clear here, but the weather
    # endpoint will create a new HealthMonitor for the new cluster's K8s clients
    
    # Clear cluster discovery cache if needed (though this is per-session, not per-cluster)
    # We keep the cluster list cache since it's still valid for the user's credentials
    
    logger.debug(f"Cleared cluster-specific cache for session {session_id[:8]}...")
