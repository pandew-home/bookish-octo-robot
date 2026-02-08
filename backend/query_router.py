"""
Query routing and classification for DevOps Chatbot v2.
"""
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta
import re
import logging

from input_sanitizer import InputSanitizer

logger = logging.getLogger(__name__)


class QueryCategory(Enum):
    """Query categories for routing and enrichment."""
    POD_ISSUE = "pod_issue"
    DEPLOYMENT_STATUS = "deployment_status"
    SERVICE_NETWORKING = "service_networking"
    NODE_HEALTH = "node_health"
    STORAGE = "storage"
    ARGOCD = "argocd"
    SECURITY = "security"
    GENERAL_HEALTH = "general_health"
    KB_SEARCH = "kb_search"


@dataclass
class EnrichmentPlan:
    """Plan for enriching a query with cluster context."""
    categories: List[QueryCategory]
    resource_names: List[str]
    namespaces: List[str]
    include_k8sgpt_results: bool = True
    include_aws_context: bool = False
    time_range: Optional[timedelta] = None


class QueryRouter:
    """
    Route queries to appropriate enrichment strategies based on deterministic pattern matching.
    
    This router uses keyword-based classification with priority ordering to determine
    which Kubernetes/AWS APIs to call for context enrichment.
    """
    
    # Category keywords with priority ordering
    POD_KEYWORDS = {
        "pod", "pods", "container", "containers",
        "crashloop", "crashloopbackoff", "oom", "out of memory",
        "pending", "evicted", "imagepullbackoff", "errimagepull",
        "restart", "restarting", "terminated", "killed",
        "not working", "broken", "failing", "crashed"
    }
    
    DEPLOYMENT_KEYWORDS = {
        "deployment", "deployments", "rollout", "rolling update",
        "helm", "chart", "release", "replicas", "scaling",
        "hpa", "horizontal pod autoscaler", "rollback",
        "revision", "upgrade", "downgrade"
    }
    
    SERVICE_NETWORKING_KEYWORDS = {
        "service", "services", "ingress", "load balancer", "alb", "nlb",
        "network", "networking", "dns", "connectivity", "timeout",
        "connection refused", "502", "503", "504", "500",
        "latency", "slow", "unreachable", "cannot connect"
    }
    
    NODE_KEYWORDS = {
        "node", "nodes", "notready", "capacity", "resources",
        "drain", "cordon", "taint", "kubelet", "disk pressure",
        "memory pressure", "pid pressure"
    }
    
    STORAGE_KEYWORDS = {
        "pvc", "persistentvolumeclaim", "volume", "storage",
        "disk", "mount", "unmount", "storage class",
        "persistent volume", "pv"
    }
    
    ARGOCD_KEYWORDS = {
        "argocd", "argo", "sync", "out of sync", "outofsynch",
        "degraded", "prune", "auto-sync", "gitops",
        "application", "app sync"
    }
    
    SECURITY_KEYWORDS = {
        "rbac", "role", "rolebinding", "clusterrole",
        "permission", "access", "forbidden", "unauthorized",
        "serviceaccount", "secret", "certificate", "tls", "ssl",
        "policy", "network policy", "pod security"
    }
    
    AWS_KEYWORDS = {
        "aws", "ec2", "elb", "alb", "nlb", "iam", "vpc",
        "security group", "subnet", "route53", "load balancer"
    }
    
    # Priority order (first match wins if scores are equal)
    CATEGORY_PRIORITY = [
        QueryCategory.SERVICE_NETWORKING,
        QueryCategory.DEPLOYMENT_STATUS,
        QueryCategory.ARGOCD,
        QueryCategory.POD_ISSUE,
        QueryCategory.SECURITY,
        QueryCategory.STORAGE,
        QueryCategory.NODE_HEALTH,
        QueryCategory.GENERAL_HEALTH
    ]
    
    def __init__(self):
        """Initialize the query router."""
        self.sanitizer = InputSanitizer()
    
    def classify(self, query: str, k8sgpt_results: Optional[List] = None) -> EnrichmentPlan:
        """
        Classify query and create enrichment plan.
        
        Args:
            query: User query string
            k8sgpt_results: Optional K8sGPT results for context
            
        Returns:
            EnrichmentPlan with categories and enrichment strategy
            
        Raises:
            ValueError: If query is invalid or unsafe
        """
        # Validate query first
        is_valid, error = self.sanitizer.validate_query(query)
        if not is_valid:
            logger.warning(f"Invalid query blocked: {error}")
            raise ValueError(error)
        
        query_lower = query.lower()
        
        # Extract resource names
        resources = self.sanitizer.extract_resource_names(query)
        
        # Score each category
        scores = {
            QueryCategory.POD_ISSUE: self._count_keywords(query_lower, self.POD_KEYWORDS),
            QueryCategory.DEPLOYMENT_STATUS: self._count_keywords(query_lower, self.DEPLOYMENT_KEYWORDS),
            QueryCategory.SERVICE_NETWORKING: self._count_keywords(query_lower, self.SERVICE_NETWORKING_KEYWORDS),
            QueryCategory.NODE_HEALTH: self._count_keywords(query_lower, self.NODE_KEYWORDS),
            QueryCategory.STORAGE: self._count_keywords(query_lower, self.STORAGE_KEYWORDS),
            QueryCategory.ARGOCD: self._count_keywords(query_lower, self.ARGOCD_KEYWORDS),
            QueryCategory.SECURITY: self._count_keywords(query_lower, self.SECURITY_KEYWORDS),
        }
        
        # Determine primary categories (all with max score)
        max_score = max(scores.values())
        
        if max_score == 0:
            # No specific category, use general health
            categories = [QueryCategory.GENERAL_HEALTH]
        else:
            # Get categories with max score in priority order
            categories = [
                cat for cat in self.CATEGORY_PRIORITY
                if cat in scores and scores[cat] == max_score
            ]
        
        # Check if AWS context is needed
        include_aws = self._count_keywords(query_lower, self.AWS_KEYWORDS) > 0
        
        # Detect time range
        time_range = self._detect_time_range(query)
        
        # Build enrichment plan
        plan = EnrichmentPlan(
            categories=categories,
            resource_names=resources.get('pods', []) + resources.get('deployments', []) + resources.get('services', []),
            namespaces=resources.get('namespaces', []),
            include_k8sgpt_results=True,
            include_aws_context=include_aws,
            time_range=time_range
        )
        
        logger.info(f"Classified query into categories: {[c.value for c in categories]}")
        
        return plan
    
    def _count_keywords(self, query: str, keywords: set) -> int:
        """
        Count how many keywords from the set are found in the query.
        
        Args:
            query: Query string (lowercase)
            keywords: Set of keywords to check
            
        Returns:
            Number of keywords found
        """
        count = 0
        for keyword in keywords:
            if keyword in query:
                count += 1
        return count
    
    def _detect_time_range(self, query: str) -> Optional[timedelta]:
        """
        Detect time range from query for temporal queries.
        
        Args:
            query: User query string
            
        Returns:
            timedelta for the time range, or None if no time range detected
        """
        query_lower = query.lower()
        
        # Check for "last X minutes/hours/days"
        patterns = [
            (r"last\s+(\d+)\s+(minute|hour|day|week)s?", 1),
            (r"past\s+(\d+)\s+(minute|hour|day|week)s?", 1),
            (r"(\d+)\s+(minute|hour|day|week)s?\s+ago", 1),
        ]
        
        for pattern, _ in patterns:
            match = re.search(pattern, query_lower)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                
                if unit == "minute":
                    return timedelta(minutes=amount)
                elif unit == "hour":
                    return timedelta(hours=amount)
                elif unit == "day":
                    return timedelta(days=amount)
                elif unit == "week":
                    return timedelta(weeks=amount)
        
        # Check for relative time keywords
        if "recently" in query_lower or "just now" in query_lower:
            return timedelta(minutes=15)
        
        if "today" in query_lower:
            return timedelta(hours=24)
        
        if "this week" in query_lower:
            return timedelta(weeks=1)
        
        return None
    
    def get_enrichment_summary(self, plan: EnrichmentPlan) -> str:
        """
        Get a human-readable summary of the enrichment plan.
        
        Args:
            plan: Enrichment plan
            
        Returns:
            Summary string
        """
        parts = []
        
        parts.append(f"Categories: {', '.join([c.value for c in plan.categories])}")
        
        if plan.resource_names:
            parts.append(f"Resources: {', '.join(plan.resource_names[:5])}")
        
        if plan.namespaces:
            parts.append(f"Namespaces: {', '.join(plan.namespaces)}")
        
        if plan.include_aws_context:
            parts.append("AWS context: enabled")
        
        if plan.time_range:
            parts.append(f"Time range: last {plan.time_range}")
        
        return " | ".join(parts)
