"""
K8sGPT MCP Client for Kubernetes error analysis and diagnosis.

This module provides integration with K8sGPT MCP server to analyze and diagnose
Kubernetes errors with AI-powered insights.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class K8sGPTAnalysis:
    """K8sGPT analysis result for a Kubernetes error"""
    error_id: str
    resource_kind: str
    resource_name: str
    namespace: str
    error_message: str
    analysis: str  # AI-powered analysis
    solutions: List[str]  # Suggested solutions
    severity: str  # "info", "warning", "error", "critical"
    timestamp: datetime
    metadata: Dict[str, Any]  # Additional context


class K8sGPTMCPClient:
    """
    Client for K8sGPT MCP server integration.

    Provides AI-powered analysis of Kubernetes errors by calling K8sGPT MCP server
    to get detailed diagnostics and solutions.
    """

    def __init__(
        self,
        mcp_server_url: str = "http://k8sgpt-mcp.devops-tools.svc:8080",
        timeout: int = 15,
        enabled: Optional[bool] = None
    ):
        """
        Initialize K8sGPT MCP client.

        Args:
            mcp_server_url: URL of K8sGPT MCP server
            timeout: Request timeout in seconds
            enabled: Override auto-detection of K8sGPT availability
        """
        self.mcp_server_url = mcp_server_url
        self.timeout = timeout
        self.error_message: Optional[str] = None
        self.enabled = enabled if enabled is not None else self._check_server_availability()

        if self.enabled:
            logger.info(f"K8sGPT MCP client enabled at {self.mcp_server_url}")
        else:
            error_details = self.error_message or "server not available"
            logger.info(f"K8sGPT MCP client disabled - {error_details}")

    def _check_server_availability(self) -> bool:
        """
        Check if K8sGPT MCP server is available.

        Returns:
            True if server is reachable, False otherwise
        """
        try:
            response = requests.get(
                f"{self.mcp_server_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                return True
            else:
                self.error_message = f"K8sGPT MCP server returned status {response.status_code}"
                logger.debug(self.error_message)
                return False
        except requests.exceptions.Timeout:
            self.error_message = f"K8sGPT MCP server at {self.mcp_server_url} timed out (exceeded 5s)"
            logger.debug(self.error_message)
            return False
        except requests.exceptions.ConnectionError as e:
            self.error_message = f"Cannot connect to K8sGPT MCP at {self.mcp_server_url}: {str(e)}"
            logger.debug(self.error_message)
            return False
        except Exception as e:
            self.error_message = f"K8sGPT MCP server error: {type(e).__name__}: {str(e)}"
            logger.debug(self.error_message)
            return False

    def analyze_error(
        self,
        error_message: str,
        resource_kind: str,
        resource_name: str,
        namespace: str = "default",
        error_logs: Optional[str] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        explain: bool = True
    ) -> Optional[K8sGPTAnalysis]:
        """
        Analyze a Kubernetes error using K8sGPT.

        Args:
            error_message: The error message to analyze
            resource_kind: Kind of resource (Pod, Deployment, etc.)
            resource_name: Name of the resource
            namespace: Namespace of the resource (default: 'default')
            error_logs: Optional logs from the resource
            events: Optional list of related Kubernetes events
            explain: Enable AI-powered explanation using LLM (default: True)

        Returns:
            K8sGPTAnalysis with diagnosis and solutions or None if failed
        """
        if not self.enabled:
            logger.debug("K8sGPT MCP client disabled, skipping analysis")
            return None

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "analyze",
                "params": {
                    "error_message": error_message,
                    "resource_kind": resource_kind,
                    "resource_name": resource_name,
                    "namespace": namespace,
                    "error_logs": error_logs,
                    "events": events or [],
                    "explain": explain
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json().get("result", {})
                if result:
                    return K8sGPTAnalysis(
                        error_id=result.get("error_id", "unknown"),
                        resource_kind=resource_kind,
                        resource_name=resource_name,
                        namespace=namespace,
                        error_message=error_message,
                        analysis=result.get("analysis", ""),
                        solutions=result.get("solutions", []),
                        severity=result.get("severity", "warning"),
                        timestamp=datetime.utcnow(),
                        metadata=result.get("metadata", {})
                    )
                else:
                    logger.warning("K8sGPT MCP server returned empty result")
                    return None
            else:
                logger.warning(f"K8sGPT MCP server returned {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"K8sGPT MCP server timeout after {self.timeout}s")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Failed to connect to K8sGPT MCP server at {self.mcp_server_url}")
            return None
        except Exception as e:
            logger.warning(f"Failed to analyze error with K8sGPT: {e}")
            return None

    def analyze_pod_error(
        self,
        pod_name: str,
        namespace: str = "default",
        error_message: str = "",
        container_logs: Optional[str] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        explain: bool = True
    ) -> Optional[K8sGPTAnalysis]:
        """
        Analyze a Pod error specifically.

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod (default: 'default')
            error_message: Error message from the pod
            container_logs: Optional container logs
            events: Optional pod events
            explain: Enable AI-powered explanation (default: True)

        Returns:
            K8sGPTAnalysis with diagnosis or None if failed
        """
        return self.analyze_error(
            error_message=error_message,
            resource_kind="Pod",
            resource_name=pod_name,
            namespace=namespace,
            error_logs=container_logs,
            events=events,
            explain=explain
        )

    def analyze_deployment_error(
        self,
        deployment_name: str,
        namespace: str = "default",
        error_message: str = "",
        events: Optional[List[Dict[str, Any]]] = None,
        explain: bool = True
    ) -> Optional[K8sGPTAnalysis]:
        """
        Analyze a Deployment error specifically.

        Args:
            deployment_name: Name of the deployment
            namespace: Namespace of the deployment (default: 'default')
            error_message: Error message from the deployment
            events: Optional deployment events
            explain: Enable AI-powered explanation (default: True)

        Returns:
            K8sGPTAnalysis with diagnosis or None if failed
        """
        return self.analyze_error(
            error_message=error_message,
            resource_kind="Deployment",
            resource_name=deployment_name,
            namespace=namespace,
            events=events,
            explain=explain
        )

    def batch_analyze_errors(
        self,
        errors: List[Dict[str, Any]]
    ) -> List[K8sGPTAnalysis]:
        """
        Analyze multiple errors in batch.

        Args:
            errors: List of error dictionaries with keys:
                   - error_message: The error message
                   - resource_kind: Kind of resource
                   - resource_name: Name of resource
                   - namespace: Namespace (default: 'default')
                   - error_logs: Optional logs
                   - events: Optional events
                   - explain: Optional boolean to enable AI explanation (default: True)

        Returns:
            List of K8sGPTAnalysis results
        """
        results = []
        for error in errors:
            analysis = self.analyze_error(
                error_message=error.get("error_message", ""),
                resource_kind=error.get("resource_kind", "Unknown"),
                resource_name=error.get("resource_name", ""),
                namespace=error.get("namespace", "default"),
                error_logs=error.get("error_logs"),
                events=error.get("events"),
                explain=error.get("explain", True)
            )
            if analysis:
                results.append(analysis)

        return results

    def get_pod_events(
        self,
        pod_name: str,
        namespace: str = "default"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get pod events via K8sGPT MCP.

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod

        Returns:
            List of event dictionaries or None if unavailable
        """
        if not self.enabled:
            return None

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "get_pod_events",
                "params": {
                    "pod_name": pod_name,
                    "namespace": namespace
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json().get("result", {})
                return result.get("events", [])
            return None
        except Exception as e:
            logger.debug(f"Failed to get pod events from K8sGPT MCP: {e}")
            return None

    def get_pod_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        tail_lines: int = 100
    ) -> Optional[str]:
        """
        Get pod logs via K8sGPT MCP.

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod
            container: Optional container name
            tail_lines: Number of lines to retrieve

        Returns:
            Logs string or None if unavailable
        """
        if not self.enabled:
            return None

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "get_pod_logs",
                "params": {
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "container": container,
                    "tail_lines": tail_lines
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json().get("result", {})
                return result.get("logs") or result.get("output")
            return None
        except Exception as e:
            logger.debug(f"Failed to get pod logs from K8sGPT MCP: {e}")
            return None

    def get_deployment_status(
        self,
        deployment_name: str,
        namespace: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """
        Get deployment status via K8sGPT MCP.

        Args:
            deployment_name: Name of deployment
            namespace: Namespace of deployment

        Returns:
            Deployment status dictionary or None if unavailable
        """
        if not self.enabled:
            return None

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "get_deployment_status",
                "params": {
                    "deployment_name": deployment_name,
                    "namespace": namespace
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json().get("result", {})
                return result.get("deployment") or result
            return None
        except Exception as e:
            logger.debug(f"Failed to get deployment status from K8sGPT MCP: {e}")
            return None

    def get_error_patterns(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get common error patterns from K8sGPT knowledge base.

        Returns:
            List of error pattern dictionaries or None if failed
        """
        if not self.enabled:
            return None

        try:
            response = requests.post(
                f"{self.mcp_server_url}/",
                json={
                    "jsonrpc": "2.0",
                    "method": "get_patterns",
                    "params": {},
                    "id": 1
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json().get("result", [])
            else:
                logger.warning(f"Failed to get error patterns: {response.status_code}")
                return None

        except Exception as e:
            logger.warning(f"Failed to get error patterns: {e}")
            return None


def format_k8sgpt_analysis(analysis: K8sGPTAnalysis) -> str:
    """
    Format K8sGPT analysis for inclusion in LLM prompt.

    Args:
        analysis: K8sGPT analysis result

    Returns:
        Formatted string for LLM consumption
    """
    lines = [
        "# K8sGPT Error Analysis",
        f"\n**Resource**: {analysis.resource_kind}/{analysis.resource_name}",
        f"**Namespace**: {analysis.namespace}",
        f"**Severity**: {analysis.severity}",
        f"\n## Error Message",
        analysis.error_message,
        f"\n## AI Analysis",
        analysis.analysis,
    ]

    solutions = getattr(analysis, "solutions", None)
    # Normalize solutions to a safe iterable. If solutions is missing or falsy,
    # use an empty list. If it's not a list/tuple, attempt to coerce it to a list.
    if not solutions:
        solutions = []
    else:
        if not isinstance(solutions, (list, tuple)):
            try:
                solutions = list(solutions)
            except TypeError:
                # Non-iterable (e.g., a Mock); stringify and treat as single solution
                solutions = [str(solutions)]

    if solutions:
        lines.append("\n## Suggested Solutions")
        for i, solution in enumerate(solutions, 1):
            lines.append(f"{i}. {solution}")

    if analysis.metadata:
        lines.append("\n## Additional Context")
        for key, value in analysis.metadata.items():
            lines.append(f"- **{key}**: {value}")

    return "\n".join(lines)
