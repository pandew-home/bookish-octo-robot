"""
Agentic engine: LLM-powered Kubernetes troubleshooting assistant.

Builds a system prompt with K8sGPT findings and knowledge base results,
then makes a single LLM call to summarize and diagnose cluster issues.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Kubernetes troubleshooting assistant with read-only access to this cluster.

## K8sGPT Pre-scan Findings
{k8sgpt_summary}

## Knowledge Base
{kb_summary}

## Rules
- This product is READ-ONLY — suggest fixes but never execute them
- Use real names from the findings above, never placeholders like <name>
- Summarize the findings and provide actionable fix recommendations"""


class AgentEngine:
    """Single-call LLM engine for K8s troubleshooting."""

    def __init__(
        self,
        llm_client: Any,
        k8sgpt_results: Optional[List] = None,
        kb_results: Optional[List] = None,
    ):
        self.llm_client = llm_client
        self.k8sgpt_results = k8sgpt_results or []
        self.kb_results = kb_results or []

    async def run(self, query: str) -> Dict[str, Any]:
        """Run a single LLM call and return the response."""
        system_content = SYSTEM_PROMPT.format(
            k8sgpt_summary=self._format_k8sgpt_summary() or "None available.",
            kb_summary=self._format_kb_results() or "No relevant articles found.",
        )

        messages: List[Any] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        logger.info("[AGENT] Calling LLM...")
        # Pass empty tools list — this is a single-call summarization engine,
        # not a tool-calling loop. generate_with_tools handles [] gracefully.
        result = await asyncio.to_thread(
            self.llm_client.generate_with_tools, messages, []
        )

        response_text = result.get("text", "Unable to generate a response.")
        logger.info(f"[AGENT] Response: {len(response_text)} chars")

        return {
            "response": response_text,
            "errors": [],
        }

    def _format_kb_results(self) -> str:
        if not self.kb_results:
            return ""
        lines = []
        for r in self.kb_results[:5]:
            title = r.get("title", "Untitled")
            content = r.get("content") or r.get("snippet", "")
            truncated = content[:500] + ("..." if len(content) > 500 else "")
            lines.append(f"- {title}: {truncated}")
        return "\n".join(lines)

    def _format_k8sgpt_summary(self) -> str:
        if not self.k8sgpt_results:
            return ""
        lines = []
        for r in self.k8sgpt_results[:10]:
            if hasattr(r, "name"):
                details = r.details if isinstance(r.details, dict) else {}
                resource_name = details.get("resource_name", "")
                raw_errors = details.get("error", [])
                error_detail = ""
                if isinstance(raw_errors, list) and raw_errors:
                    combined = " | ".join(str(e) for e in raw_errors[:3])
                    error_detail = f"\n    raw errors: {combined}"
                ts = r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp)
                lines.append(
                    f"- [{r.severity}] {r.kind}/{resource_name} (ns: {r.namespace}) detected {ts}\n"
                    f"    problem: {r.problem}{error_detail}\n"
                    f"    fix: {r.solution}"
                )
            else:
                details = r.get("details", {}) if isinstance(r.get("details"), dict) else {}
                resource_name = details.get("resource_name", r.get("name", "?"))
                raw_errors = details.get("error", [])
                error_detail = ""
                if isinstance(raw_errors, list) and raw_errors:
                    combined = " | ".join(str(e) for e in raw_errors[:3])
                    error_detail = f"\n    raw errors: {combined}"
                lines.append(
                    f"- [{r.get('severity','?')}] {r.get('kind','?')}/{resource_name} (ns: {r.get('namespace','?')}) detected {r.get('timestamp','?')}\n"
                    f"    problem: {r.get('details','')}{error_detail}\n"
                    f"    fix: {r.get('solution','N/A')}"
                )
        return "\n".join(lines)
