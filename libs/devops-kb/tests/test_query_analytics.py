# improved-sniffle/devops-chatbot/libs/devops-kb/tests/test_query_analytics.py

import tempfile
from pathlib import Path

import pytest

from devops_kb.query_analytics import QueryAnalytics


def test_default_storage_uses_tempdir():
    """Default storage path should be inside the system temp directory."""
    qa = QueryAnalytics()
    assert qa.storage_path is not None
    assert str(qa.storage_path).startswith(tempfile.gettempdir())
    assert qa.queries_file is not None


def test_fallback_when_initial_mkdir_fails(monkeypatch):
    """If the initial mkdir (e.g., /data) raises PermissionError, QueryAnalytics should
    fall back to a writable temp directory on the next attempt.
    """
    calls = {"n": 0}
    orig_mkdir = Path.mkdir

    def fake_mkdir(self, parents=False, exist_ok=False):
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate permission error on the first attempt
            raise PermissionError("simulated permission denied")
        # On subsequent attempts, delegate to the original implementation
        return orig_mkdir(self, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    qa = QueryAnalytics(storage_path="/data/analytics")
    # First call should have failed, second (fallback) should have succeeded.
    assert calls["n"] >= 2
    assert qa.storage_path is not None
    assert str(qa.storage_path).startswith(tempfile.gettempdir())
    assert qa.queries_file is not None


def test_disable_when_all_mkdir_fail(monkeypatch):
    """If all attempts to create storage directories fail, analytics should be disabled
    (storage_path and queries_file should be None to avoid raising on instantiation).
    """
    def always_raise(self, parents=False, exist_ok=False):
        raise PermissionError("simulated permission denied")

    monkeypatch.setattr(Path, "mkdir", always_raise)

    qa = QueryAnalytics(storage_path="/data/analytics")
    assert qa.storage_path is None
    assert qa.queries_file is None
