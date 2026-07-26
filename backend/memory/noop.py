from __future__ import annotations

from .port import IngestResult, MemoryHealth, RecallHit


class NoopMemory:
    """No-op memory backend for degraded mode and testing."""

    async def health(self) -> MemoryHealth:
        return MemoryHealth(ready=False, degraded=True, backend="noop")

    async def session_start(self, *, context: str) -> list[RecallHit]:
        return []

    async def recall(
        self,
        *,
        query: str,
        top_k: int = 5,
        metadata: dict | None = None,
    ) -> list[RecallHit]:
        return []

    async def ingest(
        self,
        *,
        content: str,
        metadata: dict | None = None,
    ) -> IngestResult:
        return IngestResult(ok=True, status="noop")

    async def backfill(self, *, failure_context: str) -> list[RecallHit]:
        return []

    async def aclose(self) -> None:
        pass
