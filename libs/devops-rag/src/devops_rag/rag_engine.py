"""RAG engine with error tracking and exponential backoff."""

import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from .aws_mcp_client import AWSMCPClient, format_aws_context
from .k8sgpt_mcp_client import K8sGPTMCPClient, format_k8sgpt_analysis
from .api_reference_builder import APIReferenceBuilder

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG (Retrieval-Augmented Generation) engine with error tracking."""

    def __init__(
        self, 
        llm_client: Any, 
        vector_store: Any = None, 
        max_retries: int = 3,
        aws_mcp_client: Optional[AWSMCPClient] = None,
        k8sgpt_mcp_client: Optional[K8sGPTMCPClient] = None,
        cluster_version: Optional[str] = None
    ):
        """Initialize RAG engine.

        Args:
            llm_client: LLM client instance
            vector_store: Vector store instance for semantic search
            max_retries: Maximum number of retries with exponential backoff
            aws_mcp_client: Optional AWS MCP client for EKS context enrichment
            k8sgpt_mcp_client: Optional K8sGPT MCP client for error analysis
            cluster_version: Kubernetes cluster version for API documentation links
        """
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.max_retries = max_retries
        self.aws_mcp_client = aws_mcp_client or AWSMCPClient()
        self.k8sgpt_mcp_client = k8sgpt_mcp_client or K8sGPTMCPClient()
        self.api_reference_builder = APIReferenceBuilder(cluster_version or "v1.28")
        self.errors: List[Dict[str, Any]] = []

    def process_query(
        self,
        query: str,
        context_documents: Optional[List[Dict[str, Any]]] = None,
        cluster_context: Optional[Dict[str, Any]] = None,
        health_monitor_errors: Optional[List[Dict[str, Any]]] = None,
        selected_error: Optional[Dict[str, Any]] = None,
        max_tokens: int = 500,
        is_export: bool = False,
        aws_mcp_client: Optional[AWSMCPClient] = None,
    ) -> Dict[str, Any]:
        """Process a query with RAG pipeline.

        Args:
            query: User query string
            context_documents: Optional list of context documents
            cluster_context: Optional cluster context information
            health_monitor_errors: Optional list of errors from health monitoring
            selected_error: Optional specific error selected by user (triggers K8sGPT analysis)
            max_tokens: Maximum tokens for LLM response (default: 500 for chat)
            is_export: Whether this is for export (uses 2000 tokens if True)

        Returns:
            Dictionary with response and metadata
        """
        self.errors = []  # Reset errors for this query
        response = {
            "query": query,
            "response": "",
            "citations": [],
            "errors": [],
            "metadata": {},
        }

        try:
            active_aws_client = aws_mcp_client or self.aws_mcp_client
            # Enrich selected error with MCP-first context (silent kube fallback)
            if selected_error:
                selected_error = self._enrich_selected_error_context(selected_error)

            # Retrieve relevant documents if vector store available
            if self.vector_store and not context_documents:
                try:
                    context_documents = self._retrieve_documents(query)
                except Exception as e:
                    self._track_error("document_retrieval", str(e), "warning")
                    context_documents = []

            # Get AWS context if on EKS
            aws_context = None
            if active_aws_client and active_aws_client.enabled:
                try:
                    aws_context = active_aws_client.get_cluster_context()
                    if aws_context:
                        logger.info("Retrieved AWS context for EKS cluster")
                        # Add AWS context as a document for LLM
                        aws_doc = {
                            "id": "aws-context",
                            "title": "AWS Infrastructure Context",
                            "content": format_aws_context(aws_context),
                            "type": "aws_context"
                        }
                        if context_documents is None:
                            context_documents = []
                        context_documents.append(aws_doc)
                    else:
                        logger.debug("No AWS context retrieved")
                except Exception as e:
                    self._track_error("aws_context_retrieval", str(e), "warning")
                    logger.warning(f"Failed to retrieve AWS context: {e}")

            # Analyze selected error with K8sGPT if provided
            k8sgpt_analysis = None
            if selected_error and self.k8sgpt_mcp_client and self.k8sgpt_mcp_client.enabled:
                try:
                    k8sgpt_analysis = self.k8sgpt_mcp_client.analyze_error(
                        error_message=selected_error.get("message", ""),
                        resource_kind=selected_error.get("resource_kind", "Unknown"),
                        resource_name=selected_error.get("resource_name", ""),
                        namespace=selected_error.get("namespace", "default"),
                        error_logs=selected_error.get("logs"),
                        events=selected_error.get("events"),
                        explain=selected_error.get("explain", True)
                    )
                    if k8sgpt_analysis:
                        logger.info(f"Retrieved K8sGPT analysis for {selected_error.get('resource_kind')}/{selected_error.get('resource_name')}")
                        # Add K8sGPT analysis as a document for LLM
                        k8sgpt_doc = {
                            "id": "k8sgpt-analysis",
                            "title": "K8sGPT Error Analysis",
                            "content": format_k8sgpt_analysis(k8sgpt_analysis),
                            "type": "k8sgpt_analysis"
                        }
                        if context_documents is None:
                            context_documents = []
                        context_documents.append(k8sgpt_doc)
                    else:
                        logger.debug("No K8sGPT analysis retrieved")
                except Exception as e:
                    self._track_error("k8sgpt_analysis", str(e), "warning")
                    logger.warning(f"Failed to retrieve K8sGPT analysis: {e}")

            # Build prompt with context
            prompt = self._build_prompt(
                query,
                context_documents or [],
                cluster_context,
                aws_context,
                k8sgpt_analysis,
                health_monitor_errors,
            )

            # Determine token limit (2000 for export, 500 for chat)
            token_limit = 2000 if is_export else max_tokens

            # Call LLM with retries
            llm_response = self._call_llm_with_backoff(prompt, token_limit)

            response["response"] = llm_response
            if context_documents:
                response["citations"] = [
                    {
                        "id": doc.get("id"),
                        "title": doc.get("title"),
                        "snippet": doc.get("snippet", doc.get("content", ""))[:200],
                    }
                    for doc in context_documents[:5]
                ]

        except Exception as e:
            self._track_error("query_processing", str(e), "error")
            response["response"] = f"Error processing query: {str(e)}"

        response["errors"] = self.errors
        return response

    def _retrieve_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant documents from vector store.

        Args:
            query: Query string
            top_k: Number of top documents to retrieve

        Returns:
            List of relevant documents
        """
        if not self.vector_store:
            return []

        try:
            # Embed query
            query_embedding = self.llm_client.embed(query)

            # Search vector store
            results = self.vector_store.search(query_embedding, top_k=top_k)

            return results
        except Exception as e:
            self._track_error("document_retrieval", str(e), "warning")
            return []

    def _build_prompt(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        cluster_context: Optional[Dict[str, Any]],
        aws_context: Optional[Any],  # AWSClusterContext or None
        k8sgpt_analysis: Optional[Any],  # K8sGPTAnalysis or None
        health_monitor_errors: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Build LLM prompt with context.

        Args:
            query: User query
            context_documents: Context documents
            cluster_context: Cluster context
            aws_context: AWS context (AWSClusterContext object)
            k8sgpt_analysis: K8sGPT analysis (K8sGPTAnalysis object)
            health_monitor_errors: Health monitor errors

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "You are a DevOps expert assistant. Provide clear, actionable advice.",
            "When recommending solutions, prefer Kubernetes API calls over kubectl commands.",
            "Strongly prefer using the in-cluster K8sGPT MCP server for supported diagnostics and troubleshooting.",
            "If K8sGPT MCP is unavailable or lacks a tool, silently fall back to Kubernetes API data.",
            "",
            "KUBERNETES API DOCUMENTATION:",
        ]

        # Add API documentation links
        api_links = self.api_reference_builder.get_documentation_links()
        prompt_parts.extend([
            f"API Overview: {api_links['api_overview']}",
            f"API Reference ({api_links['cluster_version']}): {api_links['api_reference']}",
            "",
            "Use these links to provide accurate API examples and recommend Python kubernetes client calls.",
            "",
            "CLUSTER CONTEXT:",
        ])

        if cluster_context:
            prompt_parts.append(f"Cluster: {cluster_context.get('cluster_name', 'unknown')}")
            prompt_parts.append(f"Kubernetes Version: {cluster_context.get('cluster_version', 'unknown')}")
            if cluster_context.get("cluster_tools"):
                tools_str = ", ".join(
                    [f"{t.get('name')} {t.get('version')}" for t in cluster_context.get("cluster_tools", [])]
                )
                prompt_parts.append(f"Installed Tools: {tools_str}")

        # AWS context is now handled as a document in context_documents
        # Look for AWS context document
        aws_doc = None
        k8sgpt_doc = None
        other_docs = []
        for doc in context_documents:
            if doc.get("type") == "aws_context":
                aws_doc = doc
            elif doc.get("type") == "k8sgpt_analysis":
                k8sgpt_doc = doc
            else:
                other_docs.append(doc)

        if aws_doc:
            prompt_parts.append("")
            prompt_parts.append("AWS INFRASTRUCTURE CONTEXT:")
            prompt_parts.append(aws_doc.get("content", ""))

        if k8sgpt_doc:
            prompt_parts.append("")
            prompt_parts.append("K8sGPT ERROR ANALYSIS:")
            prompt_parts.append(k8sgpt_doc.get("content", ""))

        if other_docs:
            prompt_parts.append("")
            prompt_parts.append("RELEVANT SOLUTIONS AND PATTERNS:")
            for doc in other_docs[:5]:
                prompt_parts.append(f"- {doc.get('title', 'Unknown')}: {doc.get('snippet', doc.get('content', ''))[:100]}")

        if self.errors:
            prompt_parts.append("")
            prompt_parts.append("ERRORS ENCOUNTERED:")
            for error in self.errors:
                if error.get("severity") == "warning":
                    prompt_parts.append(f"- {error.get('type')}: {error.get('message')}")

        # Include health monitor errors if provided
        if health_monitor_errors:
            prompt_parts.append("")
            prompt_parts.append("CLUSTER MONITORING ERRORS:")
            for error in health_monitor_errors:
                if error.get("severity") == "warning":
                    prompt_parts.append(f"- {error.get('type')}: {error.get('message')}")
                    
            prompt_parts.append("")
            prompt_parts.append("NOTE: Some cluster metrics may be incomplete due to API errors above.")
            prompt_parts.append("Consider these limitations when providing recommendations.")

        prompt_parts.append("")
        prompt_parts.append("USER QUERY:")
        prompt_parts.append(query)
        prompt_parts.append("")
        prompt_parts.append("RESPONSE INSTRUCTIONS:")
        prompt_parts.append("- Provide clear, actionable solutions")
        prompt_parts.append("- Include Python Kubernetes API examples instead of kubectl commands when possible")
        prompt_parts.append("- Reference the API documentation links provided above")
        prompt_parts.append("- Include specific resource URLs from the API reference when relevant")
        prompt_parts.append("")
        prompt_parts.append("RESPONSE:")

        return "\n".join(prompt_parts)

    def _enrich_selected_error_context(self, selected_error: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich selected error with MCP-first context and silent kube fallback.

        Args:
            selected_error: Selected error dictionary

        Returns:
            Updated error dictionary with events/logs when available
        """
        enriched = dict(selected_error)
        resource_kind = (enriched.get("resource_kind") or "").lower()
        namespace = enriched.get("namespace") or "default"
        resource_name = enriched.get("resource_name") or ""

        # Prefer MCP for supported calls
        try:
            if self.k8sgpt_mcp_client and self.k8sgpt_mcp_client.enabled:
                if resource_kind == "pod" and resource_name:
                    if not enriched.get("events"):
                        mcp_events = self.k8sgpt_mcp_client.get_pod_events(resource_name, namespace)
                        if mcp_events:
                            enriched["events"] = mcp_events
                    if not enriched.get("logs"):
                        mcp_logs = self.k8sgpt_mcp_client.get_pod_logs(resource_name, namespace)
                        if mcp_logs:
                            enriched["logs"] = mcp_logs
        except Exception as e:
            logger.debug(f"K8sGPT MCP enrichment failed: {e}")

        # Silent kube fallback if MCP didn't provide data
        try:
            if resource_name:
                if resource_kind == "pod" and not enriched.get("logs"):
                    from devops_k8s.client import K8sClient
                    k8s_client = K8sClient()
                    enriched["logs"] = k8s_client.get_pod_logs(resource_name, namespace, tail_lines=100)

                if not enriched.get("events"):
                    from devops_k8s.event_correlator import EventCorrelator
                    correlator = EventCorrelator()
                    timeline = correlator.get_event_timeline(
                        resource_name=resource_name,
                        namespace=namespace,
                        resource_kind=enriched.get("resource_kind", "Pod"),
                        hours_back=24
                    )
                    enriched["events"] = [
                        {
                            "type": event.type,
                            "reason": event.reason,
                            "message": event.message,
                            "timestamp": event.timestamp.isoformat(),
                            "resource_kind": event.resource_kind,
                            "resource_name": event.resource_name,
                            "namespace": event.namespace
                        }
                        for event in timeline.events
                    ]
        except Exception as e:
            logger.debug(f"Kubernetes fallback enrichment failed: {e}")

        return enriched

    def _call_llm_with_backoff(self, prompt: str, max_tokens: int = 500, initial_delay: float = 1.0) -> str:
        """Call LLM with exponential backoff retry logic.

        Args:
            prompt: Prompt to send to LLM
            max_tokens: Maximum tokens for response
            initial_delay: Initial delay in seconds

        Returns:
            LLM response string
        """
        delay = initial_delay
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return self.llm_client.generate(prompt, max_tokens=max_tokens)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    self._track_error(
                        "llm_call",
                        f"Attempt {attempt + 1} failed: {str(e)}",
                        "warning",
                    )
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

        # All retries failed
        self._track_error("llm_call", f"All {self.max_retries} attempts failed: {str(last_error)}", "error")
        raise last_error

    def _track_error(self, error_type: str, message: str, severity: str = "warning") -> None:
        """Track non-critical errors.

        Args:
            error_type: Type of error
            message: Error message
            severity: Error severity ("warning" or "error")
        """
        self.errors.append(
            {
                "type": error_type,
                "message": message,
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_api_call_example(self, resource_kind: str, operation: str = "get") -> str:
        """Get API call example for a resource.

        Args:
            resource_kind: Kubernetes resource kind (e.g., "Pod", "Deployment")
            operation: Operation type (e.g., "get", "list", "create", "delete")

        Returns:
            Python API call example string
        """
        return self.api_reference_builder.format_api_call_example(resource_kind, operation)

    def get_resource_documentation_url(self, resource_kind: str) -> Optional[str]:
        """Get documentation URL for a specific resource.

        Args:
            resource_kind: Kubernetes resource kind (e.g., "Pod", "Deployment")

        Returns:
            Resource documentation URL or None if not found
        """
        return self.api_reference_builder.get_resource_url(resource_kind)

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get tracked errors.

        Returns:
            List of error dictionaries
        """
        return self.errors
