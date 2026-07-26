from __future__ import annotations

import pytest

from backend.memory.noop import NoopMemory
from backend.memory.port import IngestResult, MemoryHealth


@pytest.fixture
def noop() -> NoopMemory:
    return NoopMemory()


class TestNoopMemory:
    async def test_health_returns_degraded(self, noop: NoopMemory):
        result = await noop.health()

        assert isinstance(result, MemoryHealth)
        assert result.ready is False
        assert result.degraded is True
        assert result.backend == "noop"

    async def test_recall_returns_empty(self, noop: NoopMemory):
        result = await noop.recall(query="anything")

        assert result == []

    async def test_session_start_returns_empty(self, noop: NoopMemory):
        result = await noop.session_start(context="test context")

        assert result == []

    async def test_ingest_returns_noop(self, noop: NoopMemory):
        result = await noop.ingest(content="some content")

        assert isinstance(result, IngestResult)
        assert result.ok is True
        assert result.status == "noop"

    async def test_backfill_returns_empty(self, noop: NoopMemory):
        result = await noop.backfill(failure_context="something failed")

        assert result == []

    async def test_aclose_does_not_raise(self, noop: NoopMemory):
        await noop.aclose()
