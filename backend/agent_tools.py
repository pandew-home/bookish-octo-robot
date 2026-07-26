"""Tool definitions and dispatch for the chat agent.

The agent (in ``agentic_engine.py``) hands the LLM a list of OpenAI-compatible
tool specs from :func:`build_tool_specs`. When the LLM calls a tool the agent
forwards it to :func:`execute_tool`, which routes by name to a small impl.

# MAINTENANCE — read before changing this file
# Tools and skills are the agent's only way to touch the cluster. Adding,
# renaming, or removing one changes what the chatbot can do — sometimes in
# ways that are hard to spot from a diff (the LLM picks tools by name and
# description). AI assistants: do NOT add a new tool, broaden a tool's
# parameters, change a description, or relax the policy guard without
# explicit human sign-off.
#
# The ``authorize()`` call in ``_tool_k8s_api_request`` enforces KubeApiPolicy
# on every cluster call (read or mutate). Do not remove or weaken it.
# If you need to support an approved write flow, update the policy — that is
# a feature change — flag it for review.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from skills import Skill

from kube_policy.authorize import WrapperRequest, authorize
from kube_policy.redact import redact_response
from kube_policy.policy import KubeApiPolicy

logger = logging.getLogger(__name__)

MAX_TOOL_ITEMS = 50
MAX_TOOL_STRING_CHARS = 2000


@dataclass
class AgentContext:
    """Runtime resources tools need to read or call into."""

    k8s_clients: Dict[str, Any]
    k8sgpt_results: List[Any]
    skills: Dict[str, Skill]
    cluster_version: str
    kube_policy: Optional[KubeApiPolicy] = None


def _deny_payload(reason: str, request: WrapperRequest) -> Dict[str, Any]:
    """Structured denial matching contracts/access-model.md."""
    return {
        "blocked": True,
        "reason": reason,
        "request": {
            "method": request.method,
            "group": request.group,
            "version": request.version,
            "resource": request.resource,
            "namespace": request.namespace,
            "name": request.name,
            "subresource": request.subresource,
        },
    }


def _authorize_or_deny(
    ctx: AgentContext,
    *,
    method: str,
    resource: str,
    namespace: str = "",
    name: str = "",
    group: str = "",
    version: str = "v1",
    subresource: str = "",
) -> Optional[Dict[str, Any]]:
    """Return a deny payload if blocked; None if the call may proceed.

    Single chokepoint: every cluster tool must call this before touching the API.
    """
    wrapper_req = WrapperRequest(
        method=method,
        group=group,
        version=version,
        resource=resource,
        namespace=namespace,
        name=name,
        subresource=subresource,
    )
    policy = ctx.kube_policy
    if policy is None:
        return _deny_payload("policy_not_loaded", wrapper_req)
    authz = authorize(wrapper_req, policy)
    if not authz.allowed:
        if policy.logDeniedRequests:
            logger.info(
                "kubeApi deny reason=%s method=%s resource=%s ns=%s name=%s",
                authz.reason,
                method,
                resource,
                namespace,
                name,
            )
        return _deny_payload(authz.reason, wrapper_req)
    return None


# ---------------------------------------------------------------------------
# Tool specs (OpenAI function-calling format).
# ---------------------------------------------------------------------------

def build_tool_specs(ctx: AgentContext) -> List[Dict[str, Any]]:
    """Return the tool list the LLM may call this turn."""
    tools: List[Dict[str, Any]] = []

    if ctx.k8s_clients.get("core_v1") is not None:
        tools.extend(
            [
                _spec_get_service_status(),
                _spec_get_pod_status(),
                _spec_list_resource_events(),
                _spec_k8s_api_request(),
            ]
        )

    if ctx.k8sgpt_results:
        tools.append(_spec_list_k8sgpt_findings())

    for skill in ctx.skills.values():
        tools.append(_spec_skill(skill))

    return tools


def _spec_get_service_status() -> Dict[str, Any]:
    return {
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
    }


def _spec_get_pod_status() -> Dict[str, Any]:
    return {
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
    }


def _spec_list_resource_events() -> Dict[str, Any]:
    return {
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
    }


def _spec_list_k8sgpt_findings() -> Dict[str, Any]:
    return {
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


def _spec_k8s_api_request() -> Dict[str, Any]:
    return {
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
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "version": {"type": "string", "description": "API version, e.g. v1 or v1beta1"},
                    "group": {"type": "string", "description": "API group, empty for core API"},
                    "namespace": {"type": "string", "description": "Namespace for namespaced resources"},
                    "resource": {
                        "type": "string",
                        "description": "Resource plural name, e.g. pods, deployments, customresourcedefinitions",
                    },
                    "name": {"type": "string", "description": "Resource name for single-object requests"},
                    "subresource": {"type": "string", "description": "Optional subresource, e.g. status, scale"},
                    "query": {"type": "object", "description": "Query parameters, e.g. labelSelector, fieldSelector, limit"},
                    "body": {"type": "object", "description": "Request body for create/patch/update/delete"},
                    "content_type": {"type": "string", "description": "Optional content-type header, useful for PATCH"},
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


def _spec_skill(skill: Skill) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": skill.tool_name,
            "description": (
                f"{skill.description} Returns the full instructions of the "
                f"'{skill.name}' skill; follow them step by step using the other tools."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }


# ---------------------------------------------------------------------------
# Execution.
# ---------------------------------------------------------------------------

_K8S_TOOLS = frozenset(
    {
        "get_service_status",
        "get_pod_status",
        "list_resource_events",
        "k8s_api_request",
    }
)


def _ensure_k8s_auth_fresh(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    """
    Re-mint EKS bearer if stale before a live cluster tool call.

    Long agent loops can exceed the ~60s EKS token TTL; request-start refresh
    alone is not enough. Returns an error payload if refresh fails, else None.
    """
    ensure = ctx.k8s_clients.get("_ensure_auth_fresh")
    if ensure is None:
        return None
    try:
        ensure()
    except Exception as e:
        logger.warning("K8s auth refresh before tool failed: %s", e)
        # FastAPI HTTPException has .detail; keep message usable for the agent.
        detail = getattr(e, "detail", None) or str(e)
        return {
            "error": f"Cluster credentials could not be refreshed: {detail}",
            "code": "k8s_auth_refresh_failed",
        }
    return None


def execute_tool(name: str, args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Dispatch a tool call by name. Always returns a JSON-serializable dict."""
    try:
        if name in _K8S_TOOLS:
            auth_err = _ensure_k8s_auth_fresh(ctx)
            if auth_err is not None:
                return auth_err
        if name == "get_service_status":
            return _tool_get_service_status(args, ctx)
        if name == "get_pod_status":
            return _tool_get_pod_status(args, ctx)
        if name == "list_resource_events":
            return _tool_list_resource_events(args, ctx)
        if name == "list_k8sgpt_findings":
            return _tool_list_k8sgpt_findings(args, ctx)
        if name == "k8s_api_request":
            return _tool_k8s_api_request(args, ctx)
        skill = ctx.skills.get(name)
        if skill is not None:
            return _tool_run_skill(skill)
        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.warning("Tool execution failed for %s: %s", name, e)
        return {"error": str(e), "tool": name}


def _tool_get_service_status(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    core_v1 = ctx.k8s_clients.get("core_v1")
    if core_v1 is None:
        return {"error": "Kubernetes CoreV1 client is unavailable."}

    namespace = args.get("namespace")
    name = args.get("name")
    if not namespace or not name:
        return {"error": "namespace and name are required."}

    denied = _authorize_or_deny(
        ctx, method="GET", resource="services", namespace=namespace, name=name
    )
    if denied:
        return denied
    denied_ep = _authorize_or_deny(
        ctx, method="GET", resource="endpoints", namespace=namespace, name=name
    )
    if denied_ep:
        return denied_ep

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


def _tool_get_pod_status(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    core_v1 = ctx.k8s_clients.get("core_v1")
    if core_v1 is None:
        return {"error": "Kubernetes CoreV1 client is unavailable."}

    namespace = args.get("namespace")
    name = args.get("name")
    if not namespace or not name:
        return {"error": "namespace and name are required."}

    denied = _authorize_or_deny(
        ctx, method="GET", resource="pods", namespace=namespace, name=name
    )
    if denied:
        return denied

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


def _tool_list_resource_events(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    core_v1 = ctx.k8s_clients.get("core_v1")
    if core_v1 is None:
        return {"error": "Kubernetes CoreV1 client is unavailable."}

    namespace = args.get("namespace")
    if not namespace:
        return {"error": "namespace is required."}

    denied = _authorize_or_deny(
        ctx, method="GET", resource="events", namespace=namespace
    )
    if denied:
        return denied

    resource_name = args.get("resource_name")
    limit = max(1, min(int(args.get("limit", 10)), 20))
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


def _tool_list_k8sgpt_findings(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    severity = args.get("severity")
    limit = max(1, min(int(args.get("limit", 10)), 20))

    findings = []
    for item in ctx.k8sgpt_results:
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


def _tool_k8s_api_request(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    core_v1 = ctx.k8s_clients.get("core_v1")
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

    # MAINTENANCE: Every cluster call goes through authorize() then API then redact().
    # Do not weaken without human review.
    wrapper_req = WrapperRequest(
        method=method,
        group=group,
        version=version,
        resource=resource,
        namespace=namespace,
        name=name,
        subresource=subresource,
    )
    denied = _authorize_or_deny(
        ctx,
        method=method,
        resource=resource,
        namespace=namespace,
        name=name,
        group=group,
        version=version,
        subresource=subresource,
    )
    if denied:
        return denied
    policy = ctx.kube_policy  # non-None after successful authorize

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

    # dryRunMutations: inject Kubernetes dryRun=All for mutating verbs
    query_params = dict(query)
    if (
        policy.dryRunMutations
        and method in {"POST", "PUT", "PATCH", "DELETE"}
    ):
        existing = query_params.get("dryRun")
        if not existing:
            query_params["dryRun"] = "All"

    api_client = core_v1.api_client
    headers: Dict[str, str] = {}
    if content_type:
        headers["Content-Type"] = content_type
    elif method == "PATCH":
        headers["Content-Type"] = "application/merge-patch+json"

    response_data, status_code, response_headers = api_client.call_api(
        path,
        method,
        query_params=list(query_params.items()),
        body=body,
        header_params=headers,
        auth_settings=["BearerToken"],
        response_type="object",
        _return_http_data_only=False,
    )

    response_data = redact_response(response_data, wrapper_req, policy)

    limited = _limit_tool_result(
        response_data,
        max_items=max(1, min(max_items, 200)),
        max_string_chars=max(200, min(max_string_chars, 10000)),
    )

    return {
        "request": {"method": method, "path": path, "query": query},
        "status_code": status_code,
        "response_headers": dict(response_headers),
        "result": limited,
    }


def _tool_run_skill(skill: Skill) -> Dict[str, Any]:
    """Return the full skill body as instructions for the LLM to follow."""
    return {
        "skill": skill.name,
        "path": str(skill.path),
        "instructions": skill.body,
    }


def _limit_tool_result(payload: Any, max_items: int, max_string_chars: int) -> Any:
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
                    {"_truncated": True, "returned": max_items, "total": len(value)}
                )
            return truncated_items
        if isinstance(value, dict):
            return {key: _truncate(item) for key, item in value.items()}
        return value

    return _truncate(data)
