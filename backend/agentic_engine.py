"""
Agentic engine: LLM-driven Kubernetes investigation via tool calls.

The LLM decides which K8s APIs to call, executes them via tools, and
iterates until it can produce a final diagnosis + fix recommendations.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from k8s_tools import K8sToolExecutor

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Kubernetes DevOps troubleshooting assistant with live read access to the cluster.

## Cluster
Name: {cluster_name}
Version: {cluster_version}
API reference: {api_ref_url}

Use correct apiVersions in suggested manifests/commands:
- Pods, Services, ConfigMaps, Secrets, Events, Nodes, Namespaces: core/v1
- Deployments, ReplicaSets, DaemonSets, StatefulSets: apps/v1
- CronJobs: batch/v1  |  Ingress: networking.k8s.io/v1
- HPA: autoscaling/v2  |  NetworkPolicy: networking.k8s.io/v1
- RBAC: rbac.authorization.k8s.io/v1

## K8sGPT Pre-scan Findings
{k8sgpt_summary}

## Knowledge Base
{kb_summary}

## Rules
- Call read-only tools freely without asking — list → describe → logs → events until you have a root cause.
- Never guess cluster state; always use the tools.
- Do not give a final answer until you have root cause + concrete fix.

## Investigation Order
1. list_namespaces → list_pods / list_deployments to orient
2. get_pod / get_deployment on anything not Ready
3. get_pod_logs (previous=true for crashed containers)
4. get_events for Warning events
5. Once root cause is clear, write the final answer using the template below

## Response Template
Use this template exactly. Only include bullets/steps you actually observed or need — omit placeholders.

---
**Root Cause**
[One sentence: the specific resource name, namespace, and what is broken]

**Cause(s)**
- [The underlying reason — e.g. missing resource, misconfiguration, version mismatch, exhausted quota]
- [Second cause only if there genuinely is one]

**Evidence**
- [Exact observed fact: resource name, exit code, error string, event reason, or log line — only what you found]

**Fix**

Step 1 — [title]
```
[exact kubectl command, YAML snippet, or manifest field change with real names and values from this cluster]
```

Step 2 — [title] *(add more steps only if required)*
```
[exact command or change]
```

**Verify**
```
[kubectl command to confirm the fix worked]
```
---

Never use placeholders like `<name>` or `your-namespace` — use the real names from the cluster.
Never write "check X" or "ensure Y" without the exact command or change that accomplishes it.

## Available Tools
- list_namespaces
- list_pods(namespace)
- get_pod(pod_name, namespace)
- get_pod_logs(pod_name, namespace, container?, tail_lines?, previous?)
- list_deployments(namespace)
- get_deployment(name, namespace)
- get_events(namespace, resource_name?, limit?)
- list_nodes
"""

MAX_TOOL_ITERATIONS = 15


def _extract_minor_version(cluster_version: str) -> str:
    """Extract vMAJOR.MINOR from a version string like 'v1.34.2-k3s1' or '1.28'."""
    m = re.match(r"v?(\d+\.\d+)", cluster_version)
    return f"v{m.group(1)}" if m else cluster_version


class AgentEngine:
    """Drives K8s investigation via an LLM tool-calling loop."""

    def __init__(
        self,
        k8s_clients: Dict[str, Any],
        llm_client: Any,
        k8sgpt_results: Optional[List] = None,
        kb_results: Optional[List] = None,
        cluster_version: str = "v1.34",
        cluster_name: str = "unknown",
    ):
        self.executor = K8sToolExecutor(k8s_clients)
        self.llm_client = llm_client
        self.k8sgpt_results = k8sgpt_results or []
        self.kb_results = kb_results or []
        self.cluster_version = cluster_version
        self.cluster_name = cluster_name

    async def run(self, query: str) -> Dict[str, Any]:
        """Run the agentic loop and return the final response."""
        minor = _extract_minor_version(self.cluster_version)
        api_ref_url = f"https://kubernetes.io/docs/reference/generated/kubernetes-api/{minor}/"

        system_content = SYSTEM_PROMPT.format(
            cluster_name=self.cluster_name,
            cluster_version=self.cluster_version,
            api_ref_url=api_ref_url,
            k8sgpt_summary=self._format_k8sgpt_summary() or "None available.",
            kb_summary=self._format_kb_results() or "No relevant articles found.",
        )

        messages: List[Any] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]
        tools = self.executor.get_tool_definitions()
        tool_calls_made: List[Dict] = []
        is_anthropic = self.llm_client.__class__.__name__ == "AnthropicClient"

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info(f"[AGENT] Iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

            result = await asyncio.to_thread(
                self.llm_client.generate_with_tools, messages, tools
            )

            if result["type"] == "text":
                logger.info(f"[AGENT] Final answer after {iteration} tool call(s)")
                return {
                    "response": result["text"],
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                    "errors": [],
                }

            # Execute tool calls and append results to messages
            if is_anthropic:
                messages.append({"role": "assistant", "content": result["raw_content"]})
                tool_results = []
                for tc in result["tool_calls"]:
                    logger.info(f"[AGENT] → {tc['name']}({json.dumps(tc['args'])})")
                    tool_result = await asyncio.to_thread(
                        self.executor.execute, tc["name"], tc["args"]
                    )
                    tool_calls_made.append({"tool": tc["name"], "args": tc["args"]})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": tool_result,
                    })
                messages.append({"role": "user", "content": tool_results})
            else:
                # OpenAI format
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in result["tool_calls"]
                    ],
                })
                for tc in result["tool_calls"]:
                    logger.info(f"[AGENT] → {tc['name']}({json.dumps(tc['args'])})")
                    tool_result = await asyncio.to_thread(
                        self.executor.execute, tc["name"], tc["args"]
                    )
                    tool_calls_made.append({"tool": tc["name"], "args": tc["args"]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

        # Hit max iterations — demand a final answer with what was gathered
        logger.warning(f"[AGENT] Max iterations ({MAX_TOOL_ITERATIONS}) reached")
        messages.append({
            "role": "user",
            "content": "Provide your final diagnosis and fix commands based on what you've gathered.",
        })
        result = await asyncio.to_thread(
            self.llm_client.generate_with_tools, messages, []
        )
        return {
            "response": result.get("text", "Unable to complete diagnosis within iteration limit."),
            "tool_calls_made": tool_calls_made,
            "iterations": MAX_TOOL_ITERATIONS,
            "errors": [{"type": "max_iterations", "message": "Hit maximum tool call iterations"}],
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
