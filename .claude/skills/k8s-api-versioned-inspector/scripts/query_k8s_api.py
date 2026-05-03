#!/usr/bin/env python3
"""Query the Kubernetes API directly from inside a cluster and derive versioned docs."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DOCS_BASE_URL = "https://kubernetes.io/docs/reference/generated/kubernetes-api"
SERVICE_ACCOUNT_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SERVICE_ACCOUNT_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SERVICE_ACCOUNT_NAMESPACE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
DEFAULT_LIMIT = 20
DEFAULT_EVENT_SUMMARY_LIMIT = 10
DEFAULT_TRACE_LIMIT = 10
DEFAULT_DISCOVERY_LIMIT = 50
DEFAULT_ROLLOUT_LIMIT = 10
DEFAULT_LOG_TAIL_LINES = 200
DEFAULT_LOG_LIMIT_BYTES = 32768

TRACE_CHOICES = [
    "service-path",
    "workload-path",
    "storage-path",
    "owner-chain",
]


@dataclass(frozen=True)
class ResourceSpec:
    alias: str
    collection_path: str
    namespaced_collection_path: Optional[str] = None
    item_path: Optional[str] = None
    namespaced_item_path: Optional[str] = None
    supports_label_selector: bool = True
    supports_field_selector: bool = True

    def build_path(self, namespace: Optional[str], name: Optional[str]) -> str:
        if name:
            if namespace and self.namespaced_item_path:
                return self.namespaced_item_path.format(namespace=namespace, name=name)
            if self.item_path:
                return self.item_path.format(name=name)
            raise ValueError(
                f"Resource '{self.alias}' requires --namespace when used with --name"
            )

        if namespace and self.namespaced_collection_path:
            return self.namespaced_collection_path.format(namespace=namespace)

        return self.collection_path


RESOURCE_SPECS: Dict[str, ResourceSpec] = {
    "version": ResourceSpec(
        "version", "/version", None, "/version", None, False, False
    ),
    "api-groups": ResourceSpec(
        "api-groups", "/apis", None, "/apis", None, False, False
    ),
    "namespaces": ResourceSpec(
        "namespaces", "/api/v1/namespaces", None, "/api/v1/namespaces/{name}", None
    ),
    "nodes": ResourceSpec("nodes", "/api/v1/nodes", None, "/api/v1/nodes/{name}", None),
    "pods": ResourceSpec(
        "pods",
        "/api/v1/pods",
        "/api/v1/namespaces/{namespace}/pods",
        None,
        "/api/v1/namespaces/{namespace}/pods/{name}",
    ),
    "deployments": ResourceSpec(
        "deployments",
        "/apis/apps/v1/deployments",
        "/apis/apps/v1/namespaces/{namespace}/deployments",
        None,
        "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
    ),
    "replicasets": ResourceSpec(
        "replicasets",
        "/apis/apps/v1/replicasets",
        "/apis/apps/v1/namespaces/{namespace}/replicasets",
        None,
        "/apis/apps/v1/namespaces/{namespace}/replicasets/{name}",
    ),
    "statefulsets": ResourceSpec(
        "statefulsets",
        "/apis/apps/v1/statefulsets",
        "/apis/apps/v1/namespaces/{namespace}/statefulsets",
        None,
        "/apis/apps/v1/namespaces/{namespace}/statefulsets/{name}",
    ),
    "daemonsets": ResourceSpec(
        "daemonsets",
        "/apis/apps/v1/daemonsets",
        "/apis/apps/v1/namespaces/{namespace}/daemonsets",
        None,
        "/apis/apps/v1/namespaces/{namespace}/daemonsets/{name}",
    ),
    "jobs": ResourceSpec(
        "jobs",
        "/apis/batch/v1/jobs",
        "/apis/batch/v1/namespaces/{namespace}/jobs",
        None,
        "/apis/batch/v1/namespaces/{namespace}/jobs/{name}",
    ),
    "cronjobs": ResourceSpec(
        "cronjobs",
        "/apis/batch/v1/cronjobs",
        "/apis/batch/v1/namespaces/{namespace}/cronjobs",
        None,
        "/apis/batch/v1/namespaces/{namespace}/cronjobs/{name}",
    ),
    "services": ResourceSpec(
        "services",
        "/api/v1/services",
        "/api/v1/namespaces/{namespace}/services",
        None,
        "/api/v1/namespaces/{namespace}/services/{name}",
    ),
    "endpoints": ResourceSpec(
        "endpoints",
        "/api/v1/endpoints",
        "/api/v1/namespaces/{namespace}/endpoints",
        None,
        "/api/v1/namespaces/{namespace}/endpoints/{name}",
    ),
    "endpointslices": ResourceSpec(
        "endpointslices",
        "/apis/discovery.k8s.io/v1/endpointslices",
        "/apis/discovery.k8s.io/v1/namespaces/{namespace}/endpointslices",
        None,
        "/apis/discovery.k8s.io/v1/namespaces/{namespace}/endpointslices/{name}",
    ),
    "ingresses": ResourceSpec(
        "ingresses",
        "/apis/networking.k8s.io/v1/ingresses",
        "/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses",
        None,
        "/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{name}",
    ),
    "ingressclasses": ResourceSpec(
        "ingressclasses",
        "/apis/networking.k8s.io/v1/ingressclasses",
        None,
        "/apis/networking.k8s.io/v1/ingressclasses/{name}",
        None,
    ),
    "networkpolicies": ResourceSpec(
        "networkpolicies",
        "/apis/networking.k8s.io/v1/networkpolicies",
        "/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies",
        None,
        "/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies/{name}",
    ),
    "events": ResourceSpec(
        "events",
        "/apis/events.k8s.io/v1/events",
        "/apis/events.k8s.io/v1/namespaces/{namespace}/events",
        None,
        "/apis/events.k8s.io/v1/namespaces/{namespace}/events/{name}",
    ),
    "leases": ResourceSpec(
        "leases",
        "/apis/coordination.k8s.io/v1/leases",
        "/apis/coordination.k8s.io/v1/namespaces/{namespace}/leases",
        None,
        "/apis/coordination.k8s.io/v1/namespaces/{namespace}/leases/{name}",
    ),
    "persistentvolumeclaims": ResourceSpec(
        "persistentvolumeclaims",
        "/api/v1/persistentvolumeclaims",
        "/api/v1/namespaces/{namespace}/persistentvolumeclaims",
        None,
        "/api/v1/namespaces/{namespace}/persistentvolumeclaims/{name}",
    ),
    "persistentvolumes": ResourceSpec(
        "persistentvolumes",
        "/api/v1/persistentvolumes",
        None,
        "/api/v1/persistentvolumes/{name}",
        None,
    ),
    "storageclasses": ResourceSpec(
        "storageclasses",
        "/apis/storage.k8s.io/v1/storageclasses",
        None,
        "/apis/storage.k8s.io/v1/storageclasses/{name}",
        None,
    ),
    "volumeattachments": ResourceSpec(
        "volumeattachments",
        "/apis/storage.k8s.io/v1/volumeattachments",
        None,
        "/apis/storage.k8s.io/v1/volumeattachments/{name}",
        None,
    ),
    "csidrivers": ResourceSpec(
        "csidrivers",
        "/apis/storage.k8s.io/v1/csidrivers",
        None,
        "/apis/storage.k8s.io/v1/csidrivers/{name}",
        None,
    ),
    "csinodes": ResourceSpec(
        "csinodes",
        "/apis/storage.k8s.io/v1/csinodes",
        None,
        "/apis/storage.k8s.io/v1/csinodes/{name}",
        None,
    ),
    "csistoragecapacities": ResourceSpec(
        "csistoragecapacities",
        "/apis/storage.k8s.io/v1/csistoragecapacities",
        "/apis/storage.k8s.io/v1/namespaces/{namespace}/csistoragecapacities",
        None,
        "/apis/storage.k8s.io/v1/namespaces/{namespace}/csistoragecapacities/{name}",
    ),
    "serviceaccounts": ResourceSpec(
        "serviceaccounts",
        "/api/v1/serviceaccounts",
        "/api/v1/namespaces/{namespace}/serviceaccounts",
        None,
        "/api/v1/namespaces/{namespace}/serviceaccounts/{name}",
    ),
    "roles": ResourceSpec(
        "roles",
        "/apis/rbac.authorization.k8s.io/v1/roles",
        "/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/roles",
        None,
        "/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/roles/{name}",
    ),
    "rolebindings": ResourceSpec(
        "rolebindings",
        "/apis/rbac.authorization.k8s.io/v1/rolebindings",
        "/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/rolebindings",
        None,
        "/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/rolebindings/{name}",
    ),
    "clusterroles": ResourceSpec(
        "clusterroles",
        "/apis/rbac.authorization.k8s.io/v1/clusterroles",
        None,
        "/apis/rbac.authorization.k8s.io/v1/clusterroles/{name}",
        None,
    ),
    "clusterrolebindings": ResourceSpec(
        "clusterrolebindings",
        "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings",
        None,
        "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/{name}",
        None,
    ),
    "resourcequotas": ResourceSpec(
        "resourcequotas",
        "/api/v1/resourcequotas",
        "/api/v1/namespaces/{namespace}/resourcequotas",
        None,
        "/api/v1/namespaces/{namespace}/resourcequotas/{name}",
    ),
    "limitranges": ResourceSpec(
        "limitranges",
        "/api/v1/limitranges",
        "/api/v1/namespaces/{namespace}/limitranges",
        None,
        "/api/v1/namespaces/{namespace}/limitranges/{name}",
    ),
    "horizontalpodautoscalers": ResourceSpec(
        "horizontalpodautoscalers",
        "/apis/autoscaling/v2/horizontalpodautoscalers",
        "/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers",
        None,
        "/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers/{name}",
    ),
    "poddisruptionbudgets": ResourceSpec(
        "poddisruptionbudgets",
        "/apis/policy/v1/poddisruptionbudgets",
        "/apis/policy/v1/namespaces/{namespace}/poddisruptionbudgets",
        None,
        "/apis/policy/v1/namespaces/{namespace}/poddisruptionbudgets/{name}",
    ),
    "customresourcedefinitions": ResourceSpec(
        "customresourcedefinitions",
        "/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
        None,
        "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/{name}",
        None,
    ),
    "apiservices": ResourceSpec(
        "apiservices",
        "/apis/apiregistration.k8s.io/v1/apiservices",
        None,
        "/apis/apiregistration.k8s.io/v1/apiservices/{name}",
        None,
    ),
    "k8sgpt-results": ResourceSpec(
        "k8sgpt-results",
        "/apis/core.k8sgpt.ai/v1alpha1/results",
        "/apis/core.k8sgpt.ai/v1alpha1/namespaces/{namespace}/results",
        None,
        "/apis/core.k8sgpt.ai/v1alpha1/namespaces/{namespace}/results/{name}",
    ),
}

TRACE_REQUIRED_RESOURCES: Dict[str, List[str]] = {
    "service-path": [
        "services",
        "endpoints",
        "endpointslices",
        "pods",
        "replicasets",
        "deployments",
    ],
    "workload-path": [
        "deployments",
        "replicasets",
        "statefulsets",
        "daemonsets",
        "pods",
    ],
    "storage-path": [
        "persistentvolumeclaims",
        "persistentvolumes",
        "volumeattachments",
        "nodes",
    ],
    "owner-chain": [
        "pods",
        "replicasets",
        "deployments",
        "statefulsets",
        "daemonsets",
        "jobs",
        "cronjobs",
    ],
}

ROLLOUT_REQUIRED_RESOURCES: List[str] = [
    "deployments",
    "replicasets",
    "pods",
    "horizontalpodautoscalers",
    "poddisruptionbudgets",
    "events",
]

BUNDLES: Dict[str, List[str]] = {
    "cluster-overview": ["version", "nodes", "namespaces", "apiservices", "leases"],
    "workload-debug": [
        "pods",
        "deployments",
        "replicasets",
        "statefulsets",
        "daemonsets",
        "events",
    ],
    "service-connectivity": [
        "services",
        "endpoints",
        "endpointslices",
        "ingresses",
        "networkpolicies",
        "events",
    ],
    "rbac": [
        "serviceaccounts",
        "roles",
        "rolebindings",
        "clusterroles",
        "clusterrolebindings",
        "events",
    ],
    "storage": [
        "persistentvolumeclaims",
        "persistentvolumes",
        "storageclasses",
        "volumeattachments",
        "csinodes",
        "events",
    ],
    "extensions": ["apiservices", "customresourcedefinitions", "events"],
    "diagnostics": ["k8sgpt-results", "events", "nodes"],
    "namespace-debug": [
        "namespaces",
        "persistentvolumeclaims",
        "resourcequotas",
        "limitranges",
        "events",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query the Kubernetes API from inside a pod and derive versioned docs."
    )
    parser.add_argument(
        "--resources",
        nargs="+",
        choices=sorted(RESOURCE_SPECS.keys()),
        default=[],
        help="Named resource aliases to query.",
    )
    parser.add_argument(
        "--bundle",
        action="append",
        choices=sorted(BUNDLES.keys()),
        default=[],
        help="Predefined troubleshooting bundle to expand into resources.",
    )
    parser.add_argument(
        "--namespace",
        help="Namespace for namespaced resources. Omit for all namespaces where supported.",
    )
    parser.add_argument("--name", help="Optional resource name for a read operation.")
    parser.add_argument(
        "--selector", help="Optional label selector for list operations."
    )
    parser.add_argument(
        "--field-selector",
        help="Optional field selector for list operations.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of items to request and retain per list response.",
    )
    parser.add_argument(
        "--trace",
        action="append",
        choices=TRACE_CHOICES,
        default=[],
        help="Generate relationship traces from fetched resources.",
    )
    parser.add_argument(
        "--trace-limit",
        type=int,
        default=DEFAULT_TRACE_LIMIT,
        help="Maximum number of trace entries to return per trace type.",
    )
    parser.add_argument(
        "--summarize-events",
        action="store_true",
        help="Build a prioritized summary for fetched events.",
    )
    parser.add_argument(
        "--event-summary-limit",
        type=int,
        default=DEFAULT_EVENT_SUMMARY_LIMIT,
        help="Maximum number of summarized event groups to return.",
    )
    parser.add_argument(
        "--finalizer-report",
        action="store_true",
        help="Report objects with finalizers or deletion timestamps from fetched data.",
    )
    parser.add_argument(
        "--discover-api",
        action="store_true",
        help="Discover available API groups, versions, and resource lists live from the cluster.",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=DEFAULT_DISCOVERY_LIMIT,
        help="Maximum number of resources to keep per discovered API group.",
    )
    parser.add_argument(
        "--diagnose-rollout",
        action="store_true",
        help="Build a rollout diagnosis that correlates Deployment, ReplicaSet, Pod, HPA, PDB, and warning event data.",
    )
    parser.add_argument(
        "--rollout-limit",
        type=int,
        default=DEFAULT_ROLLOUT_LIMIT,
        help="Maximum number of rollout diagnosis entries to return.",
    )
    parser.add_argument(
        "--log-pod",
        action="append",
        default=[],
        help="Pod name to retrieve read-only logs from. Repeat to fetch multiple pods.",
    )
    parser.add_argument(
        "--log-container",
        help="Optional container name for pod log retrieval.",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=DEFAULT_LOG_TAIL_LINES,
        help="Maximum number of log lines to fetch per pod log request.",
    )
    parser.add_argument(
        "--since-seconds",
        type=int,
        help="Only return log lines newer than this many seconds.",
    )
    parser.add_argument(
        "--previous",
        action="store_true",
        help="Return logs for the previous terminated container instance.",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Include RFC3339 timestamps in pod log output.",
    )
    parser.add_argument(
        "--log-limit-bytes",
        type=int,
        default=DEFAULT_LOG_LIMIT_BYTES,
        help="Maximum number of bytes to return per pod log request.",
    )
    parser.add_argument(
        "--raw-path",
        action="append",
        default=[],
        help="Direct Kubernetes API path, for example /apis/apps/v1/namespaces/default/deployments.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--include-managed-fields",
        action="store_true",
        help="Retain metadata.managedFields in output.",
    )
    return parser.parse_args()


def read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def require_file(path: str) -> str:
    value = read_file(path)
    if not value:
        raise RuntimeError(f"Missing required file: {path}")
    return value


def in_cluster_server() -> Optional[str]:
    host = os.getenv("KUBERNETES_SERVICE_HOST")
    port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS") or os.getenv(
        "KUBERNETES_SERVICE_PORT", "443"
    )
    if not host:
        return None
    return f"https://{host}:{port}"


def sanitize_object(
    value: Any, include_managed_fields: bool, resource_alias: Optional[str] = None
) -> Any:
    if isinstance(value, list):
        return [
            sanitize_object(item, include_managed_fields, resource_alias)
            for item in value
        ]

    if not isinstance(value, dict):
        return value

    sanitized: Dict[str, Any] = {}
    for key, item in value.items():
        if key == "managedFields" and not include_managed_fields:
            continue
        if resource_alias == "secrets" and key in {"data", "stringData"}:
            continue
        sanitized[key] = sanitize_object(item, include_managed_fields, resource_alias)

    kind = str(value.get("kind", ""))
    if resource_alias == "secrets" or kind == "Secret":
        data = value.get("data") or {}
        string_data = value.get("stringData") or {}
        sanitized["redacted_data_keys"] = sorted(data.keys())
        if string_data:
            sanitized["redacted_string_data_keys"] = sorted(string_data.keys())
        sanitized.pop("data", None)
        sanitized.pop("stringData", None)

    return sanitized


def compact_list_response(
    payload: Dict[str, Any],
    include_managed_fields: bool,
    resource_alias: str,
    limit: int,
) -> Dict[str, Any]:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return sanitize_object(payload, include_managed_fields, resource_alias)

    metadata = payload.get("metadata") or {}
    return {
        "apiVersion": payload.get("apiVersion"),
        "kind": payload.get("kind"),
        "count": len(items),
        "resourceVersion": metadata.get("resourceVersion"),
        "continue": metadata.get("continue"),
        "items": [
            sanitize_object(item, include_managed_fields, resource_alias)
            for item in items[: max(limit, 1)]
        ],
    }


def query_api(
    server: str,
    token: str,
    ca_path: str,
    path: str,
    params: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    query = {key: value for key, value in params.items() if value not in (None, "")}
    url = f"{server}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    context = ssl.create_default_context(cafile=ca_path)

    with urlopen(request, context=context, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def query_text_api(
    server: str,
    token: str,
    ca_path: str,
    path: str,
    params: Dict[str, Any],
    timeout: int,
) -> str:
    query = {
        key: value for key, value in params.items() if value not in (None, "", False)
    }
    url = f"{server}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/plain",
        },
        method="GET",
    )
    context = ssl.create_default_context(cafile=ca_path)

    with urlopen(request, context=context, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def validate_raw_path(path: str) -> Optional[str]:
    if not path.startswith("/api/") and not path.startswith("/apis/"):
        return "Raw paths must start with /api/ or /apis/"

    disallowed_segments = ["/exec", "/attach", "/portforward", "/proxy"]
    for segment in disallowed_segments:
        if segment in path:
            return f"Raw path contains disallowed subresource {segment}"

    return None


def normalize_minor(minor: Optional[str]) -> Optional[str]:
    if not minor:
        return None
    match = re.match(r"^(\d+)", minor)
    if not match:
        return None
    return match.group(1)


def derive_docs_url(version_payload: Dict[str, Any]) -> Optional[str]:
    major = str(version_payload.get("major") or "").strip()
    minor = normalize_minor(str(version_payload.get("minor") or "").strip())
    if not major or not minor:
        return None
    return f"{DOCS_BASE_URL}/v{major}.{minor}/"


def resolve_resources(args: argparse.Namespace) -> List[str]:
    resources: List[str] = []
    for bundle in args.bundle:
        for resource in BUNDLES[bundle]:
            if resource not in resources:
                resources.append(resource)
    for resource in args.resources:
        if resource not in resources:
            resources.append(resource)

    for trace_name in args.trace:
        for resource in TRACE_REQUIRED_RESOURCES[trace_name]:
            if resource not in resources:
                resources.append(resource)

    if args.summarize_events and "events" not in resources:
        resources.append("events")

    if args.finalizer_report and "namespaces" not in resources and args.namespace:
        resources.append("namespaces")

    if args.diagnose_rollout:
        for resource in ROLLOUT_REQUIRED_RESOURCES:
            if resource not in resources:
                resources.append(resource)

    if not resources and not args.raw_path and not args.discover_api:
        return ["version", "nodes", "namespaces"]
    return resources


def build_params(args: argparse.Namespace, spec: ResourceSpec) -> Dict[str, Any]:
    if args.name:
        return {}

    params: Dict[str, Any] = {"limit": max(args.limit, 1)}
    if spec.supports_label_selector and args.selector:
        params["labelSelector"] = args.selector
    if spec.supports_field_selector and args.field_selector:
        params["fieldSelector"] = args.field_selector
    return params


def format_error(exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, HTTPError):
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = None
        return {
            "type": "http_error",
            "status": exc.code,
            "reason": exc.reason,
            "body": body,
        }
    if isinstance(exc, URLError):
        return {"type": "url_error", "reason": str(exc.reason)}
    return {"type": exc.__class__.__name__, "reason": str(exc)}


def get_resource_items(payload: Dict[str, Any], alias: str) -> List[Dict[str, Any]]:
    data = payload.get("data", {}).get(alias)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if data.get("kind") and data.get("metadata"):
        return [data]
    return []


def metadata_of(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def item_name(item: Dict[str, Any]) -> Optional[str]:
    return metadata_of(item).get("name")


def item_namespace(item: Dict[str, Any]) -> Optional[str]:
    return metadata_of(item).get("namespace")


def item_labels(item: Dict[str, Any]) -> Dict[str, str]:
    labels = metadata_of(item).get("labels")
    return labels if isinstance(labels, dict) else {}


def item_kind(item: Dict[str, Any], default: str = "Unknown") -> str:
    kind = item.get("kind")
    return str(kind) if kind else default


def item_finalizers(item: Dict[str, Any]) -> List[str]:
    finalizers = metadata_of(item).get("finalizers")
    return [str(value) for value in finalizers] if isinstance(finalizers, list) else []


def item_deletion_timestamp(item: Dict[str, Any]) -> Optional[str]:
    return metadata_of(item).get("deletionTimestamp")


def item_owner_refs(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs = metadata_of(item).get("ownerReferences")
    return (
        [value for value in refs if isinstance(value, dict)]
        if isinstance(refs, list)
        else []
    )


def item_conditions(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    conditions = item.get("status", {}).get("conditions")
    return (
        [value for value in conditions if isinstance(value, dict)]
        if isinstance(conditions, list)
        else []
    )


def match_selector(labels: Dict[str, str], selector: Dict[str, str]) -> bool:
    if not selector:
        return False
    for key, value in selector.items():
        if labels.get(key) != value:
            return False
    return True


def object_ref_string(
    kind: Optional[str], namespace: Optional[str], name: Optional[str]
) -> str:
    kind_part = kind or "Unknown"
    if namespace:
        return f"{kind_part}/{namespace}/{name or 'unknown'}"
    return f"{kind_part}/{name or 'unknown'}"


def namespaced_key(
    kind: Optional[str], namespace: Optional[str], name: Optional[str]
) -> Tuple[str, Optional[str], str]:
    return (str(kind or "Unknown"), namespace, str(name or "unknown"))


def build_object_index(
    payload: Dict[str, Any],
) -> Dict[Tuple[str, Optional[str], str], Dict[str, Any]]:
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]] = {}
    for alias in payload.get("data", {}):
        for item in get_resource_items(payload, alias):
            key = namespaced_key(item_kind(item), item_namespace(item), item_name(item))
            index[key] = item
    return index


def lookup_owner(
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]],
    kind: Optional[str],
    namespace: Optional[str],
    name: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not kind or not name:
        return None
    direct_key = namespaced_key(kind, namespace, name)
    if direct_key in index:
        return index[direct_key]
    cluster_key = namespaced_key(kind, None, name)
    return index.get(cluster_key)


def walk_owner_chain(
    item: Dict[str, Any],
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]],
    max_depth: int = 8,
) -> List[str]:
    chain = [object_ref_string(item_kind(item), item_namespace(item), item_name(item))]
    current = item
    depth = 0
    seen: set = set()
    while depth < max_depth:
        refs = item_owner_refs(current)
        if not refs:
            break
        owner = refs[0]
        owner_key = namespaced_key(
            owner.get("kind"), item_namespace(current), owner.get("name")
        )
        if owner_key in seen:
            break
        seen.add(owner_key)
        chain.append(
            object_ref_string(
                owner.get("kind"), item_namespace(current), owner.get("name")
            )
        )
        next_item = lookup_owner(
            index, owner.get("kind"), item_namespace(current), owner.get("name")
        )
        if not next_item:
            break
        current = next_item
        depth += 1
    return chain


def selector_for(item: Dict[str, Any]) -> Dict[str, str]:
    selector = item.get("spec", {}).get("selector")
    if isinstance(selector, dict) and isinstance(selector.get("matchLabels"), dict):
        return selector["matchLabels"]
    if isinstance(selector, dict):
        return {k: v for k, v in selector.items() if isinstance(v, str)}
    return {}


def pod_waiting_reason(pod: Dict[str, Any]) -> Optional[str]:
    container_statuses = pod.get("status", {}).get("containerStatuses") or []
    for status in container_statuses:
        waiting = status.get("state", {}).get("waiting")
        if isinstance(waiting, dict) and waiting.get("reason"):
            return waiting.get("reason")
    return None


def pod_restart_count(pod: Dict[str, Any]) -> int:
    container_statuses = pod.get("status", {}).get("containerStatuses") or []
    return sum(
        int(status.get("restartCount") or 0)
        for status in container_statuses
        if isinstance(status, dict)
    )


def deployment_condition_summary(item: Dict[str, Any]) -> List[str]:
    summary = []
    for condition in item_conditions(item):
        type_name = condition.get("type")
        status = condition.get("status")
        reason = condition.get("reason")
        entry = f"{type_name}={status}"
        if reason:
            entry = f"{entry} ({reason})"
        summary.append(entry)
    return summary


def extract_event_details(item: Dict[str, Any]) -> Dict[str, Any]:
    series_value = item.get("series")
    series: Dict[str, Any] = series_value if isinstance(series_value, dict) else {}
    regarding_value = item.get("regarding")
    regarding: Dict[str, Any] = (
        regarding_value if isinstance(regarding_value, dict) else {}
    )
    if not regarding:
        involved_object = item.get("involvedObject")
        regarding = involved_object if isinstance(involved_object, dict) else {}

    count = item.get("deprecatedCount")
    if count is None:
        count = series.get("count")
    if count is None:
        count = item.get("count")
    if count is None:
        count = 1

    last_seen = (
        item.get("eventTime")
        or series.get("lastObservedTime")
        or item.get("deprecatedLastTimestamp")
        or metadata_of(item).get("creationTimestamp")
    )

    return {
        "namespace": item_namespace(item),
        "type": item.get("type") or item.get("deprecatedSource", {}).get("component"),
        "reason": item.get("reason"),
        "message": item.get("note") or item.get("message"),
        "count": int(count),
        "kind": regarding.get("kind"),
        "name": regarding.get("name"),
        "regarding_namespace": regarding.get("namespace") or item_namespace(item),
        "last_seen": last_seen,
    }


def summarize_events(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for item in items:
        details = extract_event_details(item)
        key = (
            details["namespace"],
            details["kind"],
            details["name"],
            details["reason"],
            details["type"],
        )
        if key not in grouped:
            grouped[key] = {
                "namespace": details["namespace"],
                "involved_object": object_ref_string(
                    details["kind"], details["regarding_namespace"], details["name"]
                ),
                "reason": details["reason"],
                "type": details["type"],
                "total_count": 0,
                "latest_seen": details["last_seen"],
                "messages": [],
            }
        entry = grouped[key]
        entry["total_count"] += details["count"]
        if details["last_seen"] and (
            not entry["latest_seen"] or details["last_seen"] > entry["latest_seen"]
        ):
            entry["latest_seen"] = details["last_seen"]
        message = details["message"]
        if message and message not in entry["messages"]:
            entry["messages"].append(message)

    entries = list(grouped.values())
    entries.sort(
        key=lambda entry: (
            0 if str(entry.get("type") or "").lower() == "warning" else 1,
            -int(entry.get("total_count") or 0),
            str(entry.get("latest_seen") or ""),
        )
    )

    for entry in entries:
        entry["messages"] = entry["messages"][:2]

    return entries[: max(limit, 1)]


def iter_objects_for_analysis(
    payload: Dict[str, Any],
) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for alias in payload.get("data", {}):
        for item in get_resource_items(payload, alias):
            yield alias, item


def build_finalizer_report(payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    entries = []
    for alias, item in iter_objects_for_analysis(payload):
        finalizers = item_finalizers(item)
        deletion_timestamp = item_deletion_timestamp(item)
        if not finalizers and not deletion_timestamp:
            continue
        entries.append(
            {
                "resource_alias": alias,
                "object": object_ref_string(
                    item_kind(item), item_namespace(item), item_name(item)
                ),
                "deletion_timestamp": deletion_timestamp,
                "finalizers": finalizers,
                "phase": item.get("status", {}).get("phase"),
            }
        )
    entries.sort(
        key=lambda entry: (
            0 if entry.get("deletion_timestamp") else 1,
            -len(entry.get("finalizers") or []),
            entry.get("object") or "",
        )
    )
    return entries[: max(limit, 1)]


def pod_ready(pod: Dict[str, Any]) -> bool:
    for condition in item_conditions(pod):
        if condition.get("type") == "Ready" and condition.get("status") == "True":
            return True
    return False


def selector_matches_any_pod(
    selector: Dict[str, str], pods: List[Dict[str, Any]], namespace: Optional[str]
) -> bool:
    if not selector:
        return False
    return any(
        item_namespace(pod) == namespace and match_selector(item_labels(pod), selector)
        for pod in pods
    )


def filter_events_for_objects(
    events: List[Dict[str, Any]],
    object_keys: Iterable[Tuple[Optional[str], Optional[str], Optional[str]]],
) -> List[Dict[str, Any]]:
    key_set = set(object_keys)
    matches = []
    for event in events:
        details = extract_event_details(event)
        key = (
            details.get("kind"),
            details.get("regarding_namespace"),
            details.get("name"),
        )
        if key in key_set:
            matches.append(event)
    return matches


def summarize_pods_for_rollout(pods: List[Dict[str, Any]]) -> Dict[str, Any]:
    phase_counts: Dict[str, int] = {}
    waiting_reasons: Dict[str, int] = {}
    restart_total = 0
    ready_count = 0
    pod_entries = []

    for pod in pods:
        phase = str(pod.get("status", {}).get("phase") or "Unknown")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        if pod_ready(pod):
            ready_count += 1
        restart_total += pod_restart_count(pod)
        waiting_reason = pod_waiting_reason(pod)
        if waiting_reason:
            waiting_reasons[waiting_reason] = waiting_reasons.get(waiting_reason, 0) + 1
        pod_entries.append(
            {
                "name": item_name(pod),
                "phase": phase,
                "ready": pod_ready(pod),
                "restarts": pod_restart_count(pod),
                "waiting_reason": waiting_reason,
            }
        )

    waiting_reason_entries = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            waiting_reasons.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    return {
        "total": len(pods),
        "ready": ready_count,
        "restart_total": restart_total,
        "phase_counts": phase_counts,
        "waiting_reasons": waiting_reason_entries,
        "pods": pod_entries[:10],
    }


def hpa_condition_summary(item: Dict[str, Any]) -> List[str]:
    summary = []
    for condition in item_conditions(item):
        entry = f"{condition.get('type')}={condition.get('status')}"
        if condition.get("reason"):
            entry = f"{entry} ({condition.get('reason')})"
        summary.append(entry)
    return summary


def pdb_selector(item: Dict[str, Any]) -> Dict[str, str]:
    spec_selector = item.get("spec", {}).get("selector")
    if isinstance(spec_selector, dict) and isinstance(
        spec_selector.get("matchLabels"), dict
    ):
        return spec_selector["matchLabels"]
    return {}


def diagnose_rollouts(
    payload: Dict[str, Any], args: argparse.Namespace
) -> List[Dict[str, Any]]:
    deployments = get_resource_items(payload, "deployments")
    replicasets = get_resource_items(payload, "replicasets")
    pods = get_resource_items(payload, "pods")
    hpas = get_resource_items(payload, "horizontalpodautoscalers")
    pdbs = get_resource_items(payload, "poddisruptionbudgets")
    events = get_resource_items(payload, "events")

    diagnoses = []
    target_deployments = [
        item for item in deployments if not args.name or item_name(item) == args.name
    ]

    for deployment in target_deployments[: max(args.rollout_limit, 1)]:
        namespace = item_namespace(deployment)
        deployment_name = item_name(deployment)
        deployment_selector = selector_for(deployment)

        matched_rs = [
            item
            for item in replicasets
            if item_namespace(item) == namespace
            and any(
                ref.get("kind") == "Deployment" and ref.get("name") == deployment_name
                for ref in item_owner_refs(item)
            )
        ]
        rs_names = {item_name(item) for item in matched_rs if item_name(item)}
        matched_pods = [
            pod
            for pod in pods
            if item_namespace(pod) == namespace
            and (
                any(
                    ref.get("kind") == "ReplicaSet" and ref.get("name") in rs_names
                    for ref in item_owner_refs(pod)
                )
                or match_selector(item_labels(pod), deployment_selector)
            )
        ]
        matched_hpas = [
            item
            for item in hpas
            if item_namespace(item) == namespace
            and item.get("spec", {}).get("scaleTargetRef", {}).get("kind")
            == "Deployment"
            and item.get("spec", {}).get("scaleTargetRef", {}).get("name")
            == deployment_name
        ]
        matched_pdbs = [
            item
            for item in pdbs
            if item_namespace(item) == namespace
            and selector_matches_any_pod(pdb_selector(item), matched_pods, namespace)
        ]

        event_keys = {("Deployment", namespace, deployment_name)}
        for rs in matched_rs:
            event_keys.add(("ReplicaSet", namespace, item_name(rs)))
        for pod in matched_pods:
            event_keys.add(("Pod", namespace, item_name(pod)))
        relevant_events = filter_events_for_objects(events, event_keys)
        event_summary = summarize_events(relevant_events, args.event_summary_limit)

        status = deployment.get("status", {})
        spec = deployment.get("spec", {})
        blockers: List[str] = []

        generation = metadata_of(deployment).get("generation")
        observed_generation = status.get("observedGeneration")
        if generation and observed_generation and generation != observed_generation:
            blockers.append(
                "Deployment controller has not observed the latest generation"
            )
        if int(status.get("unavailableReplicas") or 0) > 0:
            blockers.append(
                f"Deployment has {int(status.get('unavailableReplicas') or 0)} unavailable replica(s)"
            )
        if int(status.get("updatedReplicas") or 0) < int(spec.get("replicas") or 0):
            blockers.append("Not all desired replicas have been updated")
        if not matched_rs:
            blockers.append("No ReplicaSets found for the Deployment")
        if not matched_pods:
            blockers.append("No Pods match the Deployment selector")

        for condition in item_conditions(deployment):
            if (
                condition.get("type") in {"Progressing", "Available"}
                and condition.get("status") == "False"
            ):
                message = condition.get("message")
                reason = condition.get("reason")
                blocker = f"Deployment condition {condition.get('type')}=False"
                if reason:
                    blocker = f"{blocker} ({reason})"
                if message:
                    blocker = f"{blocker}: {message}"
                blockers.append(blocker)

        pod_summary = summarize_pods_for_rollout(matched_pods)
        if pod_summary["waiting_reasons"]:
            top_reason = pod_summary["waiting_reasons"][0]
            blockers.append(
                f"Pods are waiting with {top_reason['reason']} ({top_reason['count']} occurrence(s))"
            )

        for hpa in matched_hpas:
            for condition in item_conditions(hpa):
                if (
                    condition.get("type") in {"AbleToScale", "ScalingActive"}
                    and condition.get("status") == "False"
                ):
                    blockers.append(
                        f"HPA {item_name(hpa)} reports {condition.get('type')}=False ({condition.get('reason')})"
                    )
                if (
                    condition.get("type") == "ScalingLimited"
                    and condition.get("status") == "True"
                ):
                    blockers.append(
                        f"HPA {item_name(hpa)} is scaling-limited ({condition.get('reason')})"
                    )

        for pdb in matched_pdbs:
            disruptions_allowed = int(
                pdb.get("status", {}).get("disruptionsAllowed") or 0
            )
            current_healthy = int(pdb.get("status", {}).get("currentHealthy") or 0)
            desired_healthy = int(pdb.get("status", {}).get("desiredHealthy") or 0)
            if disruptions_allowed == 0 and current_healthy <= desired_healthy:
                blockers.append(
                    f"PodDisruptionBudget {item_name(pdb)} allows no disruptions and may constrain rollout progress"
                )

        if event_summary:
            top_event = event_summary[0]
            if str(top_event.get("type") or "").lower() == "warning":
                blockers.append(
                    f"Warning events highlight {top_event.get('reason')} on {top_event.get('involved_object')}"
                )

        if not blockers:
            blockers.append(
                "No obvious rollout blocker found from Deployment, ReplicaSet, Pod, HPA, PDB, and warning event data"
            )

        diagnoses.append(
            {
                "deployment": object_ref_string(
                    "Deployment", namespace, deployment_name
                ),
                "replicas": {
                    "desired": spec.get("replicas"),
                    "updated": status.get("updatedReplicas"),
                    "ready": status.get("readyReplicas"),
                    "available": status.get("availableReplicas"),
                    "unavailable": status.get("unavailableReplicas"),
                },
                "generation": {
                    "metadata": generation,
                    "observed": observed_generation,
                },
                "conditions": deployment_condition_summary(deployment),
                "replicasets": [
                    {
                        "name": item_name(item),
                        "revision": metadata_of(item)
                        .get("annotations", {})
                        .get("deployment.kubernetes.io/revision"),
                        "replicas": item.get("status", {}).get("replicas"),
                        "ready_replicas": item.get("status", {}).get("readyReplicas"),
                        "available_replicas": item.get("status", {}).get(
                            "availableReplicas"
                        ),
                    }
                    for item in matched_rs[:10]
                ],
                "pods": pod_summary,
                "horizontal_pod_autoscalers": [
                    {
                        "name": item_name(item),
                        "min_replicas": item.get("spec", {}).get("minReplicas"),
                        "max_replicas": item.get("spec", {}).get("maxReplicas"),
                        "current_replicas": item.get("status", {}).get(
                            "currentReplicas"
                        ),
                        "desired_replicas": item.get("status", {}).get(
                            "desiredReplicas"
                        ),
                        "conditions": hpa_condition_summary(item),
                    }
                    for item in matched_hpas[:10]
                ],
                "pod_disruption_budgets": [
                    {
                        "name": item_name(item),
                        "disruptions_allowed": item.get("status", {}).get(
                            "disruptionsAllowed"
                        ),
                        "current_healthy": item.get("status", {}).get("currentHealthy"),
                        "desired_healthy": item.get("status", {}).get("desiredHealthy"),
                    }
                    for item in matched_pdbs[:10]
                ],
                "warning_events": event_summary,
                "blockers": blockers,
            }
        )

    return diagnoses


def collect_pod_logs(
    server: str,
    token: str,
    ca_path: str,
    namespace: Optional[str],
    pod_names: List[str],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    logs: List[Dict[str, Any]] = []
    errors: Dict[str, Dict[str, Any]] = {}

    if not pod_names:
        return logs, errors
    if not namespace:
        errors["pod_logs"] = {
            "type": "argument_error",
            "reason": "--namespace is required when using --log-pod",
        }
        return logs, errors

    for pod_name in pod_names:
        key = f"pod_log:{namespace}/{pod_name}"
        params: Dict[str, Any] = {
            "tailLines": max(args.tail_lines, 1) if args.tail_lines else None,
            "sinceSeconds": args.since_seconds,
            "previous": True if args.previous else None,
            "timestamps": True if args.timestamps else None,
            "limitBytes": max(args.log_limit_bytes, 1)
            if args.log_limit_bytes
            else None,
        }
        if args.log_container:
            params["container"] = args.log_container

        try:
            content = query_text_api(
                server,
                token,
                ca_path,
                f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log",
                params,
                args.timeout,
            )
            logs.append(
                {
                    "pod": object_ref_string("Pod", namespace, pod_name),
                    "container": args.log_container,
                    "previous": args.previous,
                    "tail_lines": args.tail_lines,
                    "since_seconds": args.since_seconds,
                    "timestamps": args.timestamps,
                    "limit_bytes": args.log_limit_bytes,
                    "line_count": len(content.splitlines()),
                    "content": content,
                }
            )
        except Exception as exc:
            errors[key] = format_error(exc)

    return logs, errors


def trace_service_paths(
    payload: Dict[str, Any],
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    services = get_resource_items(payload, "services")
    endpoints = get_resource_items(payload, "endpoints")
    endpoint_slices = get_resource_items(payload, "endpointslices")
    pods = get_resource_items(payload, "pods")

    focused_services = [
        item for item in services if not args.name or item_name(item) == args.name
    ]
    if not focused_services and args.name:
        return {"entries": [], "notes": ["No matching Service found for --name"]}

    entries = []
    for service in focused_services[: max(args.trace_limit, 1)]:
        namespace = item_namespace(service)
        service_name = item_name(service)
        selector = service.get("spec", {}).get("selector") or {}
        matched_pods = [
            pod
            for pod in pods
            if item_namespace(pod) == namespace
            and match_selector(item_labels(pod), selector)
        ]
        matching_endpoints = [
            item
            for item in endpoints
            if item_namespace(item) == namespace and item_name(item) == service_name
        ]
        matching_slices = [
            item
            for item in endpoint_slices
            if item_namespace(item) == namespace
            and metadata_of(item).get("labels", {}).get("kubernetes.io/service-name")
            == service_name
        ]
        owner_chains = []
        for pod in matched_pods[:5]:
            owner_chains.append(walk_owner_chain(pod, index))

        entries.append(
            {
                "service": object_ref_string("Service", namespace, service_name),
                "selector": selector,
                "matched_pods": [item_name(pod) for pod in matched_pods[:10]],
                "matched_pod_count": len(matched_pods),
                "endpoint_objects": [item_name(item) for item in matching_endpoints],
                "endpoint_slice_objects": [
                    item_name(item) for item in matching_slices[:10]
                ],
                "pod_owner_chains": owner_chains[:5],
            }
        )
    return {"entries": entries}


def trace_workload_paths(
    payload: Dict[str, Any],
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    deployments = get_resource_items(payload, "deployments")
    replicasets = get_resource_items(payload, "replicasets")
    pods = get_resource_items(payload, "pods")
    statefulsets = get_resource_items(payload, "statefulsets")
    daemonsets = get_resource_items(payload, "daemonsets")

    entries = []
    focused_deployments = [
        item for item in deployments if not args.name or item_name(item) == args.name
    ]
    for deployment in focused_deployments[: max(args.trace_limit, 1)]:
        namespace = item_namespace(deployment)
        deployment_name = item_name(deployment)
        selector = selector_for(deployment)
        deployment_rs = [
            item
            for item in replicasets
            if item_namespace(item) == namespace
            and (
                any(
                    ref.get("kind") == "Deployment"
                    and ref.get("name") == deployment_name
                    for ref in item_owner_refs(item)
                )
                or match_selector(item_labels(item), selector)
            )
        ]
        rs_names = {item_name(item) for item in deployment_rs}
        deployment_pods = [
            pod
            for pod in pods
            if item_namespace(pod) == namespace
            and (
                any(
                    ref.get("kind") == "ReplicaSet" and ref.get("name") in rs_names
                    for ref in item_owner_refs(pod)
                )
                or match_selector(item_labels(pod), selector)
            )
        ]
        entries.append(
            {
                "workload": object_ref_string("Deployment", namespace, deployment_name),
                "selector": selector,
                "conditions": deployment_condition_summary(deployment),
                "replicasets": [item_name(item) for item in deployment_rs[:10]],
                "pods": [
                    {
                        "name": item_name(pod),
                        "phase": pod.get("status", {}).get("phase"),
                        "restarts": pod_restart_count(pod),
                        "waiting_reason": pod_waiting_reason(pod),
                    }
                    for pod in deployment_pods[:10]
                ],
            }
        )

    for workload in (statefulsets + daemonsets)[: max(args.trace_limit, 1)]:
        if args.name and item_name(workload) != args.name:
            continue
        entries.append(
            {
                "workload": object_ref_string(
                    item_kind(workload), item_namespace(workload), item_name(workload)
                ),
                "selector": selector_for(workload),
                "conditions": deployment_condition_summary(workload),
                "pods": [
                    object_ref_string(
                        item_kind(pod), item_namespace(pod), item_name(pod)
                    )
                    for pod in pods[:10]
                    if item_namespace(pod) == item_namespace(workload)
                    and match_selector(item_labels(pod), selector_for(workload))
                ],
            }
        )

    if args.name and not entries:
        return {"entries": [], "notes": ["No matching workload found for --name"]}
    return {"entries": entries[: max(args.trace_limit, 1)]}


def trace_storage_paths(
    payload: Dict[str, Any], args: argparse.Namespace
) -> Dict[str, Any]:
    pvcs = get_resource_items(payload, "persistentvolumeclaims")
    pvs = get_resource_items(payload, "persistentvolumes")
    attachments = get_resource_items(payload, "volumeattachments")

    focused_pvcs = [
        item for item in pvcs if not args.name or item_name(item) == args.name
    ]
    if not focused_pvcs and args.name:
        return {
            "entries": [],
            "notes": ["No matching PersistentVolumeClaim found for --name"],
        }

    entries = []
    for pvc in focused_pvcs[: max(args.trace_limit, 1)]:
        pvc_name = item_name(pvc)
        namespace = item_namespace(pvc)
        volume_name = pvc.get("spec", {}).get("volumeName")
        matched_pv = None
        for pv in pvs:
            claim_ref = pv.get("spec", {}).get("claimRef") or {}
            if item_name(pv) == volume_name or (
                claim_ref.get("name") == pvc_name
                and claim_ref.get("namespace") == namespace
            ):
                matched_pv = pv
                break

        matched_attachments = []
        if matched_pv:
            pv_name = item_name(matched_pv)
            matched_attachments = [
                item
                for item in attachments
                if item.get("spec", {}).get("source", {}).get("persistentVolumeName")
                == pv_name
            ]

        entries.append(
            {
                "persistent_volume_claim": object_ref_string(
                    "PersistentVolumeClaim", namespace, pvc_name
                ),
                "phase": pvc.get("status", {}).get("phase"),
                "volume_name": volume_name,
                "persistent_volume": object_ref_string(
                    "PersistentVolume", None, item_name(matched_pv)
                )
                if matched_pv
                else None,
                "volume_attachment_nodes": [
                    item.get("spec", {}).get("nodeName")
                    for item in matched_attachments[:10]
                ],
                "finalizers": item_finalizers(pvc),
                "deletion_timestamp": item_deletion_timestamp(pvc),
            }
        )
    return {"entries": entries}


def trace_owner_chains(
    payload: Dict[str, Any],
    index: Dict[Tuple[str, Optional[str], str], Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    candidates = []
    for alias in [
        "pods",
        "replicasets",
        "deployments",
        "statefulsets",
        "daemonsets",
        "jobs",
        "cronjobs",
    ]:
        candidates.extend(get_resource_items(payload, alias))

    if args.name:
        candidates = [item for item in candidates if item_name(item) == args.name]
    candidates = [item for item in candidates if item_owner_refs(item)]

    entries = []
    for item in candidates[: max(args.trace_limit, 1)]:
        entries.append(
            {
                "object": object_ref_string(
                    item_kind(item), item_namespace(item), item_name(item)
                ),
                "chain": walk_owner_chain(item, index),
            }
        )
    return {"entries": entries}


def build_relationship_traces(
    payload: Dict[str, Any], args: argparse.Namespace
) -> Dict[str, Any]:
    if not args.trace:
        return {}

    index = build_object_index(payload)
    traces: Dict[str, Any] = {}
    for trace_name in args.trace:
        if trace_name == "service-path":
            traces[trace_name] = trace_service_paths(payload, index, args)
        elif trace_name == "workload-path":
            traces[trace_name] = trace_workload_paths(payload, index, args)
        elif trace_name == "storage-path":
            traces[trace_name] = trace_storage_paths(payload, args)
        elif trace_name == "owner-chain":
            traces[trace_name] = trace_owner_chains(payload, index, args)
    return traces


def summarize_resource_list(payload: Dict[str, Any], limit: int) -> Dict[str, Any]:
    raw_resources = payload.get("resources")
    resources: List[Any] = raw_resources if isinstance(raw_resources, list) else []
    entries = []
    for resource in resources[: max(limit, 1)]:
        if not isinstance(resource, dict):
            continue
        entries.append(
            {
                "name": resource.get("name"),
                "kind": resource.get("kind"),
                "namespaced": resource.get("namespaced"),
                "verbs": resource.get("verbs"),
                "shortNames": resource.get("shortNames"),
                "singularName": resource.get("singularName"),
            }
        )
    return {
        "groupVersion": payload.get("groupVersion"),
        "kind": payload.get("kind"),
        "resource_count": len(resources),
        "resources": entries,
    }


def discover_api_surface(
    server: str, token: str, ca_path: str, timeout: int, limit: int
) -> Dict[str, Any]:
    discovery: Dict[str, Any] = {
        "core_versions": [],
        "core_resources": {},
        "groups": [],
        "errors": {},
    }

    try:
        core_versions = query_api(server, token, ca_path, "/api", {}, timeout)
        raw_versions = core_versions.get("versions")
        versions: List[Any] = raw_versions if isinstance(raw_versions, list) else []
        discovery["core_versions"] = versions
        for version in versions:
            try:
                resource_list = query_api(
                    server, token, ca_path, f"/api/{version}", {}, timeout
                )
                discovery["core_resources"][version] = summarize_resource_list(
                    resource_list, limit
                )
            except Exception as exc:
                discovery["errors"][f"/api/{version}"] = format_error(exc)
    except Exception as exc:
        discovery["errors"]["/api"] = format_error(exc)

    try:
        groups_payload = query_api(server, token, ca_path, "/apis", {}, timeout)
        raw_groups = groups_payload.get("groups")
        groups: List[Any] = raw_groups if isinstance(raw_groups, list) else []
        for group in groups:
            if not isinstance(group, dict):
                continue
            preferred = group.get("preferredVersion") or {}
            group_version = preferred.get("groupVersion")
            entry = {
                "name": group.get("name"),
                "preferred_version": group_version,
                "versions": [
                    value.get("groupVersion")
                    for value in group.get("versions", [])
                    if isinstance(value, dict)
                ],
            }
            if group_version:
                try:
                    resources_payload = query_api(
                        server, token, ca_path, f"/apis/{group_version}", {}, timeout
                    )
                    entry["resources"] = summarize_resource_list(
                        resources_payload, limit
                    )
                except Exception as exc:
                    entry["resources_error"] = format_error(exc)
            discovery["groups"].append(entry)
    except Exception as exc:
        discovery["errors"]["/apis"] = format_error(exc)

    return discovery


def main() -> int:
    args = parse_args()
    server = in_cluster_server()
    if not server:
        print(
            json.dumps(
                {
                    "error": "in-cluster configuration unavailable",
                    "details": "KUBERNETES_SERVICE_HOST is not set.",
                },
                indent=2,
            )
        )
        return 2

    try:
        token = require_file(SERVICE_ACCOUNT_TOKEN)
        ca_path = SERVICE_ACCOUNT_CA
        if not os.path.exists(ca_path):
            raise RuntimeError(f"Missing required file: {ca_path}")
    except Exception as exc:
        print(
            json.dumps(
                {"error": "service account unavailable", "details": str(exc)}, indent=2
            )
        )
        return 2

    payload: Dict[str, Any] = {
        "queried_at": datetime.now(timezone.utc).isoformat(),
        "api_server": server,
        "requested_namespace": args.namespace,
        "service_account_namespace": read_file(SERVICE_ACCOUNT_NAMESPACE),
        "resources": resolve_resources(args),
        "raw_paths": args.raw_path,
        "name": args.name,
        "label_selector": args.selector,
        "field_selector": args.field_selector,
        "cluster_version": None,
        "docs_url": None,
        "data": {},
        "errors": {},
        "notes": [],
        "event_summary": [],
        "relationship_traces": {},
        "rollout_diagnosis": [],
        "finalizer_report": [],
        "pod_logs": [],
        "api_discovery": None,
    }

    try:
        version_payload = query_api(
            server, token, ca_path, "/version", {}, args.timeout
        )
        payload["cluster_version"] = sanitize_object(
            version_payload, args.include_managed_fields, "version"
        )
        payload["docs_url"] = derive_docs_url(version_payload)
    except Exception as exc:
        payload["errors"]["version"] = format_error(exc)

    for resource in payload["resources"]:
        spec = RESOURCE_SPECS[resource]
        try:
            path = spec.build_path(args.namespace, args.name)
            result = query_api(
                server,
                token,
                ca_path,
                path,
                build_params(args, spec),
                args.timeout,
            )
            payload["data"][resource] = compact_list_response(
                result, args.include_managed_fields, resource, args.limit
            )
        except Exception as exc:
            payload["errors"][resource] = format_error(exc)

    for raw_path in args.raw_path:
        key = f"raw:{raw_path}"
        validation_error = validate_raw_path(raw_path)
        if validation_error:
            payload["errors"][key] = {
                "type": "argument_error",
                "reason": validation_error,
            }
            continue
        try:
            result = query_api(server, token, ca_path, raw_path, {}, args.timeout)
            payload["data"][key] = compact_list_response(
                result, args.include_managed_fields, "raw", args.limit
            )
        except Exception as exc:
            payload["errors"][key] = format_error(exc)

    if args.summarize_events or "events" in payload["data"]:
        payload["event_summary"] = summarize_events(
            get_resource_items(payload, "events"), args.event_summary_limit
        )

    if args.trace:
        payload["relationship_traces"] = build_relationship_traces(payload, args)

    if args.diagnose_rollout:
        payload["rollout_diagnosis"] = diagnose_rollouts(payload, args)
        if args.name and not payload["rollout_diagnosis"]:
            payload["notes"].append(
                "No matching Deployment found for rollout diagnosis"
            )

    if args.finalizer_report:
        payload["finalizer_report"] = build_finalizer_report(payload, args.limit)

    if args.log_pod:
        pod_logs, pod_log_errors = collect_pod_logs(
            server,
            token,
            ca_path,
            args.namespace,
            args.log_pod,
            args,
        )
        payload["pod_logs"] = pod_logs
        payload["errors"].update(pod_log_errors)

    if args.discover_api:
        payload["api_discovery"] = discover_api_surface(
            server, token, ca_path, args.timeout, args.discover_limit
        )

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
