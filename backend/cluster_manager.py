"""
Cluster discovery and Kubernetes client factory for both EKS (AWS) and local (kubeconfig) clusters.
"""
import boto3
import base64
import tempfile
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from kubernetes import client as k8s_client
from kubernetes.client import Configuration
from botocore.exceptions import ClientError, BotoCoreError
import logging

from credential_store import StoredCredentials
from eks_auth import get_eks_bearer_token
from local_k8s_auth import get_local_k8s_client
from utils.error_handler import handle_aws_error, handle_k8s_error, k8s_api_retry

logger = logging.getLogger(__name__)

# Cache for cluster discovery results
_cluster_cache: Dict[str, tuple] = {}  # {session_id: (clusters, timestamp)}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def discover_clusters(creds: StoredCredentials) -> List[Dict[str, Any]]:
    """
    Discover EKS clusters accessible with user's credentials.
    
    Implements caching to minimize API calls (300 second TTL).
    
    Args:
        creds: AWS credentials
        
    Returns:
        List of cluster metadata dictionaries with keys:
        - name: Cluster name
        - endpoint: K8s API endpoint URL
        - version: K8s version (e.g., "1.28")
        - status: Cluster status (ACTIVE, CREATING, etc.)
        - region: AWS region
        - ca_data: Base64-encoded CA certificate
        
    Raises:
        Exception: If cluster discovery fails
    """
    try:
        # Create EKS client
        eks_client = boto3.client(
            'eks',
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key,
            aws_session_token=creds.session_token,
            region_name=creds.region
        )
        
        # List clusters
        logger.info(f"Discovering EKS clusters in region {creds.region}")
        response = eks_client.list_clusters()
        cluster_names = response.get('clusters', [])
        
        if not cluster_names:
            logger.info("No EKS clusters found")
            return []
        
        # Get detailed information for each cluster
        clusters = []
        for cluster_name in cluster_names:
            try:
                cluster_info = eks_client.describe_cluster(name=cluster_name)
                cluster_data = cluster_info['cluster']
                
                clusters.append({
                    'name': cluster_data['name'],
                    'endpoint': cluster_data['endpoint'],
                    'version': cluster_data['version'],
                    'status': cluster_data['status'],
                    'region': creds.region,
                    'ca_data': cluster_data['certificateAuthority']['data']
                })
                
                logger.debug(f"Discovered cluster: {cluster_name} (version {cluster_data['version']})")
                
            except Exception as e:
                logger.warning(f"Failed to describe cluster {cluster_name}: {e}")
                # Continue with other clusters
                continue
        
        logger.info(f"Discovered {len(clusters)} EKS cluster(s)")
        return clusters
        
    except (ClientError, BotoCoreError) as e:
        logger.error(f"AWS error discovering clusters: {e}")
        raise handle_aws_error(e, "discovering EKS clusters")
    except Exception as e:
        logger.error(f"Failed to discover clusters: {e}")
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail="Unable to discover clusters. Please check your credentials and try again."
        )


def get_k8s_clients(creds: StoredCredentials, cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create authenticated Kubernetes API clients for target cluster.
    
    **CA Certificate Handling:**
    
    EKS clusters use TLS/SSL to secure the Kubernetes API endpoint. To verify the 
    server's identity and establish a secure connection, we need the cluster's 
    Certificate Authority (CA) certificate.
    
    The CA certificate:
    1. Is provided by AWS EKS in base64-encoded format
    2. Must be decoded and written to a temporary file
    3. Is used by the Kubernetes client to verify the API server's SSL certificate
    4. Prevents man-in-the-middle attacks by ensuring we're connecting to the real cluster
    
    Without the CA certificate, the Kubernetes client would either:
    - Fail to connect (if SSL verification is enabled)
    - Be vulnerable to MITM attacks (if SSL verification is disabled)
    
    The temporary file approach is used because the Kubernetes Python client expects
    a file path for the CA certificate, not the certificate data directly.
    
    Args:
        creds: AWS credentials
        cluster: Cluster metadata from discover_clusters()
        
    Returns:
        Dictionary with Kubernetes API clients:
        - core_v1: CoreV1Api (pods, services, nodes, etc.)
        - apps_v1: AppsV1Api (deployments, statefulsets, daemonsets)
        - custom_objects: CustomObjectsApi (CRDs like K8sGPT Results, ArgoCD Apps)
        - networking_v1: NetworkingV1Api (ingresses, network policies)
        - rbac_v1: RbacAuthorizationV1Api (roles, rolebindings)
        - _api_client: Base API client (for cleanup)
        - _ca_cert_path: Path to temp CA cert file (for cleanup)
        
    Raises:
        Exception: If client creation fails
    """
    try:
        cluster_name = cluster['name']
        endpoint = cluster['endpoint']
        ca_data = cluster['ca_data']
        
        # Generate EKS bearer token
        bearer_token = get_eks_bearer_token(creds, cluster_name)
        
        # Decode CA certificate and write to temp file
        ca_cert_bytes = base64.b64decode(ca_data)
        ca_cert_file = tempfile.NamedTemporaryFile(delete=False, suffix='.crt')
        ca_cert_file.write(ca_cert_bytes)
        ca_cert_file.flush()
        ca_cert_path = ca_cert_file.name
        ca_cert_file.close()
        
        # Configure Kubernetes client
        config = Configuration()
        config.host = endpoint
        config.api_key = {"authorization": f"Bearer {bearer_token}"}
        config.ssl_ca_cert = ca_cert_path
        config.verify_ssl = True
        
        # Create API clients
        api_client = k8s_client.ApiClient(config)
        
        clients = {
            'core_v1': k8s_client.CoreV1Api(api_client),
            'apps_v1': k8s_client.AppsV1Api(api_client),
            'custom_objects': k8s_client.CustomObjectsApi(api_client),
            'networking_v1': k8s_client.NetworkingV1Api(api_client),
            'rbac_v1': k8s_client.RbacAuthorizationV1Api(api_client),
            '_api_client': api_client,
            '_ca_cert_path': ca_cert_path,  # Store for cleanup
            '_auth_mode': 'aws',
            '_cluster_name': cluster_name,
        }
        
        logger.info(f"Created K8s API clients for cluster {cluster_name}")
        return clients
        
    except (ClientError, BotoCoreError) as e:
        logger.error(f"AWS error creating K8s clients: {e}")
        raise handle_aws_error(e, "creating Kubernetes API clients")
    except Exception as e:
        logger.error(f"Failed to create K8s clients: {e}")
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail="Unable to create Kubernetes API clients. Please verify the cluster is accessible."
        )


# EKS get-token tokens last ~60s. Refresh before this age so multi-round agent
# tool calls never ride a near-expired bearer for the full loop.
EKS_BEARER_MAX_AGE_SECONDS = 45


def refresh_eks_bearer_on_clients(
    clients: Dict[str, Any],
    creds: StoredCredentials,
    cluster_name: str,
) -> None:
    """
    Mint a fresh EKS bearer (60s TTL) onto an existing ApiClient configuration.

    Call at request start and before each K8s tool use so long agent turns do
    not fail after the initial token expires.

    Raises:
        RuntimeError: If the session map is torn down (no ApiClient / config).
            Callers should map this to HTTP 503 so clients re-select / re-auth.
    """
    import time

    if clients.get("_closed"):
        raise RuntimeError(
            "Cannot refresh EKS bearer: K8s clients were closed "
            f"(cluster={cluster_name!r})."
        )
    api_client = clients.get("_api_client")
    if api_client is None:
        raise RuntimeError(
            "Cannot refresh EKS bearer: session K8s ApiClient is missing "
            f"(cluster={cluster_name!r}; session may have been cleared)."
        )
    conf = getattr(api_client, "configuration", None)
    if conf is None:
        raise RuntimeError(
            "Cannot refresh EKS bearer: ApiClient configuration is missing "
            f"(cluster={cluster_name!r})."
        )
    bearer_token = get_eks_bearer_token(creds, cluster_name)
    conf.api_key = {"authorization": f"Bearer {bearer_token}"}
    clients["_token_refreshed_at"] = time.monotonic()
    clients["_auth_mode"] = "aws"
    clients["_cluster_name"] = cluster_name
    logger.debug("Refreshed EKS bearer for cluster %s", cluster_name)


def ensure_eks_bearer_fresh(
    clients: Dict[str, Any],
    creds: StoredCredentials,
    cluster_name: str,
    *,
    max_age_seconds: float = EKS_BEARER_MAX_AGE_SECONDS,
) -> bool:
    """
    Refresh EKS bearer if missing or older than max_age_seconds.

    Returns True if a refresh was performed, False if still fresh / not AWS.
    """
    import time

    # kubeconfig sessions never use EKS tokens.
    if clients.get("_auth_mode") == "kubeconfig":
        return False
    if getattr(creds, "auth_mode", None) not in (None, "aws"):
        return False
    if clients.get("_auth_mode") not in (None, "aws"):
        return False

    last = clients.get("_token_refreshed_at")
    now = time.monotonic()
    if isinstance(last, (int, float)) and (now - last) < max_age_seconds:
        return False

    refresh_eks_bearer_on_clients(clients, creds, cluster_name)
    return True


def cleanup_k8s_clients(clients: Dict[str, Any]) -> None:
    """
    Clean up Kubernetes API clients, wipe bearer/config secrets, remove temp files.

    Always empties the clients dict so session maps do not retain live handles
    or credential material after logout / cluster switch / expiry.
    """
    if not clients:
        return

    # Mark closed before wipe so concurrent refresh paths fail closed.
    clients["_closed"] = True

    try:
        api_client = clients.get("_api_client")
        if api_client is not None:
            conf = getattr(api_client, "configuration", None)
            if conf is not None:
                # Wipe auth material so GC/residual refs cannot reuse tokens.
                conf.api_key = {}
                conf.api_key_prefix = {}
                for attr in ("password", "username", "api_key"):
                    if hasattr(conf, attr) and attr != "api_key":
                        try:
                            setattr(conf, attr, None)
                        except Exception:
                            pass
            try:
                api_client.close()
            except Exception as e:
                logger.warning(f"Error closing K8s API client: {e}")

        ca_path = clients.get("_ca_cert_path")
        if ca_path:
            try:
                os.unlink(ca_path)
                logger.debug(f"Cleaned up CA cert file: {ca_path}")
            except Exception as e:
                logger.warning(f"Failed to remove CA cert file: {e}")

        kubeconfig_temp = clients.get("_kubeconfig_temp_path")
        if kubeconfig_temp:
            try:
                os.unlink(kubeconfig_temp)
                logger.debug(f"Cleaned up temp kubeconfig: {kubeconfig_temp}")
            except Exception as e:
                logger.warning(f"Failed to remove temp kubeconfig: {e}")

    except Exception as e:
        logger.warning(f"Error during K8s client cleanup: {e}")
    finally:
        # Drop all API object references (core_v1, custom_objects, …).
        # Keep a closed marker so request-held dicts still fail refresh.
        clients.clear()
        clients["_closed"] = True


class ClusterCache:
    """Cache for cluster discovery results."""
    
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, tuple] = {}
        self._ttl_seconds = ttl_seconds
    
    def get(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached clusters for a session."""
        if session_id not in self._cache:
            return None
        
        clusters, timestamp = self._cache[session_id]
        
        # Check if cache is still valid
        if datetime.now() - timestamp > timedelta(seconds=self._ttl_seconds):
            del self._cache[session_id]
            return None
        
        logger.debug(f"Cache hit for session {session_id[:8]}...")
        return clusters
    
    def set(self, session_id: str, clusters: List[Dict[str, Any]]) -> None:
        """Cache clusters for a session."""
        self._cache[session_id] = (clusters, datetime.now())
        logger.debug(f"Cached {len(clusters)} cluster(s) for session {session_id[:8]}...")
    
    def invalidate(self, session_id: str) -> None:
        """Invalidate cache for a session."""
        if session_id in self._cache:
            del self._cache[session_id]
            logger.debug(f"Invalidated cache for session {session_id[:8]}...")
    
    def cleanup_expired(self) -> int:
        """Remove expired cache entries."""
        now = datetime.now()
        expired = [
            session_id for session_id, (_, timestamp) in self._cache.items()
            if now - timestamp > timedelta(seconds=self._ttl_seconds)
        ]
        
        for session_id in expired:
            del self._cache[session_id]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entry/entries")
        
        return len(expired)


# Global cluster cache instance
cluster_cache = ClusterCache()
