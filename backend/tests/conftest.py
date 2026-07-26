from __future__ import annotations

import sys
import types
from pathlib import Path

# Repo root + backend on path for `backend.memory` and top-level modules.
_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_BACKEND))


def _ensure_stub(name: str, attrs: dict | None = None) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if attrs:
            for k, v in attrs.items():
                setattr(mod, k, v)
        sys.modules[name] = mod
    elif attrs:
        mod = sys.modules[name]
        for k, v in attrs.items():
            if not hasattr(mod, k):
                setattr(mod, k, v)
    return sys.modules[name]


# Lightweight stubs when local editable installs are not present.
_ensure_stub("devops_rag")
_ensure_stub(
    "devops_rag.llm_client",
    {
        "OpenAIClient": type("OpenAIClient", (), {"__init__": lambda self, *a, **k: None}),
        "AnthropicClient": type(
            "AnthropicClient", (), {"__init__": lambda self, *a, **k: None}
        ),
    },
)
_ensure_stub("devops_k8s")
