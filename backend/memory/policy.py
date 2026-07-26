from __future__ import annotations

_REMEDIATION_SIGNALS = frozenset({
    "fix",
    "apply",
    "run",
    "kubectl",
    "yaml",
    "restart",
    "delete",
    "scale",
    "patch",
    "deploy",
})

_DENY_LIST = frozenset({
    "ping",
    "hello",
    "hi",
    "hey",
    "test",
    "auth failed",
    "unauthorized",
})


def is_durable_turn(user_query: str, assistant_response: str) -> bool:
    """Return ``True`` if the turn is worth persisting to memory."""
    normalized_query = user_query.strip().lower()
    if normalized_query in _DENY_LIST:
        return False

    if not assistant_response.strip():
        return False

    if len(assistant_response) > 200:
        return True

    response_lower = assistant_response.lower()
    return any(token in response_lower for token in _REMEDIATION_SIGNALS)
