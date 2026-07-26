from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from .port import (
    IngestResult,
    MemoryHealth,
    MemoryUnavailableError,
    RecallHit,
)

logger = logging.getLogger(__name__)

_MCP_PROTOCOL_VERSION = "2024-11-05"
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _validate_base_url(url: str) -> str:
    """Restrict Vestige client to loopback by default (SSRF guard)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allow_remote = os.environ.get("VESTIGE_ALLOW_REMOTE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_remote and host not in _ALLOWED_HOSTS:
        raise MemoryUnavailableError(
            f"VESTIGE_HTTP_URL host {host!r} not allowed; use loopback or set VESTIGE_ALLOW_REMOTE=true"
        )
    return url.rstrip("/")


class VestigeMcpMemory:
    """HTTP MCP client for the colocated Vestige memory server."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        auth_token: str | None = None,
        recall_timeout_ms: int | None = None,
        ingest_timeout_ms: int | None = None,
    ) -> None:
        raw = (
            base_url
            or os.environ.get("VESTIGE_HTTP_URL")
            or "http://127.0.0.1:3928"
        )
        self._base_url = _validate_base_url(raw)
        self._auth_token = auth_token if auth_token is not None else os.environ.get(
            "VESTIGE_AUTH_TOKEN", ""
        )
        # Vestige writes its HTTP auth token under XDG data home by default.
        if not self._auth_token:
            candidates = [
                os.environ.get("VESTIGE_AUTH_TOKEN_FILE", ""),
                "/tmp/vestige-auth-token",
                "/tmp/.local/share/core/auth_token",
                os.path.expanduser("~/.local/share/core/auth_token"),
            ]
            for token_file in candidates:
                if not token_file:
                    continue
                try:
                    if os.path.isfile(token_file):
                        with open(token_file, encoding="utf-8") as f:
                            self._auth_token = f.read().strip()
                        if self._auth_token:
                            break
                except OSError:
                    continue
        self._recall_timeout = (
            recall_timeout_ms
            or int(os.environ.get("MEMORY_RECALL_TIMEOUT_MS", "2000"))
        ) / 1000.0
        self._ingest_timeout = (
            ingest_timeout_ms
            or int(os.environ.get("MEMORY_INGEST_TIMEOUT_MS", "5000"))
        ) / 1000.0

        self._client = httpx.AsyncClient(base_url=self._base_url)
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    def _invalidate_session(self) -> None:
        self._initialized = False
        self._session_id = None

    async def _ensure_initialized(self, *, force: bool = False) -> None:
        async with self._init_lock:
            if self._initialized and not force:
                return
            request_id = str(uuid.uuid4())
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "devops-chatbot", "version": "1.0.0"},
                },
            }
            try:
                headers = self._mcp_headers(include_session=False)
                headers["MCP-Protocol-Version"] = (
                    self._protocol_version or _MCP_PROTOCOL_VERSION
                )
                resp = await self._client.post(
                    "/mcp",
                    json=payload,
                    headers=headers,
                    timeout=self._recall_timeout,
                )
                resp.raise_for_status()
                self._session_id = resp.headers.get(
                    "mcp-session-id"
                ) or resp.headers.get("Mcp-Session-Id")
                self._protocol_version = (
                    resp.headers.get("MCP-Protocol-Version") or _MCP_PROTOCOL_VERSION
                )
                self._initialized = True
                logger.info("[VESTIGE_MCP] Initialized session=%s", self._session_id)
            except httpx.TimeoutException:
                self._invalidate_session()
                logger.warning("[VESTIGE_MCP] Timeout during MCP initialize handshake")
                raise MemoryUnavailableError("MCP initialize timed out")
            except httpx.HTTPError as exc:
                self._invalidate_session()
                logger.warning("[VESTIGE_MCP] HTTP error during initialize: %s", exc)
                raise MemoryUnavailableError(f"MCP initialize failed: {exc}")

    def _mcp_headers(self, *, include_session: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if self._protocol_version:
            headers["MCP-Protocol-Version"] = self._protocol_version
        if include_session and self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout: float | None = None,
        _retried: bool = False,
    ) -> Any:
        await self._ensure_initialized()
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            resp = await self._client.post(
                "/mcp",
                json=payload,
                headers=self._mcp_headers(),
                timeout=timeout or self._recall_timeout,
            )
            if resp.status_code in (401, 404) and not _retried:
                logger.warning(
                    "[VESTIGE_MCP] session stale status=%s; re-handshake",
                    resp.status_code,
                )
                self._invalidate_session()
                await self._ensure_initialized(force=True)
                return await self._call_tool(
                    tool_name, arguments, timeout=timeout, _retried=True
                )
            resp.raise_for_status()
            body = resp.json()
        except httpx.TimeoutException:
            logger.warning("[VESTIGE_MCP] Timeout calling %s", tool_name)
            raise MemoryUnavailableError(f"Tool {tool_name} timed out")
        except httpx.HTTPError as exc:
            if not _retried:
                self._invalidate_session()
            logger.warning("[VESTIGE_MCP] HTTP error calling %s: %s", tool_name, exc)
            raise MemoryUnavailableError(f"Tool {tool_name} failed: {exc}")

        if "error" in body:
            err = body["error"]
            msg = str(err)
            if not _retried and any(
                x in msg.lower() for x in ("session", "unauthorized", "initialize")
            ):
                self._invalidate_session()
                await self._ensure_initialized(force=True)
                return await self._call_tool(
                    tool_name, arguments, timeout=timeout, _retried=True
                )
            logger.warning("[VESTIGE_MCP] JSON-RPC error from %s: %s", tool_name, err)
            raise MemoryUnavailableError(f"Tool {tool_name} returned error: {err}")

        result = body.get("result", {}) or {}
        if result.get("isError"):
            text = _extract_text(result.get("content") or [])
            raise MemoryUnavailableError(
                f"Tool {tool_name} isError: {text[:300] or 'unknown'}"
            )
        # Prefer structuredContent when present (MCP 2024+)
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        return result.get("content", [])

    async def health(self) -> MemoryHealth:
        try:
            raw = await self._call_tool(
                "memory_status", {}, timeout=self._recall_timeout
            )
            text = _content_to_text(raw)
            return MemoryHealth(
                ready=True, degraded=False, backend="vestige", detail=text[:500]
            )
        except MemoryUnavailableError as exc:
            return MemoryHealth(
                ready=False, degraded=True, backend="vestige", detail=str(exc)
            )
        except Exception as exc:
            logger.warning("[VESTIGE_MCP] health check failed: %s", exc)
            return MemoryHealth(
                ready=False, degraded=True, backend="vestige", detail=str(exc)
            )

    async def session_start(self, *, context: str) -> list[RecallHit]:
        try:
            raw = await self._call_tool("session_start", {"context": context})
            return parse_recall_hits(raw)
        except MemoryUnavailableError:
            raise
        except Exception as exc:
            logger.warning("[VESTIGE_MCP] session_start failed: %s", exc)
            raise MemoryUnavailableError(f"session_start failed: {exc}") from exc

    async def recall(
        self,
        *,
        query: str,
        top_k: int = 5,
        metadata: dict | None = None,
    ) -> list[RecallHit]:
        args: dict[str, Any] = {"query": query, "top_k": top_k}
        if metadata:
            args["metadata"] = metadata
        try:
            raw = await self._call_tool("recall", args, timeout=self._recall_timeout)
            return parse_recall_hits(raw)
        except MemoryUnavailableError:
            raise
        except Exception as exc:
            logger.warning("[VESTIGE_MCP] recall failed: %s", exc)
            raise MemoryUnavailableError(f"recall failed: {exc}") from exc

    async def ingest(
        self,
        *,
        content: str,
        metadata: dict | None = None,
    ) -> IngestResult:
        args: dict[str, Any] = {"content": content}
        if metadata:
            args["metadata"] = metadata
        try:
            raw = await self._call_tool(
                "smart_ingest", args, timeout=self._ingest_timeout
            )
            return parse_ingest_result(raw)
        except MemoryUnavailableError:
            raise
        except Exception as exc:
            logger.warning("[VESTIGE_MCP] ingest failed: %s", exc)
            raise MemoryUnavailableError(f"ingest failed: {exc}") from exc

    async def backfill(self, *, failure_context: str) -> list[RecallHit]:
        try:
            raw = await self._call_tool(
                "backfill", {"failure_context": failure_context}
            )
            return parse_recall_hits(raw)
        except MemoryUnavailableError:
            raise
        except Exception as exc:
            logger.warning("[VESTIGE_MCP] backfill failed: %s", exc)
            raise MemoryUnavailableError(f"backfill failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
        self._invalidate_session()
        logger.info("[VESTIGE_MCP] Client closed")


def _extract_text(content_items: list[Any]) -> str:
    parts: list[str] = []
    for item in content_items:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(parts)


def _content_to_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return _extract_text(raw)
    if isinstance(raw, dict):
        return json.dumps(raw)[:2000]
    return str(raw)[:2000]


def _try_parse_json(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Sometimes models wrap JSON in fences
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue
    return None


def parse_recall_hits(raw: Any) -> list[RecallHit]:
    """Parse Vestige recall/session_start payloads into RecallHit list.

    Supports:
    - structuredContent dict/list (preferred)
    - MCP content[] with JSON text
    - free text (legacy id:/content: blocks or whole blob as one hit)
    """
    hits: list[RecallHit] = []

    def _from_obj(obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, list):
            for item in obj:
                _from_obj(item)
            return
        if isinstance(obj, dict):
            # MCP content item: parse nested text as structured payload
            if obj.get("type") == "text" and isinstance(obj.get("text"), str):
                nested = _try_parse_json(obj["text"])
                if nested is not None:
                    _from_obj(nested)
                    return
                # Legacy multi-block protocol inside text
                legacy = parse_recall_hits(obj["text"])
                if legacy and not (
                    len(legacy) == 1 and legacy[0].id.startswith("hit-")
                ):
                    hits.extend(legacy)
                    return
                if legacy:
                    hits.extend(legacy)
                    return
            # Nested containers
            for key in ("memories", "results", "hits", "items", "nodes"):
                if key in obj and isinstance(obj[key], list):
                    _from_obj(obj[key])
                    return
            content = (
                obj.get("content")
                or obj.get("snippet")
                or obj.get("summary")
                or obj.get("body")
            )
            if content is None and obj.get("type") != "text":
                content = obj.get("text")
            if content is None and obj.get("memory"):
                content = obj["memory"]
            if isinstance(content, dict):
                content = json.dumps(content)
            hit_id = str(
                obj.get("id")
                or obj.get("memory_id")
                or obj.get("memoryId")
                or obj.get("nodeId")
                or ""
            )
            score = obj.get("score")
            if score is None:
                score = obj.get("semanticScore") or obj.get("semantic_score")
            try:
                score_f = float(score) if score is not None else None
            except (TypeError, ValueError):
                score_f = None
            reason = obj.get("reason") or obj.get("decision") or obj.get("why")
            if content or hit_id:
                hits.append(
                    RecallHit(
                        id=hit_id or f"hit-{len(hits)}",
                        content=str(content or ""),
                        score=score_f,
                        reason=str(reason) if reason is not None else None,
                    )
                )
            return
        if isinstance(obj, str) and obj.strip():
            hits.append(RecallHit(id=f"hit-{len(hits)}", content=obj.strip()))

    if isinstance(raw, (dict, list)):
        _from_obj(raw)
        if hits:
            return hits

    text = _content_to_text(raw)
    parsed = _try_parse_json(text)
    if parsed is not None:
        _from_obj(parsed)
        if hits:
            return hits

    # Legacy line protocol
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        hit_id = ""
        content = ""
        score: float | None = None
        reason: str | None = None
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("id:"):
                hit_id = line[3:].strip()
            elif line.startswith("content:"):
                content = line[8:].strip()
            elif line.startswith("score:"):
                try:
                    score = float(line[6:].strip())
                except ValueError:
                    pass
            elif line.startswith("reason:"):
                reason = line[7:].strip()
        if hit_id or content:
            hits.append(
                RecallHit(id=hit_id, content=content, score=score, reason=reason)
            )

    if not hits and text.strip():
        hits.append(RecallHit(id="hit-0", content=text.strip()[:2000]))
    return hits


def parse_ingest_result(raw: Any) -> IngestResult:
    """Parse smart_ingest result; fail closed unless success is recognized."""
    text = _content_to_text(raw)
    obj: Any = raw if isinstance(raw, dict) else _try_parse_json(text)

    if isinstance(obj, dict):
        decision = str(
            obj.get("decision") or obj.get("status") or obj.get("action") or ""
        ).lower()
        memory_id = (
            obj.get("memory_id")
            or obj.get("memoryId")
            or obj.get("id")
            or obj.get("nodeId")
        )
        detail = obj.get("detail") or obj.get("message") or obj.get("reason")
        success_tokens = {
            "create",
            "created",
            "stored",
            "store",
            "reinforce",
            "reinforced",
            "merged",
            "merge",
            "ok",
            "success",
            "updated",
        }
        fail_tokens = {
            "claim_contradicts_memory",
            "contradict",
            "rejected",
            "error",
            "fail",
            "failed",
            "skip",
            "skipped",
        }
        if any(t in decision for t in fail_tokens):
            return IngestResult(
                ok=False,
                memory_id=str(memory_id) if memory_id else None,
                status=decision or "failed",
                detail=str(detail) if detail else text[:500],
            )
        if decision in success_tokens or any(t == decision for t in success_tokens):
            return IngestResult(
                ok=True,
                memory_id=str(memory_id) if memory_id else None,
                status=decision or "stored",
                detail=str(detail) if detail else None,
            )
        if obj.get("ok") is True or obj.get("success") is True:
            return IngestResult(
                ok=True,
                memory_id=str(memory_id) if memory_id else None,
                status=decision or "stored",
                detail=str(detail) if detail else None,
            )
        if obj.get("ok") is False or obj.get("success") is False:
            return IngestResult(
                ok=False,
                memory_id=str(memory_id) if memory_id else None,
                status=decision or "failed",
                detail=str(detail) if detail else text[:500],
            )

    # Legacy line protocol
    ok: bool | None = None
    memory_id: str | None = None
    status: str | None = None
    detail: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ok:"):
            ok = line[3:].strip().lower() in ("true", "1", "yes")
        elif line.startswith("memory_id:"):
            memory_id = line[10:].strip()
        elif line.startswith("status:"):
            status = line[7:].strip()
        elif line.startswith("detail:"):
            detail = line[7:].strip()
        elif line.lower().startswith("decision:"):
            status = line.split(":", 1)[1].strip()

    if ok is True or (status and status.lower() in ("stored", "merged", "create", "reinforce")):
        return IngestResult(
            ok=True, memory_id=memory_id, status=status or "stored", detail=detail
        )
    if ok is False or (status and "contradict" in status.lower()):
        return IngestResult(
            ok=False,
            memory_id=memory_id,
            status=status or "failed",
            detail=detail or text[:500],
        )

    # Fail closed when structure is unknown
    return IngestResult(
        ok=False,
        memory_id=memory_id,
        status=status or "unparsed",
        detail=detail or (text[:500] if text else "unrecognized ingest response"),
    )
