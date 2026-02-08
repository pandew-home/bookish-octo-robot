"""Prompt template rendering engine for DevOps Chatbot v2."""

from typing import Dict, List, Any, Optional
from enum import Enum
from jinja2 import Template, Environment, BaseLoader
import sys
import os

# Add libs to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libs', 'devops-prompts', 'src'))

from devops_prompts.template_loader import TemplateLoader


class QueryCategory(Enum):
    """Query categories (must match query_router.py)."""
    POD_ISSUE = "pod_issue"
    DEPLOYMENT_STATUS = "deployment_status"
    SERVICE_NETWORKING = "service_networking"
    NODE_HEALTH = "node_health"
    STORAGE = "storage"
    ARGOCD = "argocd"
    SECURITY = "security"
    GENERAL_HEALTH = "general_health"
    KB_SEARCH = "kb_search"


class TemplateEngine:
    """Renders structured prompts from templates and context."""

    def __init__(self, templates_path: str = "/data/knowledge-base/templates"):
        """Initialize template engine.

        Args:
            templates_path: Path to templates directory
        """
        self.template_loader = TemplateLoader(templates_path)
        self.jinja_env = Environment(loader=BaseLoader())
        
        # Template selection mapping
        self.category_template_map = {
            QueryCategory.DEPLOYMENT_STATUS: "deployment",
            QueryCategory.SERVICE_NETWORKING: "networking",
            QueryCategory.SECURITY: "security",
            QueryCategory.ARGOCD: "gitops",
            QueryCategory.POD_ISSUE: "troubleshooting",
            QueryCategory.NODE_HEALTH: "troubleshooting",
            QueryCategory.STORAGE: "troubleshooting",
            QueryCategory.GENERAL_HEALTH: "analysis",
            QueryCategory.KB_SEARCH: "general",
        }

    def get_template_for_category(self, category: QueryCategory) -> str:
        """Get appropriate template name for query category.

        Args:
            category: Query category from router

        Returns:
            Template name to use
        """
        return self.category_template_map.get(category, "troubleshooting")

    def render(
        self,
        query_category: str,
        cluster_context: Dict[str, Any],
        kb_results: List[Dict[str, Any]],
        query: str,
        cluster_name: str,
        k8sgpt_results: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Render a structured prompt from template and context.

        Args:
            query_category: Query category (e.g., "troubleshooting", "deployment")
            cluster_context: Enriched cluster data from K8s/AWS APIs
            kb_results: Knowledge base search results
            query: User's original query
            cluster_name: Name of the target cluster
            k8sgpt_results: K8sGPT Result CRDs (optional)

        Returns:
            Rendered prompt string
        """
        # Get template for category
        template_data = self.template_loader.get_template(query_category)

        # Build system prompt
        system_prompt = self._build_system_prompt(template_data)

        # Build context section
        context_section = self._build_context_section(
            cluster_name=cluster_name,
            cluster_context=cluster_context,
            k8sgpt_results=k8sgpt_results,
            kb_results=kb_results
        )

        # Build final prompt
        prompt = f"""{system_prompt}

{context_section}

User Query: {query}

Please provide a response following the specified output format."""

        return prompt

    def _build_system_prompt(self, template_data: Dict[str, Any]) -> str:
        """Build system prompt from template data.

        Args:
            template_data: Template dictionary

        Returns:
            System prompt string
        """
        system_rules = template_data.get("system_rules", "")
        constraints = template_data.get("constraints", "")
        output_format = template_data.get("output_format", "")

        system_prompt = f"""System Rules:
{system_rules}

Constraints:
{constraints}

Output Format:
{output_format}"""

        return system_prompt

    def _build_context_section(
        self,
        cluster_name: str,
        cluster_context: Dict[str, Any],
        k8sgpt_results: Optional[List[Dict[str, Any]]],
        kb_results: List[Dict[str, Any]]
    ) -> str:
        """Build context section with cluster data, K8sGPT findings, and KB results.

        Args:
            cluster_name: Name of the target cluster
            cluster_context: Enriched cluster data
            k8sgpt_results: K8sGPT Result CRDs
            kb_results: Knowledge base search results

        Returns:
            Context section string
        """
        sections = []

        # Cluster information
        sections.append(f"Cluster: {cluster_name}")

        # K8sGPT findings (if available)
        if k8sgpt_results:
            k8sgpt_section = self._format_k8sgpt_results(k8sgpt_results)
            sections.append(f"\nK8sGPT Findings:\n{k8sgpt_section}")

        # Cluster context (enriched data)
        context_section = self._format_cluster_context(cluster_context)
        sections.append(f"\nCluster Context:\n{context_section}")

        # Knowledge base results
        kb_section = self._format_kb_results(kb_results)
        sections.append(f"\nRelevant Knowledge Base Articles:\n{kb_section}")

        return "\n".join(sections)

    def _format_k8sgpt_results(self, k8sgpt_results: List[Dict[str, Any]]) -> str:
        """Format K8sGPT Result CRDs for prompt.

        Args:
            k8sgpt_results: List of K8sGPT Result CRDs

        Returns:
            Formatted string
        """
        if not k8sgpt_results:
            return "No K8sGPT findings available."

        formatted = []
        for idx, result in enumerate(k8sgpt_results[:5], 1):  # Limit to top 5
            severity = result.get("severity", "unknown")
            kind = result.get("kind", "unknown")
            name = result.get("name", "unknown")
            problem = result.get("problem", "No problem description")
            solution = result.get("solution", "No solution provided")

            formatted.append(
                f"{idx}. [{severity.upper()}] {kind}/{name}\n"
                f"   Problem: {problem}\n"
                f"   Suggested Solution: {solution}"
            )

        return "\n".join(formatted)

    def _format_cluster_context(self, cluster_context: Dict[str, Any]) -> str:
        """Format enriched cluster context for prompt.

        Args:
            cluster_context: Enriched cluster data

        Returns:
            Formatted string
        """
        formatted = []

        # Format each context category
        for category, data in cluster_context.items():
            if not data:
                continue

            formatted.append(f"\n{category.replace('_', ' ').title()}:")

            if isinstance(data, dict):
                for key, value in data.items():
                    formatted.append(f"  {key}: {value}")
            elif isinstance(data, list):
                for item in data[:10]:  # Limit to 10 items per category
                    if isinstance(item, dict):
                        # Format dict items
                        item_str = ", ".join(f"{k}={v}" for k, v in item.items())
                        formatted.append(f"  - {item_str}")
                    else:
                        formatted.append(f"  - {item}")
            else:
                formatted.append(f"  {data}")

        return "\n".join(formatted) if formatted else "No additional cluster context available."

    def _format_kb_results(self, kb_results: List[Dict[str, Any]]) -> str:
        """Format knowledge base results for prompt.

        Args:
            kb_results: Knowledge base search results

        Returns:
            Formatted string with citations
        """
        if not kb_results:
            return "No relevant knowledge base articles found."

        formatted = []
        for idx, result in enumerate(kb_results, 1):
            title = result.get("title", "Untitled")
            content = result.get("content", "No content")
            similarity = result.get("similarity_score", 0.0)
            tags = result.get("tags", [])

            formatted.append(
                f"{idx}. {title} (relevance: {similarity:.2f})\n"
                f"   Tags: {', '.join(tags) if tags else 'None'}\n"
                f"   Content: {content[:200]}..."  # Truncate long content
            )

        return "\n".join(formatted)

    def validate_templates(self) -> tuple[bool, Optional[str]]:
        """Validate that all required templates can be loaded.

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_templates = [
            "troubleshooting",
            "deployment",
            "networking",
            "security",
            "gitops",
            "general"
        ]

        for template_type in required_templates:
            try:
                template_data = self.template_loader.get_template(template_type)
                if not template_data:
                    return False, f"Template '{template_type}' is empty"

                # Check required fields
                required_fields = ["system_rules", "constraints", "output_format"]
                for field in required_fields:
                    if field not in template_data:
                        return False, f"Template '{template_type}' missing field '{field}'"

            except Exception as e:
                return False, f"Failed to load template '{template_type}': {str(e)}"

        return True, None
