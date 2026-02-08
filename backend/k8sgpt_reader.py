"""
K8sGPT Result CRD Reader

This module provides functionality to read and parse K8sGPT Result CRDs from
Kubernetes clusters. K8sGPT is a tool that scans clusters for issues and creates
Result CRDs containing diagnostic information.

Requirements: 3.1, 12.1
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

from kubernetes.client import CustomObjectsApi
from kubernetes.client.rest import ApiException

from utils.error_handler import handle_k8s_error, k8s_api_retry

logger = logging.getLogger(__name__)


@dataclass
class K8sGPTResult:
    """
    Represents a K8sGPT Result CRD.
    
    Attributes:
        name: Result CRD name
        kind: Resource kind (Pod, Deployment, etc.)
        namespace: Resource namespace
        severity: Issue severity ("low", "medium", "high")
        problem: Problem description
        solution: Suggested solution
        analyzer: K8sGPT analyzer name
        timestamp: Result creation time
        details: Additional metadata
    """
    name: str
    kind: str
    namespace: str
    severity: str
    problem: str
    solution: str
    analyzer: str
    timestamp: datetime
    details: Dict
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert datetime to ISO format string
        if isinstance(result['timestamp'], datetime):
            result['timestamp'] = result['timestamp'].isoformat()
        return result


class K8sGPTReader:
    """
    Reads and parses K8sGPT Result CRDs from Kubernetes clusters.
    
    K8sGPT creates Result CRDs in the format:
    - Group: core.k8sgpt.ai
    - Version: v1alpha1
    - Plural: results
    """
    
    # K8sGPT CRD configuration
    GROUP = "core.k8sgpt.ai"
    VERSION = "v1alpha1"
    PLURAL = "results"
    
    def __init__(self, custom_api: CustomObjectsApi):
        """
        Initialize K8sGPT reader.
        
        Args:
            custom_api: Kubernetes CustomObjectsApi client
        """
        self.custom_api = custom_api
    
    @k8s_api_retry(max_retries=3, initial_delay=1.0)
    async def read_results(
        self,
        namespace: Optional[str] = None,
        severity_filter: Optional[str] = None
    ) -> List[K8sGPTResult]:
        """
        Read K8sGPT Result CRDs from the cluster.
        
        Implements retry logic with exponential backoff for connection failures.
        Does not retry on RBAC 403 errors.
        
        Requirements: 17.7
        
        Args:
            namespace: Optional namespace filter (None = all namespaces)
            severity_filter: Optional severity filter ("low", "medium", "high")
        
        Returns:
            List of K8sGPTResult objects
        
        Raises:
            ApiException: If CRD reading fails after retries
        """
        try:
            # Read CRDs from cluster
            if namespace:
                logger.info(f"Reading K8sGPT Results from namespace: {namespace}")
                response = self.custom_api.list_namespaced_custom_object(
                    group=self.GROUP,
                    version=self.VERSION,
                    namespace=namespace,
                    plural=self.PLURAL
                )
            else:
                logger.info("Reading K8sGPT Results from all namespaces")
                response = self.custom_api.list_cluster_custom_object(
                    group=self.GROUP,
                    version=self.VERSION,
                    plural=self.PLURAL
                )
            
            # Parse results
            items = response.get('items', [])
            logger.info(f"Found {len(items)} K8sGPT Result CRDs")
            
            results = []
            for item in items:
                try:
                    parsed_result = self._parse_result(item)
                    
                    # Apply severity filter if specified
                    if severity_filter and parsed_result.severity != severity_filter:
                        continue
                    
                    results.append(parsed_result)
                except Exception as e:
                    logger.warning(f"Failed to parse K8sGPT result: {e}")
                    continue
            
            logger.info(f"Successfully parsed {len(results)} K8sGPT Results")
            return results
            
        except ApiException as e:
            if e.status == 404:
                # CRD not installed or no results exist
                logger.info("K8sGPT Result CRDs not found (CRD may not be installed)")
                return []
            else:
                # Other API errors
                error_msg = handle_k8s_error(e, "read K8sGPT Results")
                logger.error(f"Failed to read K8sGPT Results: {error_msg}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error reading K8sGPT Results: {e}")
            raise
    
    def _parse_result(self, result: Dict) -> K8sGPTResult:
        """
        Parse a K8sGPT Result CRD into a structured object.
        
        Args:
            result: Raw CRD data from Kubernetes API
        
        Returns:
            K8sGPTResult object
        """
        metadata = result.get('metadata', {})
        spec = result.get('spec', {})
        
        # Extract basic info
        kind = spec.get('kind', 'Unknown')
        resource_name = spec.get('name', 'Unknown')
        
        # Extract error details - K8sGPT stores issues in the 'error' field
        error_list = spec.get('error', [])
        
        # Parse problem and solution from error list
        problem = spec.get('details', '')
        solution = ''
        
        if isinstance(error_list, list) and error_list:
            # Combine error messages into problem description
            if not problem:
                problem = ' '.join(str(e) for e in error_list)
            # K8sGPT may provide solutions in the error text
            for error_text in error_list:
                if isinstance(error_text, str) and ('solution' in error_text.lower() or 'fix' in error_text.lower()):
                    solution = error_text
                    break
        
        # Determine severity based on error content and kind
        severity = self._determine_severity(problem, kind)
        
        # Extract namespace - may be in metadata or spec
        namespace = metadata.get('namespace', spec.get('namespace', 'default'))
        
        # Extract analyzer name - K8sGPT uses 'backend' field
        analyzer = spec.get('backend', 'Unknown')
        
        # Extract timestamp - use creation timestamp from metadata
        timestamp = self._parse_timestamp(metadata.get('creationTimestamp', ''))
        
        return K8sGPTResult(
            name=metadata.get('name', 'unknown'),
            kind=kind,
            namespace=namespace,
            severity=severity,
            problem=problem if problem else 'No problem description available',
            solution=solution if solution else 'No solution provided',
            analyzer=analyzer,
            timestamp=timestamp,
            details={
                'resource_name': resource_name,
                'error': error_list,
                'backend': spec.get('backend', 'Unknown')
            }
        )
    
    def _determine_severity(self, problem: str, kind: str) -> str:
        """
        Determine severity based on problem content and resource kind.
        
        Args:
            problem: Problem description
            kind: Resource kind
        
        Returns:
            Severity level ("low", "medium", "high")
        """
        problem_lower = problem.lower()
        
        # High severity indicators
        high_indicators = [
            'crashloopbackoff', 'imagepullbackoff', 'oomkilled',
            'failed', 'error', 'critical', 'down', 'unavailable',
            'crash', 'terminated', 'evicted'
        ]
        
        # Low severity indicators
        low_indicators = [
            'warning', 'pending', 'info', 'notice', 'deprecated'
        ]
        
        # Check for high severity
        if any(indicator in problem_lower for indicator in high_indicators):
            return 'high'
        
        # Check for low severity
        if any(indicator in problem_lower for indicator in low_indicators):
            return 'low'
        
        # Default to medium
        return 'medium'
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse ISO format timestamp from K8s metadata.
        
        Args:
            timestamp_str: ISO format timestamp string
        
        Returns:
            datetime object (or current time if parsing fails)
        """
        if not timestamp_str:
            return datetime.utcnow()
        
        try:
            # Parse ISO format timestamp (K8s uses RFC3339 with Z suffix)
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse timestamp: {timestamp_str}")
            return datetime.utcnow()
    
    def filter_by_relevance(
        self,
        results: List[K8sGPTResult],
        resource_names: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        kinds: Optional[List[str]] = None
    ) -> List[K8sGPTResult]:
        """
        Filter results by relevance to a query.
        
        Args:
            results: List of K8sGPTResult objects
            resource_names: Optional list of resource names to match
            namespaces: Optional list of namespaces to match
            kinds: Optional list of resource kinds to match
        
        Returns:
            Filtered list of K8sGPTResult objects
        """
        filtered = results
        
        if resource_names:
            resource_names_lower = [name.lower() for name in resource_names]
            filtered = [
                r for r in filtered
                if any(name in r.details.get('resource_name', '').lower() for name in resource_names_lower)
            ]
        
        if namespaces:
            namespaces_lower = [ns.lower() for ns in namespaces]
            filtered = [
                r for r in filtered
                if r.namespace.lower() in namespaces_lower
            ]
        
        if kinds:
            kinds_lower = [k.lower() for k in kinds]
            filtered = [
                r for r in filtered
                if r.kind.lower() in kinds_lower
            ]
        
        return filtered
    
    def sort_by_severity(self, results: List[K8sGPTResult]) -> List[K8sGPTResult]:
        """
        Sort results by severity (high → medium → low).
        
        Args:
            results: List of K8sGPTResult objects
        
        Returns:
            Sorted list of K8sGPTResult objects
        """
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        return sorted(results, key=lambda r: severity_order.get(r.severity, 3))
