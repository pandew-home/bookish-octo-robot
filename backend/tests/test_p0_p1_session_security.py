"""Regression tests for P0/P1 session, token, and authz fixes."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _purge_stub_modules(*prefixes: str) -> None:
    """Drop empty ModuleType stubs (from other tests) so real packages can load."""
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            mod = sys.modules[name]
            if getattr(mod, "__file__", None) is None:
                del sys.modules[name]


_purge_stub_modules("botocore", "boto3")

# Real botocore is installed; boto3 may not be in this env — provide a minimal stub.
if "boto3" not in sys.modules:
    _boto3 = types.ModuleType("boto3")
    _boto3.Session = MagicMock  # type: ignore[attr-defined]
    _boto3.client = MagicMock  # type: ignore[attr-defined]
    sys.modules["boto3"] = _boto3


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


class TestRefreshEksBearer:
    def test_refresh_updates_api_key(self):
        from cluster_manager import refresh_eks_bearer_on_clients
        from credential_store import StoredCredentials

        conf = MagicMock()
        conf.api_key = {"authorization": "Bearer old"}
        api_client = MagicMock()
        api_client.configuration = conf
        clients = {"_api_client": api_client, "_auth_mode": "aws"}
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="sec",
            session_token="tok",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with patch(
            "cluster_manager.get_eks_bearer_token", return_value="k8s-aws-v1.fresh"
        ):
            refresh_eks_bearer_on_clients(clients, creds, "prod-cluster")
        assert conf.api_key == {"authorization": "Bearer k8s-aws-v1.fresh"}
        assert "_token_refreshed_at" in clients

    def test_refresh_missing_api_client_raises(self):
        from cluster_manager import refresh_eks_bearer_on_clients
        from credential_store import StoredCredentials

        clients = {"_auth_mode": "aws"}
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="sec",
            session_token="tok",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with pytest.raises(RuntimeError, match="ApiClient is missing"):
            refresh_eks_bearer_on_clients(clients, creds, "prod-cluster")

    def test_refresh_closed_clients_raises(self):
        from cluster_manager import refresh_eks_bearer_on_clients
        from credential_store import StoredCredentials

        conf = MagicMock()
        api_client = MagicMock()
        api_client.configuration = conf
        clients = {
            "_api_client": api_client,
            "_auth_mode": "aws",
            "_closed": True,
        }
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="sec",
            session_token="tok",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with pytest.raises(RuntimeError, match="closed"):
            refresh_eks_bearer_on_clients(clients, creds, "prod-cluster")

    def test_ensure_skips_when_fresh(self):
        import time
        from cluster_manager import ensure_eks_bearer_fresh
        from credential_store import StoredCredentials

        conf = MagicMock()
        api_client = MagicMock()
        api_client.configuration = conf
        clients = {
            "_api_client": api_client,
            "_auth_mode": "aws",
            "_token_refreshed_at": time.monotonic(),
        }
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="sec",
            session_token="tok",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with patch(
            "cluster_manager.get_eks_bearer_token", return_value="k8s-aws-v1.x"
        ) as mock_tok:
            did = ensure_eks_bearer_fresh(clients, creds, "prod", max_age_seconds=45)
        assert did is False
        mock_tok.assert_not_called()

    def test_ensure_refreshes_when_stale(self):
        import time
        from cluster_manager import ensure_eks_bearer_fresh
        from credential_store import StoredCredentials

        conf = MagicMock()
        conf.api_key = {}
        api_client = MagicMock()
        api_client.configuration = conf
        clients = {
            "_api_client": api_client,
            "_auth_mode": "aws",
            "_token_refreshed_at": time.monotonic() - 100,
        }
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="sec",
            session_token="tok",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with patch(
            "cluster_manager.get_eks_bearer_token", return_value="k8s-aws-v1.stale-ok"
        ):
            did = ensure_eks_bearer_fresh(clients, creds, "prod", max_age_seconds=45)
        assert did is True
        assert conf.api_key == {"authorization": "Bearer k8s-aws-v1.stale-ok"}

    def test_execute_tool_calls_ensure_auth_fresh(self):
        from agent_tools import AgentContext, execute_tool

        ensure = MagicMock()
        ctx = AgentContext(
            k8s_clients={
                "core_v1": None,
                "_ensure_auth_fresh": ensure,
                "_auth_mode": "aws",
            },
            k8sgpt_results=[],
            skills={},
            cluster_version="v1.28",
            kube_policy=None,
        )
        # core_v1 missing → tool errors after auth refresh
        result = execute_tool(
            "get_pod_status", {"namespace": "ns", "name": "p"}, ctx
        )
        ensure.assert_called_once()
        assert "error" in result


class TestGetK8sClientsForSession:
    def test_returns_shallow_copy_and_refreshes_aws(self):
        import api.clusters as clusters_mod
        from credential_store import StoredCredentials

        sid = "sess-snapshot-1"
        conf = MagicMock()
        conf.api_key = {}
        api_client = MagicMock()
        api_client.configuration = conf
        stored = {
            "core_v1": Mock(name="core"),
            "_api_client": api_client,
            "_auth_mode": "aws",
        }
        clusters_mod._session_k8s_clients[sid] = stored
        clusters_mod._session_clusters[sid] = {"name": "prod"}

        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="s",
            session_token="t",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )

        with (
            patch(
                "api.clusters.get_credentials_for_session", return_value=creds
            ),
            patch(
                "api.clusters.refresh_eks_bearer_on_clients"
            ) as mock_refresh,
        ):
            snapped = clusters_mod.get_k8s_clients_for_session(sid)

        assert snapped is not stored
        assert snapped["core_v1"] is stored["core_v1"]
        mock_refresh.assert_called_once()

        # Logout clear on session map must not empty the request snapshot.
        stored.clear()
        assert "core_v1" in snapped

        clusters_mod.clear_session_cluster(sid)

    def test_missing_cluster_raises_400(self):
        import api.clusters as clusters_mod
        from credential_store import StoredCredentials

        sid = "sess-no-cluster"
        clusters_mod._session_k8s_clients.pop(sid, None)
        clusters_mod._session_clusters.pop(sid, None)
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="s",
            session_token="t",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with patch(
            "api.clusters.get_credentials_for_session", return_value=creds
        ):
            with pytest.raises(HTTPException) as ei:
                clusters_mod.get_k8s_clients_for_session(sid)
        assert ei.value.status_code == 400

    def test_cleared_during_refresh_raises(self):
        """Teardown mid-remint must not return empty/closed clients."""
        import api.clusters as clusters_mod
        from credential_store import StoredCredentials

        sid = "sess-race-clear"
        conf = MagicMock()
        conf.api_key = {}
        api_client = MagicMock()
        api_client.configuration = conf
        stored = {
            "core_v1": Mock(name="core"),
            "_api_client": api_client,
            "_auth_mode": "aws",
        }
        clusters_mod._session_k8s_clients[sid] = stored
        clusters_mod._session_clusters[sid] = {"name": "prod"}

        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="s",
            session_token="t",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )

        def _refresh_then_clear(clients, _creds, _name):
            clusters_mod.clear_session_cluster(sid)

        with (
            patch(
                "api.clusters.get_credentials_for_session", return_value=creds
            ),
            patch(
                "api.clusters.refresh_eks_bearer_on_clients",
                side_effect=_refresh_then_clear,
            ),
        ):
            with pytest.raises(HTTPException) as ei:
                clusters_mod.get_k8s_clients_for_session(sid)
        assert ei.value.status_code == 400
        assert "re-select" in str(ei.value.detail).lower()

    def test_missing_api_client_before_refresh_raises_503(self):
        import api.clusters as clusters_mod
        from credential_store import StoredCredentials

        sid = "sess-no-api-client"
        stored = {
            "core_v1": Mock(name="core"),
            "_auth_mode": "aws",
        }
        clusters_mod._session_k8s_clients[sid] = stored
        clusters_mod._session_clusters[sid] = {"name": "prod"}
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA",
            secret_key="s",
            session_token="t",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        with patch(
            "api.clusters.get_credentials_for_session", return_value=creds
        ):
            with pytest.raises(HTTPException) as ei:
                clusters_mod.get_k8s_clients_for_session(sid)
        assert ei.value.status_code == 503
        clusters_mod.clear_session_cluster(sid)


class TestCleanupKubeconfigTemp:
    def test_cleanup_removes_kubeconfig_temp_and_wipes_key(self):
        from cluster_manager import cleanup_k8s_clients
        import tempfile
        import os

        conf = MagicMock()
        conf.api_key = {"authorization": "Bearer x"}
        conf.api_key_prefix = {}
        api_client = MagicMock()
        api_client.configuration = conf
        fd, path = tempfile.mkstemp(suffix=".kubeconfig")
        os.close(fd)
        clients = {
            "core_v1": Mock(),
            "_api_client": api_client,
            "_kubeconfig_temp_path": path,
            "_ca_cert_path": None,
        }
        cleanup_k8s_clients(clients)
        assert not os.path.exists(path)
        assert conf.api_key == {}
        # Closed marker retained so in-flight refresh fails closed.
        assert clients == {"_closed": True}


class TestChatClusterRequiredAndK8sgptSession:
    @pytest.fixture
    def chat_mod(self):
        # Prefer real botocore if installed; only stub if import already failed.
        import api.chat as chat_mod

        return chat_mod

    @pytest.mark.asyncio
    async def test_no_cluster_returns_cluster_required(self, chat_mod):
        with (
            patch.object(
                chat_mod,
                "_get_session_cluster_context",
                side_effect=HTTPException(status_code=400, detail="No cluster"),
            ),
            patch.object(
                chat_mod.rate_limiter,
                "check_rate_limit",
                new=AsyncMock(return_value=(True, 60, 19)),
            ),
        ):
            req = chat_mod.ChatRequest(
                query="why is nginx crashlooping?", user_id="u1", cluster_name="prod"
            )
            with pytest.raises(HTTPException) as ei:
                await chat_mod.process_chat_query(req, session_id="s1")
        assert ei.value.status_code == 400
        detail = ei.value.detail
        if isinstance(detail, dict):
            assert detail.get("code") == "cluster_required" or "cluster" in str(
                detail
            ).lower()

    @pytest.mark.asyncio
    async def test_k8sgpt_uses_session_custom_objects_not_sa(self, chat_mod):
        session_clients = {
            "core_v1": Mock(),
            "custom_objects": Mock(name="session_custom"),
        }
        selected = {"name": "remote-eks", "version": "v1.29"}
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=[])
        mock_rag = Mock()
        mock_rag.llm_client = Mock()
        mock_rag.get_token_usage.return_value = {}
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value={
                "response": "ok " * 50,
                "errors": [],
                "metadata": {},
            }
        )
        mock_hist = Mock()
        mock_hist.create_conversation.return_value = "c1"
        mock_hist.save_message.return_value = None

        with (
            patch.object(
                chat_mod,
                "_get_session_cluster_context",
                return_value=(session_clients, selected),
            ),
            patch.object(chat_mod, "K8sGPTReader", return_value=mock_reader) as k8s_cls,
            patch.object(chat_mod, "get_rag_integration", return_value=mock_rag),
            patch.object(chat_mod, "get_memory_port") as mp,
            patch.object(chat_mod, "AgentEngine", return_value=mock_agent),
            patch.object(chat_mod, "conversation_history", mock_hist),
            patch.object(chat_mod, "get_policy", return_value=Mock()),
            patch.object(
                chat_mod.rate_limiter,
                "check_rate_limit",
                new=AsyncMock(return_value=(True, 60, 19)),
            ),
        ):
            mp.return_value.recall = AsyncMock(return_value=[])
            req = chat_mod.ChatRequest(
                query="hi", user_id="u1", cluster_name="remote-eks"
            )
            await chat_mod.process_chat_query(req, session_id="s1")

        k8s_cls.assert_called_once_with(session_clients["custom_objects"])


class TestChatUnsafeIngestSkip:
    @pytest.mark.asyncio
    async def test_high_risk_secret_skips_ingest(self):
        import api.chat as chat_mod

        session_clients = {
            "core_v1": Mock(),
            "custom_objects": Mock(),
        }
        selected = {"name": "prod", "version": "v1.28"}
        durable_q = (
            "How do I fix CrashLoopBackOff? use key "
            "ASIAIOSFODNN7EXAMPLE and Bearer "
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx"
        )
        durable_resp = (
            "The pod is crashing. To fix this, run:\n"
            "- kubectl set env deployment/nginx APP_ENV=production\n"
            "- kubectl rollout restart deployment/nginx\n"
            "- kubectl get pods -n default\n"
            "This should resolve CrashLoopBackOff."
        ) * 5

        memory = Mock()
        memory.recall = AsyncMock(return_value=[])
        memory.ingest = AsyncMock()
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=[])
        mock_rag = Mock()
        mock_rag.llm_client = Mock()
        mock_rag.get_token_usage.return_value = {}
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value={"response": durable_resp, "errors": [], "metadata": {}}
        )
        mock_hist = Mock()
        mock_hist.create_conversation.return_value = "c1"
        mock_hist.save_message.return_value = None

        with (
            patch.object(
                chat_mod,
                "_get_session_cluster_context",
                return_value=(session_clients, selected),
            ),
            patch.object(chat_mod, "K8sGPTReader", return_value=mock_reader),
            patch.object(chat_mod, "get_rag_integration", return_value=mock_rag),
            patch.object(chat_mod, "get_memory_port", return_value=memory),
            patch.object(chat_mod, "AgentEngine", return_value=mock_agent),
            patch.object(chat_mod, "conversation_history", mock_hist),
            patch.object(chat_mod, "get_policy", return_value=Mock()),
            patch.object(
                chat_mod.rate_limiter,
                "check_rate_limit",
                new=AsyncMock(return_value=(True, 60, 19)),
            ),
        ):
            req = chat_mod.ChatRequest(
                query=durable_q, user_id="u1", cluster_name="prod"
            )
            resp = await chat_mod.process_chat_query(req, session_id="s1")

        memory.ingest.assert_not_called()
        assert resp.metadata.get("memory_ingest_status") == "unsafe"


class TestConversationEndpointsRequireSession:
    def test_export_requires_session_dependency(self):
        import inspect
        import api.chat as chat_mod

        sig = inspect.signature(chat_mod.export_conversation)
        assert "session_id" in sig.parameters

    def test_list_and_get_require_session_dependency(self):
        import inspect
        import api.chat as chat_mod

        assert "session_id" in inspect.signature(
            chat_mod.get_conversation_list
        ).parameters
        assert "session_id" in inspect.signature(
            chat_mod.get_conversation
        ).parameters


class TestLogoutClearsSessionClients:
    def test_remove_hook_clears_clients_and_scrubs(self):
        import api.clusters as clusters_mod
        from credential_store import CredentialStore, StoredCredentials

        sid = "sess-logout-1"
        conf = MagicMock()
        conf.api_key = {"authorization": "Bearer secret"}
        conf.api_key_prefix = {}
        api_client = MagicMock()
        api_client.configuration = conf
        clients = {
            "core_v1": Mock(),
            "_api_client": api_client,
            "_ca_cert_path": None,
        }
        clusters_mod._session_clusters[sid] = {"name": "prod"}
        clusters_mod._session_k8s_clients[sid] = clients

        store = CredentialStore(
            max_capacity=10,
            ttl_seconds=3600,
            on_session_removed=clusters_mod.clear_session_cluster,
        )
        creds = StoredCredentials(
            auth_mode="aws",
            access_key="AKIASECRET",
            secret_key="supersecret",
            session_token="token-value",
            region="us-east-1",
            expires_at=datetime.now() + timedelta(hours=1),
            created_at=datetime.now(),
        )
        store.store(sid, creds)

        # Double-clear path: explicit clear then remove (matches delete_credentials).
        clusters_mod.clear_session_cluster(sid)
        assert sid not in clusters_mod._session_k8s_clients
        assert clients == {"_closed": True}
        assert conf.api_key == {}

        assert store.remove(sid) is True
        assert creds.access_key is None
        assert creds.secret_key is None
        # Second clear is idempotent
        clusters_mod.clear_session_cluster(sid)
