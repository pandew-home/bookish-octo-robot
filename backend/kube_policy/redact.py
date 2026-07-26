from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .authorize import WrapperRequest
from .policy import KubeApiPolicy

SECRET_RESOURCE = "secrets"

# Env keys that often hold secrets even when not on a Secret resource
_SENSITIVE_ENV_NAME = (
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "access_key",
    "private",
    "credential",
    "passwd",
    "auth",
)


def _redact_secret_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Redact a single Secret resource, replacing data with key names only."""
    redacted = dict(item)
    data = redacted.pop("data", None)
    redacted.pop("stringData", None)
    if isinstance(data, dict):
        redacted["dataKeys"] = sorted(data.keys())
    return redacted


def _env_name_sensitive(name: str) -> bool:
    n = (name or "").lower()
    return any(s in n for s in _SENSITIVE_ENV_NAME)


def _redact_container_env(container: Dict[str, Any]) -> None:
    env = container.get("env")
    if not isinstance(env, list):
        return
    for entry in env:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if "value" in entry and (
            _env_name_sensitive(name) or len(str(entry.get("value") or "")) > 0
        ):
            # Redact all literal env values (common secret channel); keep name/valueFrom
            if entry.get("value") is not None:
                entry["value"] = "[REDACTED]"
        if "valueFrom" in entry and isinstance(entry["valueFrom"], dict):
            # Keep structure (secretKeyRef names) but never invent data
            pass


def _walk_redact_env(node: Any) -> Any:
    if isinstance(node, dict):
        # Pod/Workload specs
        containers = []
        for key in ("containers", "initContainers", "ephemeralContainers"):
            if isinstance(node.get(key), list):
                for c in node[key]:
                    if isinstance(c, dict):
                        _redact_container_env(c)
        for key, val in list(node.items()):
            node[key] = _walk_redact_env(val)
        return node
    if isinstance(node, list):
        return [_walk_redact_env(x) for x in node]
    return node


def redact_response(
    response_data: Any,
    request: WrapperRequest,
    policy: KubeApiPolicy,
) -> Any:
    """Strip Secret values and sensitive env literals from API responses."""
    if not isinstance(response_data, dict):
        return response_data

    # Secret CR / resource
    if request.resource.lower() == SECRET_RESOURCE:
        if policy.secrets.allowReadData:
            return response_data
        if "items" in response_data and isinstance(response_data["items"], list):
            redacted = dict(response_data)
            redacted["items"] = [
                _redact_secret_item(item) if isinstance(item, dict) else item
                for item in response_data["items"]
            ]
            return redacted
        return _redact_secret_item(dict(response_data))

    # Non-secret resources: deep-copy only when we need env/secret-like scrubbing
    if policy.secrets.allowReadData:
        return response_data

    data = deepcopy(response_data)
    data = _walk_redact_env(data)
    if data.get("kind") == "Secret":
        data = _redact_secret_item(data)
    if isinstance(data.get("items"), list):
        new_items = []
        for item in data["items"]:
            if isinstance(item, dict) and item.get("kind") == "Secret":
                new_items.append(_redact_secret_item(item))
            else:
                new_items.append(item)
        data["items"] = new_items
    return data
