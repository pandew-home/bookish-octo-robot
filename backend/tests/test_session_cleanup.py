"""Session teardown: scrub credentials and empty K8s session clients."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from credential_store import CredentialStore, StoredCredentials, scrub_credentials


@pytest.fixture
def sample_credentials():
    now = datetime.now()
    return StoredCredentials(
        auth_mode="aws",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token="FwoGZXIvYXdzEBQaDH-secret-token",
        region="us-east-1",
        user_arn="arn:aws:iam::123456789012:user/test-user",
        account_id="123456789012",
        expires_at=now + timedelta(hours=1),
        created_at=now,
    )


class TestScrubCredentials:
    def test_scrub_empties_secret_fields(self, sample_credentials):
        scrub_credentials(sample_credentials)
        assert sample_credentials.access_key is None
        assert sample_credentials.secret_key is None
        assert sample_credentials.session_token is None
        assert sample_credentials.kubeconfig_content is None
        assert sample_credentials.user_arn is None


class TestCredentialStoreRemoveHook:
    def test_remove_scrubs_and_notifies(self, sample_credentials):
        removed = []
        store = CredentialStore(
            max_capacity=10,
            ttl_seconds=3600,
            on_session_removed=lambda sid: removed.append(sid),
        )
        store.store("sess-abc", sample_credentials)
        assert store.remove("sess-abc") is True
        assert store.get("sess-abc") is None
        assert removed == ["sess-abc"]
        # Original object scrubbed (same reference was stored)
        assert sample_credentials.access_key is None
        assert sample_credentials.secret_key is None
        assert sample_credentials.session_token is None

    def test_expire_on_get_scrubs_and_notifies(self, sample_credentials):
        removed = []
        store = CredentialStore(
            max_capacity=10,
            ttl_seconds=3600,
            on_session_removed=lambda sid: removed.append(sid),
        )
        sample_credentials.expires_at = datetime.now() - timedelta(seconds=1)
        store.store("sess-exp", sample_credentials)
        assert store.get("sess-exp") is None
        assert removed == ["sess-exp"]
        assert sample_credentials.secret_key is None

    def test_restore_same_session_notifies_for_old_clients(self, sample_credentials):
        removed = []
        store = CredentialStore(
            max_capacity=10,
            ttl_seconds=3600,
            on_session_removed=lambda sid: removed.append(sid),
        )
        store.store("sess-re", sample_credentials)
        now = datetime.now()
        replacement = StoredCredentials(
            auth_mode="aws",
            access_key="AKIA-NEW",
            secret_key="new-secret",
            session_token="new-token",
            region="us-west-2",
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        store.store("sess-re", replacement)
        assert removed == ["sess-re"]
        assert sample_credentials.access_key is None
        got = store.get("sess-re")
        assert got is not None
        assert got.access_key == "AKIA-NEW"


def _run_cleanup_k8s_clients_inline(clients):
    """Mirror cluster_manager.cleanup_k8s_clients without importing botocore chain."""
    if not clients:
        return
    clients["_closed"] = True
    try:
        api_client = clients.get("_api_client")
        if api_client is not None:
            conf = getattr(api_client, "configuration", None)
            if conf is not None:
                conf.api_key = {}
                conf.api_key_prefix = {}
            try:
                api_client.close()
            except Exception:
                pass
    finally:
        clients.clear()
        clients["_closed"] = True


class TestCleanupK8sClientsBehavior:
    def test_cleanup_wipes_api_key_and_marks_closed(self):
        conf = MagicMock()
        conf.api_key = {"authorization": "Bearer secret-token"}
        conf.api_key_prefix = {"authorization": "Bearer"}
        api_client = MagicMock()
        api_client.configuration = conf

        clients = {
            "core_v1": MagicMock(),
            "_api_client": api_client,
            "_ca_cert_path": None,
        }
        _run_cleanup_k8s_clients_inline(clients)
        api_client.close.assert_called_once()
        assert conf.api_key == {}
        assert conf.api_key_prefix == {}
        assert clients == {"_closed": True}
