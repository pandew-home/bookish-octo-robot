"""Query routing and type detection."""

from typing import Optional, Tuple
from datetime import datetime, timedelta, UTC
import re


class QueryRouter:
    """Route queries to appropriate templates based on type detection."""

    # Query type keywords
    TROUBLESHOOTING_KEYWORDS = {
        "not working",
        "broken",
        "failing",
        "error",
        "issue",
        "problem",
        "crashed",
        "down",
        "unavailable",
        "timeout",
        "can't",
        "cant",
        "help",
        "fix",
        "troubleshoot",
        "debug",
        "crashloop",
        "oom",
        "pending",
        "stuck",
        "failed",
        "restart",
        "restarting",
        "evicted",
        "terminated",
        "killed",
        "unhealthy",
        "degraded",
        "backoff",
        "imagepullbackoff",
        "errimagepull",
        "connection refused",
        "503",
        "504",
        "502",
        "500",
    }

    ANALYSIS_KEYWORDS = {
        "analyze",
        "review",
        "check",
        "inspect",
        "evaluate",
        "assess",
        "performance",
        "optimize",
        "improve",
        "status",
        "health",
        "report",
        "what changed",
        "show me",
        "list",
        "describe",
        "usage",
        "consumption",
        "capacity",
        "utilization",
        "metrics",
        "monitoring",
        "trends",
        "compare",
        "summary",
        "overview",
    }

    DEPLOYMENT_KEYWORDS = {
        "deployment",
        "deploy",
        "deployed",
        "deploying",
        "configuration",
        "config",
        "misconfigured",
        "values",
        "override",
        "helm",
        "chart",
        "argocd",
        "sync",
        "out of sync",
        "outofsynch",
        "prune",
        "auto-sync",
        "revision",
        "rollout",
        "rolling update",
        "recreate",
        "canary",
        "blue-green",
        "bluegreen",
        "strategy",
        "upgrade",
        "downgrade",
        "rollback",
        "version",
        "release",
    }

    GITOPS_KEYWORDS = {
        "argocd",
        "flux",
        "gitops",
        "git",
        "repository",
        "repo",
        "branch",
        "commit",
        "push",
        "pull",
        "merge",
        "sync",
        "reconcile",
        "drift",
        "out of sync",
        "application",
        "app",
        "kustomize",
        "overlay",
        "base",
        "patch",
        "webhook",
        "notification",
        "notification rule",
    }

    SECURITY_KEYWORDS = {
        "security",
        "rbac",
        "permission",
        "access",
        "authentication",
        "authorization",
        "tls",
        "ssl",
        "certificate",
        "secret",
        "encryption",
        "pod security",
        "securitycontext",
        "runasuser",
        "runasgroup",
        "fsgroup",
        "selinux",
        "apparmor",
        "seccomp",
        "capabilities",
        "privileged",
        "audit",
        "compliance",
        "vulnerability",
        "cve",
        "scan",
    }

    NETWORKING_KEYWORDS = {
        "network",
        "dns",
        "connectivity",
        "latency",
        "throughput",
        "bandwidth",
        "firewall",
        "service mesh",
        "istio",
        "linkerd",
        "cilium",
        "calico",
        "ingress",
        "service",
        "endpoint",
        "load balancer",
        "load balancing",
        "connection",
        "socket",
        "port",
        "protocol",
        "tcp",
        "udp",
        "http",
        "https",
        "grpc",
        "dns resolution",
        "nslookup",
        "dig",
        "ping",
        "traceroute",
        "netstat",
        "tcpdump",
        "packet",
        "route",
        "routing",
        "gateway",
        "proxy",
        "sidecar",
        "virtual service",
        "destination rule",
        "traffic policy",
        "circuit breaker",
        "retry",
        "rate limiting",
        "rate limit",
        "mutual tls",
        "mtls",
        "network policy",
    }

    def detect_query_type(self, query: str) -> str:
        """Detect query type based on keywords.

        Args:
            query: User query string

        Returns:
            Query type: "troubleshooting", "analysis", "deployment", "gitops", "security", "networking", or "general"
        """
        query_lower = query.lower()

        # Special case handling for specific phrases
        if "argocd sync" in query_lower:
            return "gitops"
        if "deployment crashed" in query_lower:
            return "troubleshooting"
        if "network policy" in query_lower:
            return "networking"

        # Count matches for each category to handle overlapping keywords
        scores = {
            "networking": self._count_keywords(query_lower, self.NETWORKING_KEYWORDS),
            "security": self._count_keywords(query_lower, self.SECURITY_KEYWORDS),
            "deployment": self._count_keywords(query_lower, self.DEPLOYMENT_KEYWORDS),
            "gitops": self._count_keywords(query_lower, self.GITOPS_KEYWORDS),
            "troubleshooting": self._count_keywords(query_lower, self.TROUBLESHOOTING_KEYWORDS),
            "analysis": self._count_keywords(query_lower, self.ANALYSIS_KEYWORDS),
        }

        # Find the category with the highest score
        max_score = max(scores.values())
        if max_score == 0:
            return "general"

        # Return the first category with the highest score (priority order)
        for category in ["networking", "security", "deployment", "gitops", "troubleshooting", "analysis"]:
            if scores[category] == max_score:
                return category

        return "general"

    def detect_time_range(self, query: str) -> Optional[Tuple[datetime, datetime]]:
        """Detect time range from query for temporal queries.

        Args:
            query: User query string

        Returns:
            Tuple of (start_time, end_time) or None if no time range detected
        """
        query_lower = query.lower()
        now = datetime.now(UTC)

        # Check for "last X minutes/hours/days"
        match = re.search(r"last\s+(\d+)\s+(minute|hour|day|week|month)s?", query_lower)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit == "minute":
                start_time = now - timedelta(minutes=amount)
            elif unit == "hour":
                start_time = now - timedelta(hours=amount)
            elif unit == "day":
                start_time = now - timedelta(days=amount)
            elif unit == "week":
                start_time = now - timedelta(weeks=amount)
            elif unit == "month":
                start_time = now - timedelta(days=amount * 30)
            else:
                return None

            return (start_time, now)

        # Check for "past X minutes/hours/days"
        match = re.search(r"past\s+(\d+)\s+(minute|hour|day|week|month)s?", query_lower)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit == "minute":
                start_time = now - timedelta(minutes=amount)
            elif unit == "hour":
                start_time = now - timedelta(hours=amount)
            elif unit == "day":
                start_time = now - timedelta(days=amount)
            elif unit == "week":
                start_time = now - timedelta(weeks=amount)
            elif unit == "month":
                start_time = now - timedelta(days=amount * 30)
            else:
                return None

            return (start_time, now)

        # Check for "since X"
        match = re.search(r"since\s+(\d+)\s+(minute|hour|day|week|month)s?\s+ago", query_lower)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit == "minute":
                start_time = now - timedelta(minutes=amount)
            elif unit == "hour":
                start_time = now - timedelta(hours=amount)
            elif unit == "day":
                start_time = now - timedelta(days=amount)
            elif unit == "week":
                start_time = now - timedelta(weeks=amount)
            elif unit == "month":
                start_time = now - timedelta(days=amount * 30)
            else:
                return None

            return (start_time, now)

        return None

    def _has_keywords(self, query: str, keywords: set) -> bool:
        """Check if query contains any keywords from the set.

        Args:
            query: Query string (lowercase)
            keywords: Set of keywords to check

        Returns:
            True if any keyword found in query
        """
        for keyword in keywords:
            if keyword in query:
                return True
        return False

    def _count_keywords(self, query: str, keywords: set) -> int:
        """Count how many keywords from the set are found in the query.

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
