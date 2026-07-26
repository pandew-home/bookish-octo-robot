from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from backend.memory.port import MemoryUnavailableError, RecallHit
from backend.memory.vestige_mcp import (
    VestigeMcpMemory,
    parse_ingest_result,
    parse_recall_hits,
)


def _jsonrpc_response(result_content: list[dict], *, headers: dict | None = None) -> httpx.Response:
    body = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "result": {"content": result_content},
    }
    return httpx.Response(
        status_code=200,
        json=body,
        headers=headers or {},
        request=httpx.Request("POST", "http://127.0.0.1:3928/mcp"),
    )


def _jsonrpc_error_response(message: str) -> httpx.Response:
    body = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "error": {"code": -1, "message": message},
    }
    return httpx.Response(
        status_code=200,
        json=body,
        request=httpx.Request("POST", "http://127.0.0.1:3928/mcp"),
    )


class TestMcpInitializeHandshake:
    @pytest.mark.asyncio
    async def test_initialize_sends_correct_jsonrpc(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928", auth_token="tok123")
        init_resp = _jsonrpc_response(
            [],
            headers={"mcp-session-id": "sess-abc", "MCP-Protocol-Version": "2024-11-05"},
        )
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=init_resp)

        await mem._ensure_initialized()

        call_args = mem._client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "initialize"
        assert payload["params"]["protocolVersion"] == "2024-11-05"
        assert payload["params"]["clientInfo"]["name"] == "devops-chatbot"

    @pytest.mark.asyncio
    async def test_initialize_stores_session_id(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        init_resp = _jsonrpc_response(
            [],
            headers={"mcp-session-id": "sess-xyz", "MCP-Protocol-Version": "2024-11-05"},
        )
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=init_resp)

        await mem._ensure_initialized()
        assert mem._session_id == "sess-xyz"
        assert mem._initialized is True


class TestSessionHeaders:
    @pytest.mark.asyncio
    async def test_headers_include_auth_and_session(self):
        mem = VestigeMcpMemory(
            base_url="http://127.0.0.1:3928",
            auth_token="Bearer-test-token",
        )
        mem._initialized = True
        mem._session_id = "sess-123"
        mem._protocol_version = "2024-11-05"
        headers = mem._mcp_headers()
        assert headers["Authorization"] == "Bearer Bearer-test-token"
        assert headers["mcp-session-id"] == "sess-123"

    @pytest.mark.asyncio
    async def test_headers_without_auth_token(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928", auth_token="")
        mem._initialized = True
        mem._session_id = "sess-456"
        mem._protocol_version = "2024-11-05"
        headers = mem._mcp_headers()
        assert "Authorization" not in headers


class TestRecallParsing:
    def test_parse_json_array_of_memories(self):
        hits = parse_recall_hits(
            [
                {
                    "id": "m1",
                    "content": "nginx OOM fix",
                    "semanticScore": 0.91,
                    "decision": "reinforce",
                }
            ]
        )
        assert len(hits) == 1
        assert hits[0].id == "m1"
        assert hits[0].score == 0.91

    def test_parse_ingest_decision_create(self):
        result = parse_ingest_result({"decision": "create", "memory_id": "x1"})
        assert result.ok is True
        assert result.memory_id == "x1"

    def test_parse_ingest_fail_closed_unknown(self):
        result = parse_ingest_result("garbage unstructured")
        assert result.ok is False
        assert result.status == "unparsed"

    @pytest.mark.asyncio
    async def test_recall_maps_to_recall_hits(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._initialized = True
        mem._session_id = "sess-1"
        mem._protocol_version = "2024-11-05"
        recall_text = (
            "id: mem-001\n"
            "content: Pod nginx was crashing due to OOM\n"
            "score: 0.95\n"
            "reason: similar issue\n"
            "\n"
            "id: mem-002\n"
            "content: Deployment scale fix\n"
            "score: 0.80\n"
            "reason: keyword match"
        )
        tool_resp = _jsonrpc_response([{"type": "text", "text": recall_text}])
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=tool_resp)
        hits = await mem.recall(query="nginx crashing", top_k=5)
        assert len(hits) == 2
        assert isinstance(hits[0], RecallHit)
        assert hits[0].id == "mem-001"
        assert hits[0].score == 0.95

    @pytest.mark.asyncio
    async def test_recall_empty_result(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._initialized = True
        mem._session_id = "sess-1"
        mem._protocol_version = "2024-11-05"
        tool_resp = _jsonrpc_response([{"type": "text", "text": ""}])
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=tool_resp)
        hits = await mem.recall(query="nothing found", top_k=5)
        assert hits == []


class TestIngestCallsSmartIngest:
    @pytest.mark.asyncio
    async def test_ingest_calls_smart_ingest_tool(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._initialized = True
        mem._session_id = "sess-1"
        mem._protocol_version = "2024-11-05"
        ingest_text = "ok: true\nmemory_id: mem-999\nstatus: stored\ndetail: ingested"
        tool_resp = _jsonrpc_response([{"type": "text", "text": ingest_text}])
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=tool_resp)
        content = "cluster: prod\nproblem: pod crash"
        result = await mem.ingest(content=content)
        payload = mem._client.post.call_args.kwargs["json"]
        assert payload["params"]["name"] == "smart_ingest"
        assert result.ok is True
        assert result.memory_id == "mem-999"


class TestTimeoutHandling:
    @pytest.mark.asyncio
    async def test_initialize_timeout_raises(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(
            side_effect=httpx.TimeoutException("connection timed out")
        )
        with pytest.raises(MemoryUnavailableError, match="timed out"):
            await mem._ensure_initialized()

    @pytest.mark.asyncio
    async def test_recall_timeout_raises(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._initialized = True
        mem._session_id = "sess-1"
        mem._protocol_version = "2024-11-05"
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(side_effect=httpx.TimeoutException("read timed out"))
        with pytest.raises(MemoryUnavailableError, match="timed out"):
            await mem.recall(query="test", top_k=5)

    @pytest.mark.asyncio
    async def test_jsonrpc_error_raises(self):
        mem = VestigeMcpMemory(base_url="http://127.0.0.1:3928")
        mem._initialized = True
        mem._session_id = "sess-1"
        mem._protocol_version = "2024-11-05"
        mem._client = AsyncMock(spec=httpx.AsyncClient)
        mem._client.post = AsyncMock(return_value=_jsonrpc_error_response("tool not found"))
        with pytest.raises(MemoryUnavailableError, match="error"):
            await mem.recall(query="test", top_k=5)

    def test_remote_url_rejected(self):
        with pytest.raises(MemoryUnavailableError, match="not allowed"):
            VestigeMcpMemory(base_url="http://169.254.169.254/")
