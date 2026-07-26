from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class SecretsPolicy:
    """Policy governing Secret identification, reading, and mutation."""

    allowIdentify: bool = True
    allowReadData: bool = False
    allowMutate: bool = False


@dataclass
class DenyRules:
    """Explicit deny rules for specific Kubernetes operations."""

    serviceaccounts: bool = True
    clusterScopedWrites: bool = True
    execSubresource: bool = True
    portforwardSubresource: bool = True
    proxySubresource: bool = True


@dataclass
class KubeApiPolicy:
    """Complete policy controlling agent access to the Kubernetes API."""

    allowRead: bool = True
    allowMutate: bool = False
    allowedMethods: List[str] = field(default_factory=lambda: ["GET"])
    allowedSubresources: List[str] = field(default_factory=list)
    namespaceMode: str = "any"
    namespaces: List[str] = field(default_factory=list)
    allowedResources: List[str] = field(default_factory=list)
    allowedApiGroups: List[str] = field(default_factory=list)
    secrets: SecretsPolicy = field(default_factory=SecretsPolicy)
    deny: DenyRules = field(default_factory=DenyRules)
    dryRunMutations: bool = False
    logDeniedRequests: bool = True


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes")


def _env_csv(key: str, default: List[str]) -> List[str]:
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def load_policy_from_env() -> KubeApiPolicy:
    """Load a KubeApiPolicy from environment variables with chart defaults."""

    secrets = SecretsPolicy(
        allowIdentify=_env_bool("KUBE_API_SECRETS_ALLOW_IDENTIFY", True),
        allowReadData=_env_bool("KUBE_API_SECRETS_ALLOW_READ_DATA", False),
        allowMutate=_env_bool("KUBE_API_SECRETS_ALLOW_MUTATE", False),
    )

    # Accept both contract names (KUBE_API_DENY_EXEC) and helm-suffixed names
    # (KUBE_API_DENY_EXEC_SUBRESOURCE) so chart env wiring cannot drift silently.
    deny = DenyRules(
        serviceaccounts=_env_bool("KUBE_API_DENY_SERVICEACCOUNTS", True),
        clusterScopedWrites=_env_bool("KUBE_API_DENY_CLUSTER_SCOPED_WRITES", True),
        execSubresource=_env_bool(
            "KUBE_API_DENY_EXEC",
            _env_bool("KUBE_API_DENY_EXEC_SUBRESOURCE", True),
        ),
        portforwardSubresource=_env_bool(
            "KUBE_API_DENY_PORTFORWARD",
            _env_bool("KUBE_API_DENY_PORTFORWARD_SUBRESOURCE", True),
        ),
        proxySubresource=_env_bool(
            "KUBE_API_DENY_PROXY",
            _env_bool("KUBE_API_DENY_PROXY_SUBRESOURCE", True),
        ),
    )

    return KubeApiPolicy(
        allowRead=_env_bool("KUBE_API_ALLOW_READ", True),
        allowMutate=_env_bool("KUBE_API_ALLOW_MUTATE", False),
        allowedMethods=_env_csv("KUBE_API_ALLOWED_METHODS", ["GET"]),
        allowedSubresources=_env_csv("KUBE_API_ALLOWED_SUBRESOURCES", []),
        namespaceMode=os.environ.get("KUBE_API_NAMESPACE_MODE", "any"),
        namespaces=_env_csv("KUBE_API_NAMESPACES", []),
        allowedResources=_env_csv("KUBE_API_ALLOWED_RESOURCES", []),
        allowedApiGroups=_env_csv("KUBE_API_ALLOWED_API_GROUPS", []),
        secrets=secrets,
        deny=deny,
        dryRunMutations=_env_bool("KUBE_API_DRY_RUN_MUTATIONS", False),
        logDeniedRequests=_env_bool("KUBE_API_LOG_DENIED", True),
    )
