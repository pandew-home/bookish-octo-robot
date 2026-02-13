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


def get_k8s_client_from_content(content: str, context_name: Optional[str] = None) -> client.CoreV1Api:
    """
    Create a Kubernetes API client from kubeconfig content.
    
    This writes the content to a temporary file and loads it, since the Kubernetes
    client library requires a file path.
    
    Args:
        content: Raw YAML content of kubeconfig
        context_name: Optional context name to use
        
    Returns:
        Kubernetes CoreV1Api client instance
        
    Raises:
        ConfigException: If there's an error loading the kubeconfig
        Exception: For other errors
    """
    temp_file = None
    try:
        # Validate content first
        is_valid, error = validate_kubeconfig_content(content)
        if not is_valid:
            raise ValueError(f"Invalid kubeconfig: {error}")
        
        # Write to temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.kubeconfig', delete=False)
        temp_file.write(content)
        temp_file.close()
        
        logger.info(f"Created temporary kubeconfig file: {temp_file.name}")
        
        # Load kubeconfig from temp file
        config.load_kube_config(config_file=temp_file.name, context=context_name)
        
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
    finally:
        # Clean up temp file
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
                logger.debug(f"Cleaned up temporary kubeconfig file: {temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")


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
