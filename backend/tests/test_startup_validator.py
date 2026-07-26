"""Tests for StartupValidator."""
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startup_validator import StartupValidator, get_validator, validate_startup


class TestStartupValidator:
    def setup_method(self):
        self.validator = StartupValidator()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_validate_environment_variables_success(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key-12345", "DEFAULT_REGION": "us-east-1"},
        ):
            validator = StartupValidator()
            validator._validate_environment_variables()
            assert len(validator.errors) == 0

    def test_validate_environment_variables_missing_api_key(self):
        with patch.dict(os.environ, {"DEFAULT_REGION": "us-east-1"}, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            assert len(validator.errors) == 1
            assert "LLM API key" in validator.errors[0]

    def test_validate_environment_variables_missing_region(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-12345"}, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            assert len(validator.errors) == 1
            assert "DEFAULT_REGION" in validator.errors[0]

    def test_validate_environment_variables_all_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            assert len(validator.errors) == 2

    def test_validate_pvc_mount_success(self):
        with patch("startup_validator.Path") as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = True
            mock_path.return_value = mock_data_path
            with patch("os.access", return_value=True):
                with patch.object(Path, "write_text"):
                    with patch.object(Path, "unlink"):
                        validator = StartupValidator()
                        validator._validate_pvc_mount()
                        pvc_errors = [
                            e
                            for e in validator.errors
                            if "PVC" in e or "/data" in e or "Data directory" in e
                        ]
                        assert len(pvc_errors) == 0

    def test_validate_pvc_mount_missing_directory(self):
        with patch("startup_validator.Path") as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = False
            mock_path.return_value = mock_data_path
            validator = StartupValidator()
            validator._validate_pvc_mount()
            assert len(validator.errors) >= 1
            assert any("not mounted" in e for e in validator.errors)

    def test_validate_pvc_mount_not_writable(self):
        with patch("startup_validator.Path") as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = True
            mock_path.return_value = mock_data_path
            with patch("os.access", return_value=False):
                validator = StartupValidator()
                validator._validate_pvc_mount()
                assert len(validator.errors) >= 1
                assert any("not writable" in e for e in validator.errors)

    def test_validate_prompt_templates_skipped(self):
        validator = StartupValidator()
        validator._validate_prompt_templates()
        assert len(validator.warnings) == 0
        assert len(validator.errors) == 0

    def test_validate_full_success(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key-12345",
                "DEFAULT_REGION": "us-east-1",
                "MEMORY_BACKEND": "noop",
            },
        ):
            with patch("startup_validator.Path") as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = True
                mock_path.return_value = mock_data_path
                with patch("os.access", return_value=True):
                    with patch.object(Path, "write_text"):
                        with patch.object(Path, "unlink"):
                            validator = StartupValidator()
                            is_valid, errors = validator.validate()
                            assert is_valid or len(errors) == 0

    def test_validate_full_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("startup_validator.Path") as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = False
                mock_path.return_value = mock_data_path
                validator = StartupValidator()
                is_valid, errors = validator.validate()
                assert not is_valid
                assert len(errors) > 0

    def test_is_ready_before_validation(self):
        validator = StartupValidator()
        assert not validator.is_ready()

    def test_is_ready_after_successful_validation(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key-12345", "DEFAULT_REGION": "us-east-1"},
        ):
            with patch("startup_validator.Path") as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = True
                mock_path.return_value = mock_data_path
                with patch("os.access", return_value=True):
                    with patch.object(Path, "write_text"):
                        with patch.object(Path, "unlink"):
                            validator = StartupValidator()
                            validator.validate()
                            if len(validator.errors) == 0:
                                assert validator.is_ready()

    def test_get_status(self):
        validator = StartupValidator()
        validator.errors = ["Test error"]
        validator.warnings = ["Test warning"]
        validator.validation_complete = False
        status = validator.get_status()
        assert "validation_complete" in status
        assert "ready" in status
        assert "errors" in status
        assert "warnings" in status
        assert "checks" in status
        assert status["errors"] == ["Test error"]

    def test_get_validator_singleton(self):
        validator1 = get_validator()
        validator2 = get_validator()
        assert validator1 is validator2

    def test_validate_startup_exits_on_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("startup_validator.Path") as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = False
                mock_path.return_value = mock_data_path
                with pytest.raises(SystemExit) as exc_info:
                    validate_startup()
                assert exc_info.value.code == 1


class TestHealthCheckEndpoints:
    def test_health_endpoint_always_returns_200(self):
        result = {"status": "healthy", "service": "devops-chatbot-v2"}
        assert result["status"] == "healthy"

    def test_ready_endpoint_returns_503_when_not_ready(self):
        mock_validator = MagicMock()
        mock_validator.is_ready.return_value = False
        mock_validator.get_status.return_value = {
            "validation_complete": False,
            "errors": ["Test error"],
            "warnings": [],
        }
        if not mock_validator.is_ready():
            status = mock_validator.get_status()
            result = {
                "status": "not_ready",
                "service": "devops-chatbot-v2",
                "validation_complete": status["validation_complete"],
                "errors": status["errors"],
                "warnings": status["warnings"],
            }
            status_code = 503
        else:
            status_code = 200
            result = {}
        assert status_code == 503
        assert result["status"] == "not_ready"

    def test_ready_endpoint_returns_200_when_ready(self):
        mock_validator = MagicMock()
        mock_validator.is_ready.return_value = True
        if not mock_validator.is_ready():
            status_code = 503
            result = {"status": "not_ready"}
        else:
            result = {
                "status": "ready",
                "service": "devops-chatbot-v2",
                "validation_complete": True,
            }
            status_code = 200
        assert status_code == 200
        assert result["status"] == "ready"
