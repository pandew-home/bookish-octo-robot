"""Unit/contract tests for memory factory + Helm path agreement.

NOTE: SC-003 (PVC-backed recall survives pod restart) is a **manual/release**
metric in specs/002-vestige-memory-mcp/checklists/release-validation.md.
This file does not spin a cluster; it only verifies factory/env contracts.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from backend.memory import get_memory_port, reset_memory_port
from backend.memory.noop import NoopMemory
from backend.memory.port import MemoryHealth


class TestNoopMemoryAcrossRestart:
    def test_factory_singleton_returns_same_noop_instance(self):
        reset_memory_port()
        with patch.dict(os.environ, {"MEMORY_BACKEND": "noop"}):
            first = get_memory_port()
            second = get_memory_port()
            assert isinstance(first, NoopMemory)
            assert first is second

    def test_reset_then_factory_yields_new_instance(self):
        """Simulate process restart: reset singleton then construct again."""
        reset_memory_port()
        with patch.dict(os.environ, {"MEMORY_BACKEND": "noop"}):
            first = get_memory_port()
            reset_memory_port()
            second = get_memory_port()
            assert isinstance(second, NoopMemory)
            assert first is not second

    async def test_noop_health_reports_degraded(self):
        mem = NoopMemory()
        health = await mem.health()
        assert isinstance(health, MemoryHealth)
        assert health.ready is False
        assert health.degraded is True
        assert health.backend == "noop"


class TestPvcPathFromEnv:
    def test_chatbot_chart_colocates_vestige_on_shared_pvc(self):
        """Vestige runs in-process image; data under chatbot PVC /data/vestige."""
        values = (
            Path(__file__).resolve().parents[2]
            / "helm"
            / "devops-chatbot"
            / "values.yaml"
        )
        text = values.read_text(encoding="utf-8")
        assert 'backend: "vestige"' in text
        assert "http://127.0.0.1:3928" in text
        assert 'dataDir: "/data/vestige"' in text

    def test_memory_backend_env_controls_factory(self):
        reset_memory_port()
        with patch.dict(
            os.environ,
            {"MEMORY_BACKEND": "vestige", "VESTIGE_HTTP_URL": "http://localhost:9999"},
        ):
            port = get_memory_port()
            assert port.__class__.__name__ == "VestigeMcpMemory"

    def test_memory_backend_noop_is_default_when_unset(self):
        """Unset MEMORY_BACKEND must match startup_validator (safe local boot)."""
        reset_memory_port()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("MEMORY_BACKEND", "VESTIGE_HTTP_URL")
        }
        with patch.dict(os.environ, env, clear=True):
            port = get_memory_port()
            assert isinstance(port, NoopMemory)
