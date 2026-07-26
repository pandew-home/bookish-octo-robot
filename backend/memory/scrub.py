from __future__ import annotations

import re

_AWS_AKIA = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_ASIA = re.compile(r"\bASIA[0-9A-Z]{16}\b")
_AWS_SESSION = re.compile(
    r"(?i)(?:aws_session_token|session[_-]?token)\s*[=:]\s*\S+"
)
_LONG_BASE64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])")
_KUBECONFIG = re.compile(r"apiVersion:\s*v1[\s\S]*kind:\s*Config")
_BEARER = re.compile(r"[Bb]earer\s+[A-Za-z0-9\-._~+/]+=*")
_PEM = re.compile(
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z]*PRIVATE KEY-----"
)
_OPENAI_SK = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")
_GITHUB_PAT = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_EKS_TOKEN = re.compile(r"\bk8s-aws-v1\.[A-Za-z0-9._~+/-]+=*\b")
_SECRET_KV = re.compile(
    r"(?i)(?:secret|password|token|key|credential)[\w\-]*\s*[=:]\s*\S+"
)

_REDACTED = "[REDACTED]"

_HIGH_RISK = (
    _AWS_AKIA,
    _AWS_ASIA,
    _PEM,
    _OPENAI_SK,
    _GITHUB_PAT,
    _SLACK,
    _EKS_TOKEN,
    _BEARER,
    _JWT,
)


def scrub(text: str) -> str:
    """Redact secrets and sensitive patterns from *text*."""
    result = text
    for pattern in (
        _AWS_AKIA,
        _AWS_ASIA,
        _AWS_SESSION,
        _PEM,
        _OPENAI_SK,
        _GITHUB_PAT,
        _SLACK,
        _JWT,
        _EKS_TOKEN,
        _BEARER,
        _KUBECONFIG,
        _SECRET_KV,
        _LONG_BASE64,
    ):
        result = pattern.sub(_REDACTED, result)
    return result


def contains_high_risk_secret(content: str) -> bool:
    """True if original content matches high-risk secret patterns."""
    return any(p.search(content) for p in _HIGH_RISK)


def is_safe(content: str) -> bool:
    """Return False if high-risk secrets remain after scrub, or scrub changed high-risk originals.

    Prefer calling with the **original** text for refuse-ingest decisions via
    ``contains_high_risk_secret``; this checks residual risk after scrubbing.
    """
    if contains_high_risk_secret(content):
        # Original still has high-risk material (not yet scrubbed)
        return False
    scrubbed = scrub(content)
    if contains_high_risk_secret(scrubbed):
        return False
    return True
