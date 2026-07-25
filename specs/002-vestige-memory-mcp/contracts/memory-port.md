# Contract: MemoryPort (backend internal)

**Consumers**: `api/chat.py`, `agentic_engine.py`, `agent_tools.py`  
**Implementations**: `VestigeMcpMemory`, `NoopMemory` (tests/degraded)

## Types

```python
# Conceptual — actual code in backend/memory/port.py

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
    status: str | None = None  # e.g. stored | merged | claim_contradicts_memory
    detail: str | None = None

@dataclass
class MemoryHealth:
    ready: bool
    degraded: bool
    backend: str
    detail: str = ""
```

## Interface

```python
class MemoryPort(Protocol):
    async def health(self) -> MemoryHealth: ...

    async def session_start(self, *, context: str) -> list[RecallHit]:
        """Prime session; may map to Vestige session_start + recall."""

    async def recall(self, *, query: str, top_k: int = 5, metadata: dict | None = None) -> list[RecallHit]:
        ...

    async def ingest(self, *, content: str, metadata: dict | None = None) -> IngestResult:
        """Map to smart_ingest; content must be pre-scrubbed by caller."""

    async def backfill(self, *, failure_context: str) -> list[RecallHit]:
        """Optional; map to Vestige backfill tool."""

    async def aclose(self) -> None:
        """Stop child process / close MCP session."""
```

## Behavioral contracts

| Case | Behavior |
|------|----------|
| Backend unavailable | Methods raise `MemoryUnavailableError` or return empty + health.degraded; **callers must not fail chat** |
| Timeout | Configurable (default 2s recall, 5s ingest); then degrade |
| Empty store | `recall` returns `[]`, not error |
| Contradiction on ingest | `IngestResult.ok` may be false/true with `status=claim_contradicts_memory`; chat still succeeds; detail may surface in metadata |

## Factory

```python
def get_memory_port() -> MemoryPort:
    # env MEMORY_BACKEND=vestige|noop
    # env VESTIGE_BIN, VESTIGE_DATA_DIR
```
