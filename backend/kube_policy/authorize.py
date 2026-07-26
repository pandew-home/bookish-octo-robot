from __future__ import annotations

import logging
from dataclasses import dataclass

from .policy import KubeApiPolicy

logger = logging.getLogger(__name__)

VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

READ_METHODS = {"GET"}
MUTATE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SECRET_RESOURCE = "secrets"

SUBRESOURCE_DENY_MAP = {
    "exec": "execSubresource",
    "portforward": "portforwardSubresource",
    "proxy": "proxySubresource",
}


@dataclass
class WrapperRequest:
    """Represents a single Kubernetes API request to be authorized."""

    method: str
    group: str = ""
    version: str = ""
    resource: str = ""
    namespace: str = ""
    name: str = ""
    subresource: str = ""


@dataclass
class AuthzResult:
    """Result of an authorization check."""

    allowed: bool
    reason: str = ""


def _deny(reason: str) -> AuthzResult:
    return AuthzResult(allowed=False, reason=reason)


def _allow() -> AuthzResult:
    return AuthzResult(allowed=True)


def authorize(request: WrapperRequest, policy: KubeApiPolicy) -> AuthzResult:
    """Evaluate a wrapper request against the KubeApiPolicy.

    Evaluation order follows the contract in access-model.md:
    1. Method validity
    2. Read vs mutate permissions
    3. Secrets policy
    4. Deny rules (serviceaccounts, exec, portforward, proxy, cluster-scoped writes)
    5. Namespace mode
    6. Resource / API group allowlists
    7. Subresource allowlist

    First deny wins.
    """

    method = request.method.upper()

    # 1. Method valid
    if method not in VALID_METHODS:
        return _deny(f"method_not_allowed: {request.method}")

    # 2. Read vs mutate
    if method in READ_METHODS:
        if not policy.allowRead:
            return _deny("read_disabled")
    else:
        if not policy.allowMutate:
            return _deny("mutate_disabled")
        if method not in policy.allowedMethods:
            return _deny(f"method_not_in_allowed_list: {method}")

    # 3. Secrets policy
    if request.resource.lower() == SECRET_RESOURCE:
        if method in READ_METHODS:
            if not policy.secrets.allowIdentify:
                return _deny("secrets_identify_forbidden")
        else:
            if not policy.secrets.allowMutate:
                return _deny("secrets_mutate_forbidden")
            if not policy.allowMutate:
                return _deny("secrets_mutate_forbidden")

    # 4. Other deny rules
    if policy.deny.serviceaccounts and request.resource.lower() == "serviceaccounts":
        if method in MUTATE_METHODS:
            return _deny("serviceaccount_mutate_denied")

    subresource_lower = request.subresource.lower()

    # Always deny high-risk subresources by default (logs leak secrets)
    if subresource_lower in ("log", "logs"):
        return _deny("log_subresource_denied")
    if subresource_lower == "attach":
        return _deny("attach_subresource_denied")

    if subresource_lower == "exec" and policy.deny.execSubresource:
        return _deny("exec_subresource_denied")

    if subresource_lower == "portforward" and policy.deny.portforwardSubresource:
        return _deny("portforward_subresource_denied")

    if subresource_lower == "proxy" and policy.deny.proxySubresource:
        return _deny("proxy_subresource_denied")

    if policy.deny.clusterScopedWrites and method in MUTATE_METHODS:
        if not request.namespace:
            return _deny("cluster_scoped_write_denied")

    # 5. Namespace mode
    if request.namespace:
        if policy.namespaceMode == "allowlist" and policy.namespaces:
            if request.namespace not in policy.namespaces:
                return _deny(
                    f"namespace_not_in_allowlist: {request.namespace}"
                )
        elif policy.namespaceMode == "denylist" and policy.namespaces:
            if request.namespace in policy.namespaces:
                return _deny(f"namespace_in_denylist: {request.namespace}")

    # 6. Resource / API group allowlists
    if policy.allowedResources:
        if request.resource and request.resource.lower() not in {
            r.lower() for r in policy.allowedResources
        }:
            return _deny(f"resource_not_allowed: {request.resource}")

    if policy.allowedApiGroups:
        if request.group not in policy.allowedApiGroups:
            return _deny(f"api_group_not_allowed: {request.group}")

    # 7. Subresource allowlist
    if subresource_lower and policy.allowedSubresources:
        if subresource_lower not in {
            s.lower() for s in policy.allowedSubresources
        }:
            return _deny(f"subresource_not_allowed: {request.subresource}")

    return _allow()
