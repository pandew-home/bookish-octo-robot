"""
Weather State Calculator

This module calculates cluster health "weather" state based on K8sGPT Result CRDs.
The weather metaphor provides an intuitive visualization of cluster health:
- Sunny: No issues
- Partly Cloudy: Minor warnings
- Cloudy: Multiple warnings or moderate issues
- Rainy: Significant issues
- Stormy: Critical issues

Requirements: 3.2, 3.3, 3.4, 3.5
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import logging

from k8sgpt_reader import K8sGPTResult

logger = logging.getLogger(__name__)


class WeatherState(str, Enum):
    """Cluster health weather states."""
    SUNNY = "sunny"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    STORMY = "stormy"
    UNKNOWN = "unknown"


@dataclass
class K8sGPTResultSummary:
    """
    Summary of a K8sGPT Result for weather display.
    
    Attributes:
        name: Result name
        kind: Resource kind
        namespace: Resource namespace
        severity: Issue severity
        problem: Problem description (truncated)
        timestamp: Result creation time
    """
    name: str
    kind: str
    namespace: str
    severity: str
    problem: str
    timestamp: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ClusterToolInfo:
    """
    Information about installed cluster tools.
    
    Attributes:
        name: Tool name
        version: Tool version
        status: Tool status
    """
    name: str
    version: str
    status: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class WeatherResponse:
    """
    Weather endpoint response.
    
    Attributes:
        weather_state: Current weather state
        cluster_name: Target cluster name
        cluster_version: K8s version
        k8sgpt_result_count: Total Result CRD count
        top_issues: Top 3-5 issues
        cluster_tools: Installed tool versions
        timestamp: Calculation timestamp
    """
    weather_state: WeatherState
    cluster_name: str
    cluster_version: str
    k8sgpt_result_count: int
    top_issues: List[K8sGPTResultSummary]
    cluster_tools: List[ClusterToolInfo]
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'weather_state': self.weather_state.value,
            'cluster_name': self.cluster_name,
            'cluster_version': self.cluster_version,
            'k8sgpt_result_count': self.k8sgpt_result_count,
            'top_issues': [issue.to_dict() for issue in self.top_issues],
            'cluster_tools': [tool.to_dict() for tool in self.cluster_tools],
            'timestamp': self.timestamp.isoformat()
        }


class WeatherCalculator:
    """
    Calculates cluster health weather state based on K8sGPT Results.
    
    Weather classification rules:
    - Sunny: 0 issues
    - Partly Cloudy: 1-2 low severity issues
    - Cloudy: 3-5 low severity OR 1-2 medium severity issues
    - Rainy: 6+ low severity OR 3+ medium severity OR 1 high severity issue
    - Stormy: 2+ high severity issues OR 10+ total issues
    """
    
    def calculate_weather(
        self,
        results: List[K8sGPTResult],
        cluster_name: str,
        cluster_version: str,
        cluster_tools: Optional[List[ClusterToolInfo]] = None
    ) -> WeatherResponse:
        """
        Calculate weather state from K8sGPT Results.
        
        Args:
            results: List of K8sGPTResult objects
            cluster_name: Target cluster name
            cluster_version: Kubernetes version
            cluster_tools: Optional list of installed tools
        
        Returns:
            WeatherResponse with calculated state and top issues
        """
        logger.info(f"Calculating weather for cluster {cluster_name} with {len(results)} results")
        
        # Count issues by severity
        severity_counts = self._count_by_severity(results)
        
        # Calculate weather state
        weather_state = self._determine_weather_state(severity_counts, len(results))
        
        # Get top issues (sorted by severity, limited to 5)
        top_issues = self._get_top_issues(results, limit=5)
        
        # Build response
        response = WeatherResponse(
            weather_state=weather_state,
            cluster_name=cluster_name,
            cluster_version=cluster_version,
            k8sgpt_result_count=len(results),
            top_issues=top_issues,
            cluster_tools=cluster_tools or [],
            timestamp=datetime.utcnow()
        )
        
        logger.info(f"Weather state calculated: {weather_state.value}")
        return response
    
    def _count_by_severity(self, results: List[K8sGPTResult]) -> Dict[str, int]:
        """
        Count results by severity level.
        
        Args:
            results: List of K8sGPTResult objects
        
        Returns:
            Dictionary with counts for each severity level
        """
        counts = {'high': 0, 'medium': 0, 'low': 0}
        
        for result in results:
            severity = result.severity.lower()
            if severity in counts:
                counts[severity] += 1
        
        return counts
    
    def _determine_weather_state(
        self,
        severity_counts: Dict[str, int],
        total_count: int
    ) -> WeatherState:
        """
        Determine weather state based on severity counts.
        
        Args:
            severity_counts: Dictionary with counts for each severity
            total_count: Total number of results
        
        Returns:
            WeatherState enum value
        """
        high_count = severity_counts.get('high', 0)
        medium_count = severity_counts.get('medium', 0)
        low_count = severity_counts.get('low', 0)
        
        # Stormy: 2+ high severity OR 10+ total issues
        if high_count >= 2 or total_count >= 10:
            return WeatherState.STORMY
        
        # Rainy: 1 high severity OR 3+ medium severity OR 6+ low severity
        if high_count >= 1 or medium_count >= 3 or low_count >= 6:
            return WeatherState.RAINY
        
        # Cloudy: 1-2 medium severity OR 3-5 low severity
        if medium_count >= 1 or (low_count >= 3 and low_count <= 5):
            return WeatherState.CLOUDY
        
        # Partly Cloudy: 1-2 low severity
        if low_count >= 1 and low_count <= 2:
            return WeatherState.PARTLY_CLOUDY
        
        # Sunny: 0 issues
        if total_count == 0:
            return WeatherState.SUNNY
        
        # Default to cloudy if we can't determine
        return WeatherState.CLOUDY
    
    def _get_top_issues(
        self,
        results: List[K8sGPTResult],
        limit: int = 5
    ) -> List[K8sGPTResultSummary]:
        """
        Get top issues sorted by severity.
        
        Args:
            results: List of K8sGPTResult objects
            limit: Maximum number of issues to return
        
        Returns:
            List of K8sGPTResultSummary objects
        """
        # Sort by severity (high → medium → low)
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        sorted_results = sorted(
            results,
            key=lambda r: severity_order.get(r.severity.lower(), 3)
        )
        
        # Take top N and convert to summaries
        top_results = sorted_results[:limit]
        
        summaries = []
        for result in top_results:
            # Truncate problem description to 200 characters
            problem = result.problem
            if len(problem) > 200:
                problem = problem[:197] + "..."
            
            summary = K8sGPTResultSummary(
                name=result.name,
                kind=result.kind,
                namespace=result.namespace,
                severity=result.severity,
                problem=problem,
                timestamp=result.timestamp.isoformat() if isinstance(result.timestamp, datetime) else str(result.timestamp)
            )
            summaries.append(summary)
        
        return summaries
    
    def create_error_response(
        self,
        cluster_name: str,
        error_message: str
    ) -> WeatherResponse:
        """
        Create an error weather response when CRD reading fails.
        
        Args:
            cluster_name: Target cluster name
            error_message: Error description
        
        Returns:
            WeatherResponse with UNKNOWN state
        """
        logger.warning(f"Creating error weather response for {cluster_name}: {error_message}")
        
        return WeatherResponse(
            weather_state=WeatherState.UNKNOWN,
            cluster_name=cluster_name,
            cluster_version="unknown",
            k8sgpt_result_count=0,
            top_issues=[],
            cluster_tools=[],
            timestamp=datetime.utcnow()
        )
