from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy dependencies that aren't installed in the test env
# (devops_rag, devops_k8s, etc.) so we can import api.chat.
# ---------------------------------------------------------------------------

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_PARENT = str(Path(__file__).resolve().parent.parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)


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


_ensure_stub("devops_rag")
_ensure_stub(
    "devops_rag.llm_client",
    {
        "OpenAIClient": type("OpenAIClient", (), {}),
        "AnthropicClient": type("AnthropicClient", (), {}),
    },
)
_ensure_stub("devops_k8s")

# Only stub AWS packages when missing — never replace a real botocore install
# (empty ModuleType stubs break other tests that import eks_auth).
try:
    import botocore  # noqa: F401
    import botocore.signers  # noqa: F401
except Exception:
    _ensure_stub("botocore")
    _ensure_stub(
        "botocore.exceptions",
        {
            "ClientError": type("ClientError", (Exception,), {}),
            "BotoCoreError": type("BotoCoreError", (Exception,), {}),
        },
    )
try:
    import boto3  # noqa: F401
except Exception:
    _ensure_stub("boto3")

from memory.port import IngestResult, MemoryUnavailableError, RecallHit


DURABLE_QUERY = "How do I fix the CrashLoopBackOff on my nginx pod?"
DURABLE_RESPONSE = (
    "The pod is crashing because of a misconfigured environment variable. "
    "To fix this, run the following commands:\n"
    "- kubectl set env deployment/nginx APP_ENV=production\n"
    "- kubectl rollout restart deployment/nginx\n"
    "- kubectl rollout status deployment/nginx\n"
    "This should resolve the CrashLoopBackOff state."
) * 5

EPHEMERAL_QUERY = "hi"
EPHEMERAL_RESPONSE = "Hey there! How can I help you today?"


def _mock_rag_response(response_text: str) -> dict:
    return {
        "response": response_text,
        "citations": [],
        "errors": [],
        "metadata": {},
    }


def _build_patches(memory_port: Mock, *, response_text: str = DURABLE_RESPONSE):
    """Build all mocks needed by process_chat_query."""
    mock_rag = Mock()
    mock_rag.llm_client = Mock()
    mock_rag.get_token_usage.return_value = {}

    session_clients = {
        "core_v1": Mock(),
        "apps_v1": Mock(),
        "custom_objects": Mock(),
        "networking_v1": Mock(),
    }
    selected_cluster = {"name": "prod", "version": "v1.28"}

    mock_agent = Mock()
    mock_agent.run = AsyncMock(return_value=_mock_rag_response(response_text))

    mock_hist = Mock()
    mock_hist.create_conversation.return_value = "conv_123"
    mock_hist.save_message.return_value = None

    mock_k8sgpt = Mock()
    mock_k8sgpt.read_results = AsyncMock(return_value=[])

    return {
        "get_memory_port": lambda: memory_port,
        "get_rag_integration": lambda: mock_rag,
        "session_clients": session_clients,
        "selected_cluster": selected_cluster,
        "get_policy": lambda: Mock(),
        "agent_cls": lambda **kw: mock_agent,
        "hist": mock_hist,
        "k8sgpt_cls": lambda *a, **kw: mock_k8sgpt,
        "rate_limiter_check": AsyncMock(return_value=(True, 60, 19)),
        "agent": mock_agent,
    }


@contextmanager
def _patched_chat(chat_mod, p):
    """Patch chat pipeline: session clients for tools, SA for K8sGPT."""
    mock_rl = Mock()
    mock_rl.check_rate_limit = p["rate_limiter_check"]
    with (
        patch.object(chat_mod, "rate_limiter", mock_rl),
        patch.object(chat_mod, "get_policy", p["get_policy"]),
        patch.object(chat_mod, "K8sGPTReader", p["k8sgpt_cls"]),
        patch.object(chat_mod, "get_rag_integration", p["get_rag_integration"]),
        patch.object(chat_mod, "get_memory_port", p["get_memory_port"]),
        patch.object(chat_mod, "AgentEngine", p["agent_cls"]),
        patch.object(chat_mod, "conversation_history", p["hist"]),
        patch.object(
            chat_mod,
            "_get_session_cluster_context",
            return_value=(p["session_clients"], p["selected_cluster"]),
        ),
    ):
        yield mock_rl


@pytest.fixture
def _import_chat():
    """Import api.chat with all stubs in place."""
    import api.chat as chat_mod

    return chat_mod


class TestDegradedMemoryNoop:
    """T019 — When MEMORY_BACKEND=noop, chat still returns 200."""

    @pytest.mark.asyncio
    async def test_noop_backend_returns_200(self, _import_chat):
        chat_mod = _import_chat
        from memory.noop import NoopMemory

        noop = NoopMemory()
        p = _build_patches(noop)

        with _patched_chat(chat_mod, p):
            request = chat_mod.ChatRequest(
                query=DURABLE_QUERY, user_id="user_1", cluster_name="prod"
            )
            response = await chat_mod.process_chat_query(
                request, session_id="sess-1"
            )

            assert response.response == DURABLE_RESPONSE
            assert response.metadata["memory_degraded"] is False
            assert response.metadata["memory_hits"] == 0


class TestMemoryUnavailableError:
    """T019 — When memory raises MemoryUnavailableError, chat works and sets degraded."""

    @pytest.mark.asyncio
    async def test_memory_error_sets_degraded_true(self, _import_chat):
        chat_mod = _import_chat

        broken = Mock()
        broken.recall = AsyncMock(side_effect=MemoryUnavailableError("down"))
        broken.ingest = AsyncMock(side_effect=MemoryUnavailableError("down"))

        p = _build_patches(broken)

        with _patched_chat(chat_mod, p):
            request = chat_mod.ChatRequest(
                query=DURABLE_QUERY, user_id="user_1", cluster_name="prod"
            )
            response = await chat_mod.process_chat_query(
                request, session_id="sess-1"
            )

            assert response.response == DURABLE_RESPONSE
            assert response.metadata["memory_degraded"] is True
            assert response.metadata["memory_hits"] == 0


class TestEphemeralTurnNoIngest:
    """T019 — Ephemeral turns (greetings) do NOT trigger ingest."""

    @pytest.mark.asyncio
    async def test_greeting_does_not_trigger_ingest(self, _import_chat):
        chat_mod = _import_chat

        memory = Mock()
        memory.recall = AsyncMock(return_value=[])
        memory.ingest = AsyncMock(return_value=IngestResult(ok=True, status="stored"))

        p = _build_patches(memory, response_text=EPHEMERAL_RESPONSE)

        with _patched_chat(chat_mod, p):
            request = chat_mod.ChatRequest(
                query=EPHEMERAL_QUERY, user_id="user_1", cluster_name="prod"
            )
            response = await chat_mod.process_chat_query(
                request, session_id="sess-1"
            )

            assert response.response == EPHEMERAL_RESPONSE
            assert response.metadata["memory_ingested"] is False
            assert response.metadata["memory_ingest_status"] == "skipped"
            memory.ingest.assert_not_called()


class TestDurableTurnTriggersIngest:
    """T019 — Durable turns DO trigger ingest."""

    @pytest.mark.asyncio
    async def test_durable_turn_calls_ingest(self, _import_chat):
        chat_mod = _import_chat

        memory = Mock()
        memory.recall = AsyncMock(
            return_value=[
                RecallHit(id="h1", content="past fix for nginx OOM", score=0.9),
            ]
        )
        memory.ingest = AsyncMock(return_value=IngestResult(ok=True, status="stored"))

        p = _build_patches(memory)

        with _patched_chat(chat_mod, p):
            request = chat_mod.ChatRequest(
                query=DURABLE_QUERY, user_id="user_1", cluster_name="prod"
            )
            response = await chat_mod.process_chat_query(
                request, session_id="sess-1"
            )

            assert response.metadata["memory_ingested"] is True
            assert response.metadata["memory_ingest_status"] == "stored"
            assert response.metadata["memory_hits"] == 1
            memory.ingest.assert_called_once()
            content = memory.ingest.call_args.kwargs["content"]
            assert "cluster:" in content
            assert "problem:" in content
            assert "source: devops-chatbot-auto" in content
            p["hist"].create_conversation.assert_called()
            assert (
                p["hist"].create_conversation.call_args.kwargs.get("cluster_name")
                == "prod"
            )


class TestChatUsesSessionClients:
    """Live agent tools must receive session clients, not SA core_v1."""

    @pytest.mark.asyncio
    async def test_agent_gets_session_k8s_clients(self, _import_chat):
        chat_mod = _import_chat
        from memory.noop import NoopMemory

        p = _build_patches(NoopMemory())
        captured = {}

        def capture_agent(**kwargs):
            captured.update(kwargs)
            return p["agent"]

        p["agent_cls"] = capture_agent

        with _patched_chat(chat_mod, p):
            request = chat_mod.ChatRequest(
                query=DURABLE_QUERY, user_id="user_1", cluster_name="prod"
            )
            await chat_mod.process_chat_query(request, session_id="sess-1")

        assert captured["k8s_clients"] is p["session_clients"]
        assert "core_v1" in captured["k8s_clients"]
