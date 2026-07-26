from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RecallHit:
    id: str
    content: str
    score: float | None = None
    reason: str | None = None


@dataclass
class IngestResult:
    ok: bool
    memory_id: str | None = None
    status: str | None = None  # stored | merged | claim_contradicts_memory
    detail: str | None = None


@dataclass
class MemoryHealth:
    ready: bool
    degraded: bool
    backend: str
    detail: str = ""


class MemoryUnavailableError(Exception):
    """Raised when memory backend is unreachable."""
    pass


class MemoryPort(Protocol):
    async def health(self) -> MemoryHealth: ...

    async def session_start(self, *, context: str) -> list[RecallHit]:
        """Prime session; may map to Vestige session_start + recall."""

    async def recall(
        self,
        *,
        query: str,
        top_k: int = 5,
        metadata: dict | None = None,
    ) -> list[RecallHit]: ...

    async def ingest(
        self,
        *,
        content: str,
        metadata: dict | None = None,
    ) -> IngestResult:
        """Map to smart_ingest; content must be pre-scrubbed by caller."""

    async def backfill(self, *, failure_context: str) -> list[RecallHit]:
        """Optional; map to Vestige backfill tool."""

    async def aclose(self) -> None:
        """Stop child process / close MCP session."""
