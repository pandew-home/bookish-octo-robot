"""
Local Kubernetes Authentication Module for managing kubeconfig-based authentication.
"""
from typing import Dict, List, Optional, Tuple
import yaml
import os
import tempfile
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException
import logging

logger = logging.getLogger(__name__)


def validate_kubeconfig_content(content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate kubeconfig YAML content.
    
    Args:
        content: Raw YAML content of kubeconfig
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not content or not content.strip():
            return False, "Kubeconfig content is empty"
        
        kubeconfig_data = yaml.safe_load(content)
        
        if not isinstance(kubeconfig_data, dict):
            return False, "Invalid kubeconfig format: not a valid YAML mapping"
        
        if 'apiVersion' not in kubeconfig_data:
            return False, "Kubeconfig missing 'apiVersion' field"
        
        if 'kind' not in kubeconfig_data:
            return False, "Kubeconfig missing 'kind' field"
        
        if kubeconfig_data.get('kind') != 'Config':
            return False, f"Invalid kind '{kubeconfig_data.get('kind')}', expected 'Config'"
        
        return True, None
        
    except yaml.YAMLError as e:
        return False, f"Invalid YAML syntax: {str(e)}"
    except Exception as e:
        return False, f"Error validating kubeconfig: {str(e)}"


def parse_kubeconfig_content(content: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Parse kubeconfig content and extract contexts.
    
    Args:
        content: Raw YAML content of kubeconfig
        
    Returns:
        Tuple of (parsed_data, error_message)
    """
    try:
        # Validate first
        is_valid, error = validate_kubeconfig_content(content)
        if not is_valid:
            return None, error
        
        kubeconfig_data = yaml.safe_load(content)
        
        result = {
            'contexts': [],
            'current_context': None,
            'clusters': [],
            'users': []
        }
        
        # Extract contexts
        if 'contexts' in kubeconfig_data:
            for ctx in kubeconfig_data['contexts']:
                if 'name' in ctx and 'context' in ctx:
                    result['contexts'].append({
                        'name': ctx['name'],
                        'cluster': ctx['context'].get('cluster', ''),
                        'user': ctx['context'].get('user', ''),
                        'namespace': ctx['context'].get('namespace', '')
                    })
        
        # Get current context
        result['current_context'] = kubeconfig_data.get('current-context')
        
        # Extract clusters (for reference)
        if 'clusters' in kubeconfig_data:
            for cluster in kubeconfig_data['clusters']:
                if 'name' in cluster:
                    result['clusters'].append(cluster['name'])
        
        # Extract users (for reference)
        if 'users' in kubeconfig_data:
            for user in kubeconfig_data['users']:
                if 'name' in user:
                    result['users'].append(user['name'])
        
        logger.info(f"Parsed kubeconfig: {len(result['contexts'])} contexts, current={result['current_context']}")
        
        return result, None
        
    except Exception as e:
        logger.error(f"Error parsing kubeconfig content: {e}")
        return None, str(e)


def _filter_kubeconfig_for_context(
    content: str, context_name: Optional[str] = None
) -> Tuple[dict, str]:
    """Return (filtered_kubeconfig_dict, resolved_context_name)."""
    is_valid, error = validate_kubeconfig_content(content)
    if not is_valid:
        raise ValueError(f"Invalid kubeconfig: {error}")

    kubeconfig_data = yaml.safe_load(content)

    if context_name is None:
        context_name = kubeconfig_data.get("current-context")
        logger.info(f"No context specified, using current-context: {context_name}")

    if not context_name:
        raise ValueError("No context specified and kubeconfig has no current-context")

    selected_context = None
    referenced_cluster = None
    referenced_user = None

    for ctx in kubeconfig_data.get("contexts", []):
        if ctx.get("name") == context_name:
            selected_context = ctx
            referenced_cluster = ctx.get("context", {}).get("cluster")
            referenced_user = ctx.get("context", {}).get("user")
            break

    if not selected_context:
        available_contexts = [
            ctx.get("name") for ctx in kubeconfig_data.get("contexts", [])
        ]
        raise ValueError(
            f"Context '{context_name}' not found in kubeconfig. "
            f"Available contexts: {available_contexts}"
        )

    filtered_kubeconfig = {
        "apiVersion": kubeconfig_data.get("apiVersion"),
        "kind": "Config",
        "current-context": context_name,
        "contexts": [selected_context],
        "clusters": [],
        "users": [],
    }

    if referenced_cluster:
        for cluster in kubeconfig_data.get("clusters", []):
            if cluster.get("name") == referenced_cluster:
                filtered_kubeconfig["clusters"].append(cluster)
                break

    if referenced_user:
        for user in kubeconfig_data.get("users", []):
            if user.get("name") == referenced_user:
                filtered_kubeconfig["users"].append(user)
                break

    return filtered_kubeconfig, context_name


def get_k8s_clients_bundle_from_content(
    content: str, context_name: Optional[str] = None
) -> Dict[str, object]:
    """
    Build a full set of Kubernetes API clients from kubeconfig content.

    Uses a dedicated Configuration + ApiClient (no process-global default config)
    so multi-session kubeconfig auth cannot race or leave residual credentials
    after logout. Temp kubeconfig file is kept for the session lifetime and must
    be removed via cleanup_k8s_clients (_kubeconfig_temp_path).
    """
    temp_path: Optional[str] = None
    try:
        filtered, resolved_context = _filter_kubeconfig_for_context(
            content, context_name
        )

        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".kubeconfig", delete=False
        )
        yaml.dump(filtered, temp_file, default_flow_style=False)
        temp_file.close()
        temp_path = temp_file.name

        configuration = client.Configuration()
        config.load_kube_config(
            config_file=temp_path,
            client_configuration=configuration,
        )
        api_client = client.ApiClient(configuration)

        logger.info(
            "Created session-scoped K8s ApiClient for kubeconfig context: %s",
            resolved_context,
        )
        return {
            "core_v1": client.CoreV1Api(api_client),
            "apps_v1": client.AppsV1Api(api_client),
            "custom_objects": client.CustomObjectsApi(api_client),
            "networking_v1": client.NetworkingV1Api(api_client),
            "rbac_v1": client.RbacAuthorizationV1Api(api_client),
            "_api_client": api_client,
            "_ca_cert_path": None,
            "_kubeconfig_temp_path": temp_path,
            "_auth_mode": "kubeconfig",
        }
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp kubeconfig: {e}")
        raise


def get_k8s_clients_bundle_from_path(
    kubeconfig_path: str, context_name: Optional[str] = None
) -> Dict[str, object]:
    """Build session-scoped clients from a kubeconfig file path (dedicated ApiClient)."""
    configuration = client.Configuration()
    config.load_kube_config(
        config_file=kubeconfig_path,
        context=context_name,
        client_configuration=configuration,
    )
    api_client = client.ApiClient(configuration)
    return {
        "core_v1": client.CoreV1Api(api_client),
        "apps_v1": client.AppsV1Api(api_client),
        "custom_objects": client.CustomObjectsApi(api_client),
        "networking_v1": client.NetworkingV1Api(api_client),
        "rbac_v1": client.RbacAuthorizationV1Api(api_client),
        "_api_client": api_client,
        "_ca_cert_path": None,
        "_kubeconfig_temp_path": None,
        "_auth_mode": "kubeconfig",
    }


def get_k8s_client_from_content(
    content: str, context_name: Optional[str] = None
) -> client.CoreV1Api:
    """
    Create a Kubernetes CoreV1Api client from kubeconfig content.

    Prefer get_k8s_clients_bundle_from_content for multi-API session use so all
    typed clients share one ApiClient and cleanup can wipe auth material.
    """
    try:
        bundle = get_k8s_clients_bundle_from_content(content, context_name)
        return bundle["core_v1"]  # type: ignore[return-value]
    except ConfigException as e:
        logger.error(f"ConfigException when creating Kubernetes client: {e}")
        raise
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error creating Kubernetes client: {e}")
        raise


def validate_kubeconfig(kubeconfig_path: str) -> bool:
    """
    Validate that a kubeconfig file is readable and contains valid Kubernetes configuration.
    
    Args:
        kubeconfig_path: Path to the kubeconfig file
        
    Returns:
        True if the kubeconfig is valid, False otherwise
    """
    try:
        # Expand ~ to home directory
        expanded_path = os.path.expanduser(kubeconfig_path)
        logger.info(f"Validating kubeconfig: input={kubeconfig_path}, expanded={expanded_path}")
        
        if not os.path.exists(expanded_path):
            logger.error(f"Kubeconfig file not found: {kubeconfig_path} (expanded: {expanded_path})")
            return False
            
        if not os.path.isfile(expanded_path):
            logger.error(f"Path is not a file: {kubeconfig_path} (expanded: {expanded_path})")
            return False
        
        # Check file permissions
        if not os.access(expanded_path, os.R_OK):
            logger.error(f"Kubeconfig file not readable: {expanded_path}")
            return False
            
        logger.info(f"Kubeconfig file exists and is readable: {expanded_path}")
            
        with open(expanded_path, 'r') as f:
            kubeconfig_data = yaml.safe_load(f)
            
        if not isinstance(kubeconfig_data, dict):
            logger.error(f"Invalid kubeconfig format: {kubeconfig_path}")
            return False
            
        if 'apiVersion' not in kubeconfig_data or 'kind' not in kubeconfig_data:
            logger.error(f"Kubeconfig missing apiVersion or kind: {kubeconfig_path}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error validating kubeconfig: {e}")
        return False


def discover_local_clusters(kubeconfig_path: str) -> Dict[str, str]:
    """
    Discover all clusters and contexts from a kubeconfig file.
    
    Args:
        kubeconfig_path: Path to the kubeconfig file
        
    Returns:
        Dictionary mapping context names to cluster names
    """
    contexts = {}
    
    try:
        # Expand ~ to home directory
        expanded_path = os.path.expanduser(kubeconfig_path)
        logger.info(f"Discovering clusters from kubeconfig: {expanded_path}")
        
        with open(expanded_path, 'r') as f:
            kubeconfig_data = yaml.safe_load(f)
            
        if 'contexts' not in kubeconfig_data:
            logger.warning(f"No contexts key in kubeconfig. Keys found: {list(kubeconfig_data.keys()) if kubeconfig_data else 'None'}")
            return contexts
            
        for context in kubeconfig_data['contexts']:
            context_name = context['name']
            cluster_name = context['context']['cluster']
            contexts[context_name] = cluster_name
            
        logger.info(f"Discovered {len(contexts)} contexts from kubeconfig")
        
    except Exception as e:
        logger.error(f"Error discovering clusters from kubeconfig: {e}")
        
    return contexts


def get_local_k8s_client(kubeconfig_path: str, context_name: Optional[str] = None) -> client.CoreV1Api:
    """
    Create a Kubernetes API client using the specified kubeconfig and optional context.
    
    Args:
        kubeconfig_path: Path to the kubeconfig file
        context_name: Optional context name to use
        
    Returns:
        Kubernetes CoreV1Api client instance
        
    Raises:
        ConfigException: If there's an error loading the kubeconfig
        Exception: For other errors
    """
    try:
        # Expand ~ to home directory
        expanded_path = os.path.expanduser(kubeconfig_path)
        
        # Load kubeconfig
        config.load_kube_config(config_file=expanded_path, context=context_name)
        
        # Create CoreV1Api client
        v1 = client.CoreV1Api()
        
        logger.info(f"Successfully created Kubernetes client for context: {context_name or 'default'}")
        
        return v1
        
    except ConfigException as e:
        logger.error(f"ConfigException when creating Kubernetes client: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating Kubernetes client: {e}")
        raise
