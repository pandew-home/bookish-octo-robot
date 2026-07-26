from __future__ import annotations

import os
from typing import Optional

from .port import (
    IngestResult,
    MemoryHealth,
    MemoryPort,
    MemoryUnavailableError,
    RecallHit,
)

_memory_port: Optional[MemoryPort] = None


# Default when MEMORY_BACKEND is unset: noop (safe local boot without Vestige).
# Production charts set MEMORY_BACKEND=vestige explicitly.
_DEFAULT_MEMORY_BACKEND = "noop"


def get_memory_port() -> MemoryPort:
    global _memory_port
    if _memory_port is None:
        backend = os.environ.get("MEMORY_BACKEND", _DEFAULT_MEMORY_BACKEND).lower()
        if backend == "vestige":
            from .vestige_mcp import VestigeMcpMemory

            _memory_port = VestigeMcpMemory()
        else:
            from .noop import NoopMemory

            _memory_port = NoopMemory()
    return _memory_port


async def aclose_memory_port() -> None:
    """Async close of the singleton (safe under uvicorn)."""
    global _memory_port
    if _memory_port is not None:
        await _memory_port.aclose()
        _memory_port = None


def close_memory_port() -> None:
    """Best-effort sync close for scripts/tests (prefer aclose_memory_port in async)."""
    global _memory_port
    if _memory_port is None:
        return
    try:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Cannot block; leave for process exit
            _memory_port = None
            return
        asyncio.run(_memory_port.aclose())
    except Exception:
        pass
    _memory_port = None


def reset_memory_port() -> None:
    """Reset the singleton; intended for tests."""
    global _memory_port
    _memory_port = None


__all__ = [
    "MemoryPort",
    "RecallHit",
    "IngestResult",
    "MemoryHealth",
    "MemoryUnavailableError",
    "get_memory_port",
    "aclose_memory_port",
    "close_memory_port",
    "reset_memory_port",
]
