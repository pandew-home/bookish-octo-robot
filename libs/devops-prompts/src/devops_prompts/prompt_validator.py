"""Prompt validation shared between Headlamp AI and DevOps Chatbot.

Rejects off-topic queries and ensures messages are DevOps/Kubernetes/AWS related.
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PromptValidator:
    """Validates that queries are related to DevOps, AWS, or Kubernetes."""

    DEVOPS_KEYWORDS = [
        "devops", "deployment", "ci/cd", "pipeline", "infrastructure",
        "monitoring", "logging", "alerting", "observability",
        "terraform", "ansible", "chef", "puppet", "infrastructure as code",
        "container", "docker", "kubernetes", "k8s", "helm", "kustomize",
        "gitops", "argocd", "flux", "jenkins", "gitlab", "github actions",
        "aws", "ec2", "s3", "lambda", "ecs", "eks", "rds", "iam", "vpc",
        "azure", "gcp", "cloud", "serverless", "microservices",
        "scaling", "autoscaling", "load balancer", "ingress", "service mesh",
        "security", "rbac", "secrets", "vault", "certificates", "tls",
        "networking", "dns", "service discovery", "api gateway",
        "troubleshoot", "debug", "error", "issue", "problem", "fix",
        "maintenance", "update", "upgrade", "rollback", "backup", "restore",
        "performance", "optimization", "cost", "resource", "quota", "limit",
        "pod", "deployment", "service", "configmap", "secret", "pvc", "pv",
        "namespace", "node", "cluster", "daemonset", "statefulset", "job",
        "cronjob", "replicaset", "ingress", "networkpolicy", "role",
        "clusterrole", "serviceaccount", "persistentvolume", "storageclass",
    ]

    OFF_TOPIC_KEYWORDS = [
        "recipe", "cooking", "food", "restaurant", "movie", "film", "sports",
        "game", "gaming", "music", "song", "weather", "news", "politics",
        "history", "science", "math", "homework", "essay", "writing",
        "creative", "story", "poem", "joke", "jokes", "funny", "entertainment",
        "shopping", "travel", "vacation", "hotel", "flight", "car", "vehicle",
    ]

    REJECTION_MESSAGE = (
        "I am designed to assist with Kubernetes, AWS, and DevOps tasks only. "
        "Please ask questions related to cluster troubleshooting, infrastructure management, "
        "cloud services, or DevOps workflows."
    )

    def __init__(self) -> None:
        self.devops_keywords = [kw.lower() for kw in self.DEVOPS_KEYWORDS]
        self.off_topic_keywords = [kw.lower() for kw in self.OFF_TOPIC_KEYWORDS]

    def validate(self, query: str) -> Tuple[bool, Optional[str]]:
        """Validate that the query is DevOps/AWS/Kubernetes related."""
        query_lower = query.lower()

        for off_topic in self.off_topic_keywords:
            if off_topic in query_lower:
                logger.info(
                    "Query rejected - off-topic keyword detected",
                    extra={"keyword": off_topic, "query": query[:100]},
                )
                return False, self.REJECTION_MESSAGE

        has_devops_keyword = any(keyword in query_lower for keyword in self.devops_keywords)

        if not has_devops_keyword:
            logger.info(
                "Query rejected - no DevOps/AWS/Kubernetes keywords found",
                extra={"query": query[:100]},
            )
            return False, self.REJECTION_MESSAGE

        logger.debug("Query validated successfully", extra={"query": query[:100]})
        return True, None

    def validate_with_context(
        self, query: str, cluster_context: Optional[dict] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate query with optional cluster context for ambiguous asks."""
        if cluster_context:
            context_related_queries = [
                "status", "health", "check", "show", "list", "describe",
                "get", "view", "what", "why", "how", "when", "where",
            ]
            query_lower = query.lower()
            if any(cq in query_lower for cq in context_related_queries):
                logger.debug(
                    "Query validated with cluster context", extra={"query": query[:100]}
                )
                return True, None

        return self.validate(query)
