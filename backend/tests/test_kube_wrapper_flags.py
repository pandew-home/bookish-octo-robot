from __future__ import annotations

import os

import pytest

from kube_policy.authorize import WrapperRequest, authorize
from kube_policy.policy import KubeApiPolicy, load_policy_from_env
from kube_policy.redact import redact_response


def _clear_kube_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("KUBE_API_"):
            monkeypatch.delenv(key, raising=False)


class TestPolicyLoadFromEnv:
    def test_default_policy_values(self, monkeypatch: pytest.MonkeyPatch):
        _clear_kube_env(monkeypatch)
        policy = load_policy_from_env()

        assert policy.allowRead is True
        assert policy.allowMutate is False
        assert policy.allowedMethods == ["GET"]
        assert policy.secrets.allowIdentify is True
        assert policy.secrets.allowReadData is False
        assert policy.secrets.allowMutate is False

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch):
        _clear_kube_env(monkeypatch)
        monkeypatch.setenv("KUBE_API_ALLOW_READ", "false")
        monkeypatch.setenv("KUBE_API_ALLOW_MUTATE", "true")
        monkeypatch.setenv("KUBE_API_ALLOWED_METHODS", "GET,POST,DELETE")
        policy = load_policy_from_env()

        assert policy.allowRead is False
        assert policy.allowMutate is True
        assert policy.allowedMethods == ["GET", "POST", "DELETE"]

    def test_deny_exec_subresource_alias_env(self, monkeypatch: pytest.MonkeyPatch):
        """Helm historically set KUBE_API_DENY_EXEC_SUBRESOURCE; loader must honor it."""
        _clear_kube_env(monkeypatch)
        monkeypatch.setenv("KUBE_API_DENY_EXEC_SUBRESOURCE", "false")
        policy = load_policy_from_env()
        assert policy.deny.execSubresource is False


class TestAuthorizeMatrix:
    def _default_policy(self) -> KubeApiPolicy:
        return KubeApiPolicy()

    def test_get_allowed_by_default(self):
        req = WrapperRequest(method="GET", resource="pods", namespace="default")
        result = authorize(req, self._default_policy())

        assert result.allowed is True

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_mutate_blocked_when_mutate_off(self, method: str):
        req = WrapperRequest(method=method, resource="pods", namespace="default")
        result = authorize(req, self._default_policy())

        assert result.allowed is False
        assert "mutate" in result.reason.lower()

    def test_secret_list_allowed_when_identify_on(self):
        policy = self._default_policy()
        policy.secrets.allowIdentify = True
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        result = authorize(req, policy)

        assert result.allowed is True

    def test_secret_data_get_blocked_when_read_data_off(self):
        policy = self._default_policy()
        policy.secrets.allowReadData = False
        policy.secrets.allowIdentify = True
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        result = authorize(req, policy)

        assert result.allowed is True

    def test_secret_mutate_blocked_when_mutate_off(self):
        policy = self._default_policy()
        policy.secrets.allowMutate = False
        req = WrapperRequest(method="POST", resource="secrets", namespace="default")
        result = authorize(req, policy)

        assert result.allowed is False
        assert "mutate" in result.reason.lower()

    def _mutate_policy(self) -> KubeApiPolicy:
        return KubeApiPolicy(
            allowMutate=True,
            allowedMethods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        )

    def test_exec_subresource_blocked_by_default(self):
        req = WrapperRequest(
            method="POST",
            resource="pods",
            namespace="default",
            subresource="exec",
        )
        result = authorize(req, self._mutate_policy())

        assert result.allowed is False
        assert "exec" in result.reason.lower()

    def test_log_subresource_blocked_by_default(self):
        req = WrapperRequest(
            method="GET",
            resource="pods",
            namespace="default",
            name="nginx",
            subresource="log",
        )
        result = authorize(req, self._default_policy())
        assert result.allowed is False
        assert "log" in result.reason.lower()

    def test_portforward_subresource_blocked_by_default(self):
        req = WrapperRequest(
            method="POST",
            resource="pods",
            namespace="default",
            subresource="portforward",
        )
        result = authorize(req, self._mutate_policy())

        assert result.allowed is False
        assert "portforward" in result.reason.lower()

    def test_proxy_subresource_blocked_by_default(self):
        req = WrapperRequest(
            method="GET",
            resource="services",
            namespace="default",
            subresource="proxy",
        )
        result = authorize(req, self._mutate_policy())

        assert result.allowed is False
        assert "proxy" in result.reason.lower()

    def test_serviceaccount_create_blocked_by_default(self):
        req = WrapperRequest(
            method="POST",
            resource="serviceaccounts",
            namespace="default",
        )
        result = authorize(req, self._mutate_policy())

        assert result.allowed is False
        assert "serviceaccount" in result.reason.lower()

    def test_cluster_scoped_write_blocked_by_default(self):
        req = WrapperRequest(method="POST", resource="namespaces", namespace="")
        result = authorize(req, self._mutate_policy())

        assert result.allowed is False
        assert "cluster" in result.reason.lower()


class TestRedact:
    def _default_policy(self) -> KubeApiPolicy:
        return KubeApiPolicy()

    def test_redact_strips_data_from_secret(self):
        policy = self._default_policy()
        policy.secrets.allowReadData = False
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        response = {
            "metadata": {"name": "my-secret"},
            "data": {"username": "YWRtaW4=", "password": "cEBzc3cwcmQ="},
        }

        result = redact_response(response, req, policy)

        assert "data" not in result
        assert "stringData" not in result
        assert result["dataKeys"] == ["password", "username"]

    def test_redact_preserves_data_keys(self):
        policy = self._default_policy()
        policy.secrets.allowReadData = False
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        response = {
            "metadata": {"name": "my-secret"},
            "data": {"z-key": "dmFs", "a-key": "dmFs"},
        }

        result = redact_response(response, req, policy)

        assert result["dataKeys"] == ["a-key", "z-key"]

    def test_redact_passes_through_non_secret(self):
        policy = self._default_policy()
        req = WrapperRequest(method="GET", resource="pods", namespace="default")
        response = {"metadata": {"name": "my-pod"}, "status": {"phase": "Running"}}

        result = redact_response(response, req, policy)

        assert result["metadata"]["name"] == "my-pod"
        assert result["status"]["phase"] == "Running"

    def test_redact_handles_list_response(self):
        policy = self._default_policy()
        policy.secrets.allowReadData = False
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        response = {
            "items": [
                {"metadata": {"name": "s1"}, "data": {"k": "dg=="}},
                {"metadata": {"name": "s2"}, "data": {"k2": "dg=="}},
            ]
        }

        result = redact_response(response, req, policy)

        assert len(result["items"]) == 2
        for item in result["items"]:
            assert "data" not in item
            assert "dataKeys" in item

    def test_no_redact_when_allow_read_data(self):
        policy = self._default_policy()
        policy.secrets.allowReadData = True
        req = WrapperRequest(method="GET", resource="secrets", namespace="default")
        response = {"metadata": {"name": "my-secret"}, "data": {"k": "dg=="}}

        result = redact_response(response, req, policy)

        assert "data" in result
        assert result["data"] == {"k": "dg=="}
