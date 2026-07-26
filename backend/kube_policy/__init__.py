from __future__ import annotations

from typing import Optional

from .authorize import AuthzResult, WrapperRequest, authorize
from .policy import (
    DenyRules,
    KubeApiPolicy,
    SecretsPolicy,
    load_policy_from_env,
)
from .redact import redact_response

_policy: Optional[KubeApiPolicy] = None


def init_policy() -> KubeApiPolicy:
    """Load the KubeApiPolicy from env and cache it as a module-level singleton."""
    global _policy
    _policy = load_policy_from_env()
    return _policy


def get_policy() -> Optional[KubeApiPolicy]:
    """Return the cached policy (or None if not yet initialised)."""
    return _policy


__all__ = [
    "AuthzResult",
    "DenyRules",
    "KubeApiPolicy",
    "SecretsPolicy",
    "WrapperRequest",
    "authorize",
    "get_policy",
    "init_policy",
    "load_policy_from_env",
    "redact_response",
]
