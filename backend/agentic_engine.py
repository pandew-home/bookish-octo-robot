"""
Agentic engine: LLM-powered Kubernetes troubleshooting assistant.

Builds a system prompt with K8sGPT findings and knowledge base results,
then performs a bounded tool-calling loop for live diagnosis.
"""
import asyncio
import json
import logging
import re
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

K8S_CHECK_SKILL_PATH = "/app/backend/skills/k8s-check/SKILL.md"
MAX_TOOL_ITEMS = 50
MAX_TOOL_STRING_CHARS = 2000
MAX_PARALLEL_TOOL_CALLS = 3
MAX_NO_PROGRESS_ROUNDS = 2
MAX_DEDUP_ONLY_ROUNDS = 2
MAX_BLOCKED_ONLY_ROUNDS = 2
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SYSTEM_PROMPT = """You are a Kubernetes troubleshooting assistant with Kubernetes API tool access.

## Kubernetes API Reference
Cluster version: {cluster_version}
API reference: {api_reference_url}

## K8sGPT Pre-scan Findings
{k8sgpt_summary}

## Knowledge Base
{kb_summary}

## Diagnostic Rules
- Diagnose from current Kubernetes API state first, then use K8sGPT findings as supporting signals.
- Treat K8sGPT findings as potentially stale until verified against live resource status/endpoints/events.
- If evidence is incomplete, explicitly say what should be checked via Kubernetes API next.
- Use available tools to inspect and perform Kubernetes API operations allowed by RBAC.
- Use the k8s-check skill at /app/backend/skills/k8s-check/ when broad live-state health checks are needed.
- Execution mode is observe-only by default. Mutating actions require explicit human approval and are not executed in observe-only mode.

## Response Format
1. Live State Assessment
2. Root Cause Hypothesis
3. Remediation Actions (execute if requested and allowed by RBAC)

## Guardrails
- Use real resource names from context; never placeholders like <name>.
- State clearly what was observed via live APIs before taking action.
"""


class AgentEngine:
    """Tool-enabled LLM engine for Kubernetes troubleshooting and actions."""

    def __init__(
        self,
        llm_client: Any,
        k8sgpt_results: Optional[List] = None,
        kb_results: Optional[List] = None,
        k8s_clients: Optional[Dict[str, Any]] = None,
        kb_search_func: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        cluster_version: Optional[str] = None,
        execution_mode: str = "observe-only",
        require_human_approval: bool = True,
    ):
        self.llm_client = llm_client
        self.k8sgpt_results = k8sgpt_results or []
        self.kb_results = kb_results or []
        self.k8s_clients = k8s_clients or {}
        self.kb_search_func = kb_search_func
        self.cluster_version = (cluster_version or "").strip() or "unknown"
        self.execution_mode = (execution_mode or "observe-only").strip().lower()
        if self.execution_mode not in {"observe-only", "execute"}:
            self.execution_mode = "observe-only"
        self.require_human_approval = bool(require_human_approval)

    async def run(self, query: str) -> Dict[str, Any]:
        """Run a tool-calling loop and return the response."""
        system_content = SYSTEM_PROMPT.format(
            k8sgpt_summary=self._format_k8sgpt_summary() or "None available.",
            kb_summary=self._format_kb_results() or "No relevant articles found.",
            cluster_version=self._major_minor_version(self.cluster_version),
            api_reference_url=self._api_reference_url(self.cluster_version),
        )

        messages: List[Any] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]
        tools = self._get_available_tools()
        tool_calls_used = 0
        rounds = 0
        errors: List[str] = []
        stop_reason = ""
        blocked_actions: List[Dict[str, Any]] = []
        dedup_hits = 0
        no_progress_rounds = 0
        dedup_only_rounds = 0
        blocked_only_rounds = 0
        tool_cache: Dict[str, Dict[str, Any]] = {}

        logger.info("[AGENT] Calling LLM with tool access...")
        result: Dict[str, Any] = {}
        while True:
            rounds += 1

            result = await asyncio.to_thread(
                self.llm_client.generate_with_tools,
                messages,
                tools,
            )

            if result.get("type") == "text":
                break

            if result.get("type") != "tool_calls":
                errors.append("Unexpected LLM response type while processing tool calls.")
                break

            tool_calls = result.get("tool_calls", [])
            if not tool_calls:
                break

            tool_calls_used += len(tool_calls)
            outcomes = await self._execute_tool_calls_parallel(tool_calls, tool_cache)

            round_made_progress = False
            round_all_deduped = bool(outcomes)
            round_all_blocked = bool(outcomes)

            for outcome in outcomes:
                tool_name = outcome["tool_name"]
                args = outcome["args"]
                tool_output = outcome["tool_output"]

                if outcome["deduped"]:
                    dedup_hits += 1
                else:
                    round_all_deduped = False

                if outcome["made_progress"]:
                    round_made_progress = True
                    round_all_blocked = False
                elif not outcome["blocked"]:
                    round_all_blocked = False

                if outcome["approval_required"]:
                    blocked_actions.append(
                        {
                            "tool": tool_name,
                            "args": args,
                            "reason": outcome.get("reason", "approval required"),
                        }
                    )

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "TOOL_RESULT "
                            f"{tool_name} "
                            f"args={json.dumps(args, default=str)} "
                            f"result={json.dumps(tool_output, default=str)}"
                        ),
                    }
                )

            if round_made_progress:
                no_progress_rounds = 0
            else:
                no_progress_rounds += 1
                if no_progress_rounds >= MAX_NO_PROGRESS_ROUNDS:
                    stop_reason = "no_progress"
                    errors.append(
                        "Stop condition reached: repeated tool calls produced no new evidence."
                    )
                    break

            if round_all_deduped:
                dedup_only_rounds += 1
                if dedup_only_rounds >= MAX_DEDUP_ONLY_ROUNDS:
                    stop_reason = "dedupe_loop"
                    errors.append(
                        "Stop condition reached: repeated duplicate tool calls without new evidence."
                    )
                    break
            else:
                dedup_only_rounds = 0

            if round_all_blocked:
                blocked_only_rounds += 1
                if blocked_only_rounds >= MAX_BLOCKED_ONLY_ROUNDS:
                    stop_reason = "blocked_loop"
                    errors.append(
                        "Stop condition reached: only blocked/approval-required actions requested repeatedly."
                    )
                    break
            else:
                blocked_only_rounds = 0

        if result.get("type") != "text":
            # Force a final synthesis if the loop ended on tool calls or stop conditions.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "STOP_CONDITION Reached. Provide the best final diagnosis now using gathered evidence. "
                        "If evidence is insufficient, state what should be investigated next."
                    ),
                }
            )
            forced_result = await asyncio.to_thread(
                self.llm_client.generate_with_tools,
                messages,
                [],
            )
            if forced_result.get("type") == "text":
                result = forced_result
                if not stop_reason:
                    stop_reason = "forced_final_synthesis"

        response_text = result.get("text", "Unable to generate a response.")
        logger.info(f"[AGENT] Response: {len(response_text)} chars")

        return {
            "response": response_text,
            "errors": errors,
            "metadata": {
                "tool_calls_used": tool_calls_used,
                "rounds": rounds,
                "tools_available": len(tools),
                "execution_mode": self.execution_mode,
                "human_approval_required": self.require_human_approval,
                "dedup_hits": dedup_hits,
                "stop_reason": stop_reason,
                "blocked_actions": blocked_actions,
            },
        }

    async def _execute_tool_calls_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_cache: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Execute tool calls in parallel with bounded concurrency."""
        semaphore = asyncio.Semaphore(MAX_PARALLEL_TOOL_CALLS)

        async def _run(index: int, tool_call: Dict[str, Any]) -> Dict[str, Any]:
            tool_name = tool_call.get("name", "unknown_tool")
            args = tool_call.get("args", {})
            call_key = self._tool_call_key(tool_name, args)

            if call_key in tool_cache:
                cached = tool_cache[call_key]
                return {
                    "index": index,
                    "tool_name": tool_name,
                    "args": args,
                    "tool_output": {
                        "deduped": True,
                        "cached": True,
                        "tool": tool_name,
                        "result": cached,
                    },
                    "deduped": True,
                    "blocked": False,
                    "approval_required": False,
                    "made_progress": False,
                    "reason": "deduped",
                }

            async with semaphore:
                tool_output = await asyncio.to_thread(self._execute_tool, tool_name, args)

            tool_cache[call_key] = tool_output
            blocked = False
            approval_required = False
            made_progress = False
            reason = ""

            if isinstance(tool_output, dict):
                approval_required = bool(tool_output.get("approval_required"))
                blocked = bool(tool_output.get("blocked")) or approval_required
                reason = str(tool_output.get("reason", ""))
                made_progress = not tool_output.get("error") and not blocked

            return {
                "index": index,
                "tool_name": tool_name,
                "args": args,
                "tool_output": tool_output,
                "deduped": False,
                "blocked": blocked,
                "approval_required": approval_required,
                "made_progress": made_progress,
                "reason": reason,
            }

        tasks = [_run(idx, call) for idx, call in enumerate(tool_calls)]
        outcomes = await asyncio.gather(*tasks)
        outcomes.sort(key=lambda item: item["index"])
        return outcomes

    def _tool_call_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Build a stable dedupe key for tool calls."""
        try:
            normalized = json.dumps(args or {}, sort_keys=True, default=str)
        except Exception:
            normalized = str(args)
        return f"{tool_name}:{normalized}"

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for diagnosis and actions."""
        tools: List[Dict[str, Any]] = []

        if self.k8s_clients.get("core_v1") is not None:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_service_status",
                            "description": "Read Service live status including ClusterIP and endpoints.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "namespace": {"type": "string"},
                                    "name": {"type": "string"},
                                },
                                "required": ["namespace", "name"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "get_pod_status",
                            "description": "Read Pod live status including phase and restart counts.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "namespace": {"type": "string"},
                                    "name": {"type": "string"},
                                },
                                "required": ["namespace", "name"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "list_resource_events",
                            "description": "List recent Kubernetes events in a namespace, optionally filtered by resource name.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "namespace": {"type": "string"},
                                    "resource_name": {"type": "string"},
                                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                                },
                                "required": ["namespace"],
                            },
                        },
                    },
                ]
            )

        if self.k8sgpt_results:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "list_k8sgpt_findings",
                        "description": "List cached K8sGPT findings for cross-checking with live Kubernetes state.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                            },
                        },
                    },
                }
            )

        if self.kb_search_func is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "description": "Search the knowledge base for troubleshooting references.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                            },
                            "required": ["query"],
                        },
                    },
                }
            )

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "k8s_api_request",
                    "description": (
                        "Perform Kubernetes API requests across any API group/version/resource "
                        "using current in-cluster credentials. Authorization is enforced by RBAC."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                            },
                            "version": {
                                "type": "string",
                                "description": "API version, e.g. v1 or v1beta1",
                            },
                            "group": {
                                "type": "string",
                                "description": "API group, empty for core API",
                            },
                            "namespace": {
                                "type": "string",
                                "description": "Namespace for namespaced resources",
                            },
                            "resource": {
                                "type": "string",
                                "description": "Resource plural name, e.g. pods, deployments, customresourcedefinitions",
                            },
                            "name": {
                                "type": "string",
                                "description": "Resource name for single-object requests",
                            },
                            "subresource": {
                                "type": "string",
                                "description": "Optional subresource, e.g. status, scale",
                            },
                            "query": {
                                "type": "object",
                                "description": "Query parameters, e.g. labelSelector, fieldSelector, limit",
                            },
                            "body": {
                                "type": "object",
                                "description": "Request body for create/patch/update/delete",
                            },
                            "content_type": {
                                "type": "string",
                                "description": "Optional content-type header, useful for PATCH",
                            },
                            "max_items": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "description": "Maximum list items returned in the tool result",
                            },
                            "max_string_chars": {
                                "type": "integer",
                                "minimum": 200,
                                "maximum": 10000,
                                "description": "Maximum characters per string field returned",
                            },
                        },
                        "required": ["method", "version", "resource"],
                    },
                },
            }
        )

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "run_k8s_check_skill",
                    "description": "Run a broad Kubernetes health check inspired by /app/backend/skills/k8s-check/. Optional namespace scoping.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
                        },
                    },
                },
            }
        )

        return tools

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return JSON-serializable output."""
        try:
            if name == "get_service_status":
                return self._tool_get_service_status(args)
            if name == "get_pod_status":
                return self._tool_get_pod_status(args)
            if name == "list_resource_events":
                return self._tool_list_resource_events(args)
            if name == "list_k8sgpt_findings":
                return self._tool_list_k8sgpt_findings(args)
            if name == "search_knowledge_base":
                return self._tool_search_knowledge_base(args)
            if name == "k8s_api_request":
                return self._tool_k8s_api_request(args)
            if name == "run_k8s_check_skill":
                return self._tool_run_k8s_check_skill(args)
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.warning("Tool execution failed for %s: %s", name, e)
            return {"error": str(e), "tool": name}

    def _tool_get_service_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        core_v1 = self.k8s_clients.get("core_v1")
        if core_v1 is None:
            return {"error": "Kubernetes CoreV1 client is unavailable."}

        namespace = args.get("namespace")
        name = args.get("name")
        if not namespace or not name:
            return {"error": "namespace and name are required."}

        svc = core_v1.read_namespaced_service(name=name, namespace=namespace)
        endpoints = core_v1.read_namespaced_endpoints(name=name, namespace=namespace)
        endpoint_addresses: List[str] = []
        for subset in endpoints.subsets or []:
            for addr in subset.addresses or []:
                endpoint_addresses.append(addr.ip)

        return {
            "namespace": namespace,
            "name": name,
            "cluster_ip": getattr(svc.spec, "cluster_ip", None),
            "type": getattr(svc.spec, "type", None),
            "ports": [
                {
                    "name": p.name,
                    "port": p.port,
                    "target_port": str(p.target_port),
                    "protocol": p.protocol,
                }
                for p in (svc.spec.ports or [])
            ],
            "endpoints": endpoint_addresses,
        }

    def _tool_get_pod_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        core_v1 = self.k8s_clients.get("core_v1")
        if core_v1 is None:
            return {"error": "Kubernetes CoreV1 client is unavailable."}

        namespace = args.get("namespace")
        name = args.get("name")
        if not namespace or not name:
            return {"error": "namespace and name are required."}

        pod = core_v1.read_namespaced_pod(name=name, namespace=namespace)
        container_statuses = []
        for status in pod.status.container_statuses or []:
            state = status.state.to_dict() if hasattr(status.state, "to_dict") else str(status.state)
            container_statuses.append(
                {
                    "name": status.name,
                    "ready": status.ready,
                    "restart_count": status.restart_count,
                    "state": state,
                }
            )

        return {
            "namespace": namespace,
            "name": name,
            "phase": pod.status.phase,
            "pod_ip": pod.status.pod_ip,
            "node_name": pod.spec.node_name,
            "container_statuses": container_statuses,
        }

    def _tool_list_resource_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        core_v1 = self.k8s_clients.get("core_v1")
        if core_v1 is None:
            return {"error": "Kubernetes CoreV1 client is unavailable."}

        namespace = args.get("namespace")
        if not namespace:
            return {"error": "namespace is required."}

        resource_name = args.get("resource_name")
        limit = int(args.get("limit", 10))
        limit = max(1, min(limit, 20))
        field_selector = f"involvedObject.name={resource_name}" if resource_name else ""
        events = core_v1.list_namespaced_event(namespace=namespace, field_selector=field_selector)

        normalized = []
        for event in events.items[:limit]:
            normalized.append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "object": getattr(event.involved_object, "name", None),
                    "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                }
            )

        return {
            "namespace": namespace,
            "resource_name": resource_name,
            "count": len(normalized),
            "events": normalized,
        }


    def _tool_list_k8sgpt_findings(self, args: Dict[str, Any]) -> Dict[str, Any]:
        severity = args.get("severity")
        limit = int(args.get("limit", 10))
        limit = max(1, min(limit, 20))

        findings = []
        for item in self.k8sgpt_results:
            if hasattr(item, "to_dict"):
                record = item.to_dict()
            elif isinstance(item, dict):
                record = item
            else:
                continue
            if severity and record.get("severity") != severity:
                continue
            findings.append(record)

        return {
            "severity": severity,
            "count": len(findings[:limit]),
            "findings": findings[:limit],
        }

    def _tool_search_knowledge_base(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.kb_search_func is None:
            return {"error": "Knowledge base search is unavailable."}

        query = args.get("query")
        if not query:
            return {"error": "query is required."}

        top_k = int(args.get("top_k", 5))
        top_k = max(1, min(top_k, 10))
        results = self.kb_search_func(query, top_k=top_k)

        normalized = []
        for result in results[:top_k]:
            normalized.append(
                {
                    "title": result.get("title"),
                    "snippet": (result.get("content") or result.get("snippet") or "")[:500],
                    "source": result.get("source", "knowledge-base"),
                }
            )

        return {
            "query": query,
            "count": len(normalized),
            "results": normalized,
        }

    def _tool_k8s_api_request(self, args: Dict[str, Any]) -> Dict[str, Any]:
        core_v1 = self.k8s_clients.get("core_v1")
        if core_v1 is None:
            return {"error": "Kubernetes API client is unavailable."}

        method = str(args.get("method", "")).upper().strip()
        version = str(args.get("version", "")).strip()
        group = str(args.get("group", "")).strip()
        namespace = str(args.get("namespace", "")).strip()
        resource = str(args.get("resource", "")).strip()
        name = str(args.get("name", "")).strip()
        subresource = str(args.get("subresource", "")).strip()
        query = args.get("query") if isinstance(args.get("query"), dict) else {}
        body = args.get("body") if isinstance(args.get("body"), dict) else None
        content_type = str(args.get("content_type", "")).strip()
        max_items = int(args.get("max_items", MAX_TOOL_ITEMS))
        max_string_chars = int(args.get("max_string_chars", MAX_TOOL_STRING_CHARS))

        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return {"error": "method must be one of GET, POST, PUT, PATCH, DELETE"}
        if not version or not resource:
            return {"error": "version and resource are required."}

        if method in MUTATING_METHODS:
            if self.require_human_approval:
                return {
                    "approval_required": True,
                    "blocked": True,
                    "reason": (
                        f"Human approval required for mutating method {method}. "
                        "Action not executed."
                    ),
                    "request": {
                        "method": method,
                        "version": version,
                        "group": group,
                        "namespace": namespace,
                        "resource": resource,
                        "name": name,
                        "subresource": subresource,
                    },
                }
            if self.execution_mode == "observe-only":
                return {
                    "approval_required": False,
                    "blocked": True,
                    "reason": (
                        f"Execution mode is observe-only; mutating method {method} is disabled."
                    ),
                    "request": {
                        "method": method,
                        "version": version,
                        "group": group,
                        "namespace": namespace,
                        "resource": resource,
                        "name": name,
                        "subresource": subresource,
                    },
                }

        base = f"/apis/{group}/{version}" if group else f"/api/{version}"
        path_parts = [base]
        if namespace:
            path_parts.append(f"namespaces/{namespace}")
        path_parts.append(resource)
        if name:
            path_parts.append(name)
        if subresource:
            path_parts.append(subresource)
        path = "/".join(part.strip("/") for part in path_parts if part)
        if not path.startswith("/"):
            path = "/" + path

        api_client = core_v1.api_client
        headers: Dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        elif method == "PATCH":
            headers["Content-Type"] = "application/merge-patch+json"

        response_data, status_code, response_headers = api_client.call_api(
            path,
            method,
            query_params=list(query.items()),
            body=body,
            header_params=headers,
            auth_settings=["BearerToken"],
            response_type="object",
            _return_http_data_only=False,
        )

        limited = self._limit_tool_result(
            response_data,
            max_items=max(1, min(max_items, 200)),
            max_string_chars=max(200, min(max_string_chars, 10000)),
        )

        return {
            "request": {
                "method": method,
                "path": path,
                "query": query,
            },
            "status_code": status_code,
            "response_headers": dict(response_headers),
            "result": limited,
        }

    def _tool_run_k8s_check_skill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        namespace = str(args.get("namespace", "")).strip()
        namespace_scope = namespace if namespace else "all-namespaces"
        return {
            "skill": "k8s-check",
            "skill_path": K8S_CHECK_SKILL_PATH,
            "namespace": namespace_scope,
            "api_reference": self._api_reference_url(self.cluster_version),
            "guidance": (
                "Run the checks defined in the skill file to collect live cluster state "
                "(pods, deployments, events, ingress, nodes, and resource pressure), "
                "then diagnose based on those results."
            ),
        }

    def _major_minor_version(self, version: str) -> str:
        """Normalize a Kubernetes version to major.minor form (e.g., v1.34)."""
        match = re.search(r"v?(\d+)\.(\d+)", version or "")
        if not match:
            return "unknown"
        return f"v{match.group(1)}.{match.group(2)}"

    def _api_reference_url(self, version: str) -> str:
        """Build Kubernetes API reference URL for the current cluster major.minor."""
        major_minor = self._major_minor_version(version)
        if major_minor == "unknown":
            return "https://kubernetes.io/docs/reference/generated/kubernetes-api/"
        return f"https://kubernetes.io/docs/reference/generated/kubernetes-api/{major_minor}/"

    def _limit_tool_result(self, payload: Any, max_items: int, max_string_chars: int) -> Any:
        """Bound tool output size to keep model context manageable."""
        data = deepcopy(payload)

        def _truncate(value: Any) -> Any:
            if isinstance(value, str):
                if len(value) <= max_string_chars:
                    return value
                return value[:max_string_chars] + "...<truncated>"
            if isinstance(value, list):
                truncated_items = [_truncate(item) for item in value[:max_items]]
                if len(value) > max_items:
                    truncated_items.append(
                        {
                            "_truncated": True,
                            "returned": max_items,
                            "total": len(value),
                        }
                    )
                return truncated_items
            if isinstance(value, dict):
                output: Dict[str, Any] = {}
                for key, item in value.items():
                    output[key] = _truncate(item)
                return output
            return value

        return _truncate(data)

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
