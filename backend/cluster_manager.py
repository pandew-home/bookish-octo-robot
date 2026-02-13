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
            '_ca_cert_path': ca_cert_path  # Store for cleanup
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


def cleanup_k8s_clients(clients: Dict[str, Any]) -> None:
    """
    Clean up Kubernetes API clients and temporary files.
    
    Args:
        clients: Dictionary of K8s clients from get_k8s_clients()
    """
    try:
        # Close API client
        if '_api_client' in clients:
            clients['_api_client'].close()
        
        # Remove temporary CA cert file
        if '_ca_cert_path' in clients:
            try:
                os.unlink(clients['_ca_cert_path'])
                logger.debug(f"Cleaned up CA cert file: {clients['_ca_cert_path']}")
            except Exception as e:
                logger.warning(f"Failed to remove CA cert file: {e}")
                
    except Exception as e:
        logger.warning(f"Error during K8s client cleanup: {e}")


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
