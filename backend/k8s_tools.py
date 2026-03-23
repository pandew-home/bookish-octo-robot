"""
Kubernetes API tool definitions and executor for LLM agent use.
Read-only tools: list_namespaces, list_pods, get_pod, get_pod_logs,
                 list_deployments, get_deployment, get_events, list_nodes
"""
import json
import logging
from typing import Any, Dict, List, Optional

from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)

# Tool definitions in OpenAI function-calling format (also converted for Anthropic)
K8S_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_namespaces",
            "description": "List all namespaces in the cluster",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pods",
            "description": "List pods in a namespace with phase, container states, and restart counts",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (e.g. 'default', 'k8sgpt-operator-system')",
                    }
                },
                "required": ["namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod",
            "description": "Describe a specific pod: phase, conditions, container statuses, and recent events",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string", "description": "Pod name"},
                    "namespace": {"type": "string", "description": "Kubernetes namespace"},
                },
                "required": ["pod_name", "namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_logs",
            "description": "Get logs from a pod container. Use previous=true for crashed containers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string", "description": "Pod name"},
                    "namespace": {"type": "string", "description": "Kubernetes namespace"},
                    "container": {
                        "type": "string",
                        "description": "Container name (omit to use first container)",
                    },
                    "tail_lines": {
                        "type": "integer",
                        "description": "Number of log lines to return (default 100)",
                    },
                    "previous": {
                        "type": "boolean",
                        "description": "Get logs from previous (crashed) container instance",
                    },
                },
                "required": ["pod_name", "namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_deployments",
            "description": "List deployments in a namespace with desired/ready/available replica counts",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Kubernetes namespace"}
                },
                "required": ["namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deployment",
            "description": "Describe a specific deployment: replica status and conditions",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Deployment name"},
                    "namespace": {"type": "string", "description": "Kubernetes namespace"},
                },
                "required": ["name", "namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "Get Kubernetes events in a namespace, optionally filtered by resource name",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Kubernetes namespace"},
                    "resource_name": {
                        "type": "string",
                        "description": "Filter events for a specific resource (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default 50)",
                    },
                },
                "required": ["namespace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_nodes",
            "description": "List cluster nodes with Ready status and roles",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


class K8sToolExecutor:
    """Executes Kubernetes API tool calls on behalf of the LLM agent."""

    def __init__(self, k8s_clients: Dict[str, Any]):
        self.core_v1 = k8s_clients.get("core_v1")
        self.apps_v1 = k8s_clients.get("apps_v1")

    def get_tool_definitions(self) -> List[Dict]:
        return K8S_TOOL_DEFINITIONS

    def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a named tool and return JSON string result."""
        try:
            if tool_name == "list_namespaces":
                return self._list_namespaces()
            elif tool_name == "list_pods":
                return self._list_pods(args["namespace"])
            elif tool_name == "get_pod":
                return self._get_pod(args["pod_name"], args["namespace"])
            elif tool_name == "get_pod_logs":
                return self._get_pod_logs(
                    args["pod_name"],
                    args["namespace"],
                    container=args.get("container"),
                    tail_lines=args.get("tail_lines", 100),
                    previous=args.get("previous", False),
                )
            elif tool_name == "list_deployments":
                return self._list_deployments(args["namespace"])
            elif tool_name == "get_deployment":
                return self._get_deployment(args["name"], args["namespace"])
            elif tool_name == "get_events":
                return self._get_events(
                    args["namespace"],
                    resource_name=args.get("resource_name"),
                    limit=args.get("limit", 50),
                )
            elif tool_name == "list_nodes":
                return self._list_nodes()
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except ApiException as e:
            if e.status == 404:
                return json.dumps({"error": "Resource not found (404)"})
            elif e.status == 403:
                return json.dumps({"error": "Permission denied (403)"})
            return json.dumps({"error": f"Kubernetes API error {e.status}: {e.reason}"})
        except Exception as e:
            logger.error(f"Tool execution error [{tool_name}]: {e}")
            return json.dumps({"error": str(e)})

    def _list_namespaces(self) -> str:
        ns_list = self.core_v1.list_namespace()
        return json.dumps([
            {"name": ns.metadata.name, "status": ns.status.phase}
            for ns in ns_list.items
        ])

    def _list_pods(self, namespace: str) -> str:
        pods = self.core_v1.list_namespaced_pod(namespace, limit=50)
        result = []
        for pod in pods.items:
            containers = []
            for cs in (pod.status.container_statuses or []):
                state, reason = "unknown", None
                if cs.state.running:
                    state = "running"
                elif cs.state.waiting:
                    state, reason = "waiting", cs.state.waiting.reason
                elif cs.state.terminated:
                    state, reason = "terminated", cs.state.terminated.reason
                containers.append({
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": state,
                    "reason": reason,
                })
            result.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": containers,
            })
        return json.dumps(result)

    def _get_pod(self, pod_name: str, namespace: str) -> str:
        pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
        events = self.core_v1.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={pod_name}",
            limit=20,
        )

        conditions = [
            {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
            for c in (pod.status.conditions or [])
        ]

        container_statuses = []
        for cs in (pod.status.container_statuses or []):
            entry: Dict[str, Any] = {
                "name": cs.name,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
            }
            if cs.state.waiting:
                entry.update({"state": "waiting", "reason": cs.state.waiting.reason, "message": cs.state.waiting.message})
            elif cs.state.running:
                entry.update({"state": "running", "started_at": str(cs.state.running.started_at)})
            elif cs.state.terminated:
                entry.update({
                    "state": "terminated",
                    "reason": cs.state.terminated.reason,
                    "exit_code": cs.state.terminated.exit_code,
                    "message": cs.state.terminated.message,
                })
            container_statuses.append(entry)

        return json.dumps({
            "name": pod.metadata.name,
            "namespace": namespace,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "conditions": conditions,
            "container_statuses": container_statuses,
            "events": [
                {"type": e.type, "reason": e.reason, "message": e.message, "count": e.count}
                for e in events.items
            ],
        })

    def _get_pod_logs(
        self,
        pod_name: str,
        namespace: str,
        container: Optional[str] = None,
        tail_lines: int = 100,
        previous: bool = False,
    ) -> str:
        kwargs: Dict[str, Any] = {"tail_lines": tail_lines, "previous": previous}
        if container:
            kwargs["container"] = container
        MAX_LOG_CHARS = 10_000
        try:
            logs = self.core_v1.read_namespaced_pod_log(pod_name, namespace, **kwargs)
            if len(logs) > MAX_LOG_CHARS:
                logs = f"[truncated — showing last {MAX_LOG_CHARS} chars]\n" + logs[-MAX_LOG_CHARS:]
            return json.dumps({"pod": pod_name, "logs": logs})
        except ApiException as e:
            if e.status == 400:
                return json.dumps({"pod": pod_name, "logs": "", "note": "No previous container instance or container not found"})
            raise

    def _list_deployments(self, namespace: str) -> str:
        deps = self.apps_v1.list_namespaced_deployment(namespace)
        return json.dumps([
            {
                "name": d.metadata.name,
                "replicas": d.spec.replicas,
                "ready": d.status.ready_replicas or 0,
                "available": d.status.available_replicas or 0,
                "unavailable": d.status.unavailable_replicas or 0,
            }
            for d in deps.items
        ])

    def _get_deployment(self, name: str, namespace: str) -> str:
        d = self.apps_v1.read_namespaced_deployment(name, namespace)
        conditions = [
            {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
            for c in (d.status.conditions or [])
        ]
        return json.dumps({
            "name": d.metadata.name,
            "namespace": namespace,
            "replicas": d.spec.replicas,
            "ready": d.status.ready_replicas or 0,
            "available": d.status.available_replicas or 0,
            "unavailable": d.status.unavailable_replicas or 0,
            "conditions": conditions,
        })

    def _get_events(
        self, namespace: str, resource_name: Optional[str] = None, limit: int = 50
    ) -> str:
        kwargs: Dict[str, Any] = {"limit": limit}
        if resource_name:
            kwargs["field_selector"] = f"involvedObject.name={resource_name}"
        events = self.core_v1.list_namespaced_event(namespace, **kwargs)
        return json.dumps([
            {
                "type": e.type,
                "reason": e.reason,
                "object": f"{e.involved_object.kind}/{e.involved_object.name}",
                "message": e.message,
                "count": e.count,
                "last_time": str(e.last_timestamp),
            }
            for e in events.items
        ])

    def _list_nodes(self) -> str:
        nodes = self.core_v1.list_node()
        result = []
        for n in nodes.items:
            conditions = {c.type: c.status for c in (n.status.conditions or [])}
            roles = [
                k.split("/")[-1]
                for k in (n.metadata.labels or {})
                if k.startswith("node-role.kubernetes.io/")
            ]
            result.append({
                "name": n.metadata.name,
                "ready": conditions.get("Ready", "Unknown"),
                "roles": roles,
            })
        return json.dumps(result)
