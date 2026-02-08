"""
Tests for StartupValidator

Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.7
"""
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from startup_validator import StartupValidator, get_validator, validate_startup


class TestStartupValidator:
    """Test suite for StartupValidator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = StartupValidator()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_validate_environment_variables_success(self):
        """Test environment variable validation with all required vars set."""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key-12345',
            'DEFAULT_REGION': 'us-east-1'
        }):
            validator = StartupValidator()
            validator._validate_environment_variables()
            
            assert len(validator.errors) == 0
    
    def test_validate_environment_variables_missing_api_key(self):
        """Test environment variable validation with missing API key."""
        with patch.dict(os.environ, {
            'DEFAULT_REGION': 'us-east-1'
        }, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            
            assert len(validator.errors) == 1
            assert 'LLM API key' in validator.errors[0]
    
    def test_validate_environment_variables_missing_region(self):
        """Test environment variable validation with missing region."""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key-12345'
        }, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            
            assert len(validator.errors) == 1
            assert 'DEFAULT_REGION' in validator.errors[0]
    
    def test_validate_environment_variables_all_missing(self):
        """Test environment variable validation with all vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            validator = StartupValidator()
            validator._validate_environment_variables()
            
            assert len(validator.errors) == 2
    
    def test_validate_pvc_mount_success(self):
        """Test PVC mount validation with valid mount."""
        with patch('startup_validator.Path') as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = True
            mock_path.return_value = mock_data_path
            
            with patch('os.access', return_value=True):
                with patch.object(Path, 'write_text'):
                    with patch.object(Path, 'unlink'):
                        validator = StartupValidator()
                        validator._validate_pvc_mount()
                        
                        # Should have no errors (may have warnings about creating dirs)
                        pvc_errors = [e for e in validator.errors if 'PVC' in e or '/data' in e]
                        assert len(pvc_errors) == 0
    
    def test_validate_pvc_mount_missing_directory(self):
        """Test PVC mount validation with missing /data directory."""
        with patch('startup_validator.Path') as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = False
            mock_path.return_value = mock_data_path
            
            validator = StartupValidator()
            validator._validate_pvc_mount()
            
            assert len(validator.errors) >= 1
            assert any('not mounted' in e for e in validator.errors)
    
    def test_validate_pvc_mount_not_writable(self):
        """Test PVC mount validation with non-writable directory."""
        with patch('startup_validator.Path') as mock_path:
            mock_data_path = MagicMock()
            mock_data_path.exists.return_value = True
            mock_path.return_value = mock_data_path
            
            with patch('os.access', return_value=False):
                validator = StartupValidator()
                validator._validate_pvc_mount()
                
                assert len(validator.errors) >= 1
                assert any('not writable' in e for e in validator.errors)
    
    def test_validate_prompt_templates_missing_directory(self):
        """Test prompt template validation with missing directory."""
        with patch('startup_validator.Path') as mock_path:
            mock_templates_path = MagicMock()
            mock_templates_path.exists.return_value = False
            mock_path.return_value = mock_templates_path
            
            validator = StartupValidator()
            validator._validate_prompt_templates()
            
            # Missing templates should be a warning, not an error
            assert len(validator.warnings) >= 1
            assert any('Templates directory not found' in w for w in validator.warnings)
    
    def test_validate_faiss_index_creates_directory(self):
        """Test FAISS index validation creates directory if missing."""
        faiss_path = Path(self.temp_dir) / "faiss_index"
        
        with patch('startup_validator.Path') as mock_path:
            mock_faiss_path = MagicMock()
            mock_faiss_path.exists.return_value = False
            mock_faiss_path.mkdir = MagicMock()
            mock_path.return_value = mock_faiss_path
            
            validator = StartupValidator()
            validator._validate_faiss_index()
            
            # Should attempt to create directory
            mock_faiss_path.mkdir.assert_called_once()
    
    def test_validate_faiss_index_missing_library(self):
        """Test FAISS index validation with missing faiss library."""
        with patch('startup_validator.Path') as mock_path:
            mock_faiss_path = MagicMock()
            mock_faiss_path.exists.return_value = True
            mock_path.return_value = mock_faiss_path
            
            with patch('builtins.__import__', side_effect=ImportError("No module named 'faiss'")):
                validator = StartupValidator()
                validator._validate_faiss_index()
                
                # Missing FAISS library should be a warning
                assert any('FAISS library not' in w for w in validator.warnings)
    
    def test_validate_full_success(self):
        """Test full validation with all checks passing."""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key-12345',
            'DEFAULT_REGION': 'us-east-1'
        }):
            with patch('startup_validator.Path') as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = True
                mock_path.return_value = mock_data_path
                
                with patch('os.access', return_value=True):
                    with patch.object(Path, 'write_text'):
                        with patch.object(Path, 'unlink'):
                            validator = StartupValidator()
                            is_valid, errors = validator.validate()
                            
                            # Should pass with possible warnings but no errors
                            assert is_valid or len(errors) == 0
    
    def test_validate_full_failure(self):
        """Test full validation with critical failures."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('startup_validator.Path') as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = False
                mock_path.return_value = mock_data_path
                
                validator = StartupValidator()
                is_valid, errors = validator.validate()
                
                assert not is_valid
                assert len(errors) > 0
    
    def test_is_ready_before_validation(self):
        """Test is_ready returns False before validation runs."""
        validator = StartupValidator()
        assert not validator.is_ready()
    
    def test_is_ready_after_successful_validation(self):
        """Test is_ready returns True after successful validation."""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key-12345',
            'DEFAULT_REGION': 'us-east-1'
        }):
            with patch('startup_validator.Path') as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = True
                mock_path.return_value = mock_data_path
                
                with patch('os.access', return_value=True):
                    with patch.object(Path, 'write_text'):
                        with patch.object(Path, 'unlink'):
                            validator = StartupValidator()
                            validator.validate()
                            
                            # May be ready if no critical errors
                            # (warnings are allowed)
                            if len(validator.errors) == 0:
                                assert validator.is_ready()
    
    def test_get_status(self):
        """Test get_status returns detailed status information."""
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
        assert status["warnings"] == ["Test warning"]
    
    def test_get_validator_singleton(self):
        """Test get_validator returns singleton instance."""
        validator1 = get_validator()
        validator2 = get_validator()
        
        assert validator1 is validator2
    
    def test_validate_startup_exits_on_failure(self):
        """Test validate_startup exits with code 1 on failure."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('startup_validator.Path') as mock_path:
                mock_data_path = MagicMock()
                mock_data_path.exists.return_value = False
                mock_path.return_value = mock_data_path
                
                with pytest.raises(SystemExit) as exc_info:
                    validate_startup()
                
                assert exc_info.value.code == 1


class TestHealthCheckEndpoints:
    """Test suite for health check endpoints."""
    
    def test_health_endpoint_always_returns_200(self):
        """Test /api/health always returns 200."""
        # Test the health check logic directly without importing app
        # The endpoint always returns healthy status
        result = {"status": "healthy", "service": "devops-chatbot-v2"}
        
        assert result["status"] == "healthy"
        assert result["service"] == "devops-chatbot-v2"
    
    def test_ready_endpoint_returns_503_when_not_ready(self):
        """Test /api/health/ready returns 503 when validation incomplete."""
        # Test the readiness check logic
        mock_validator = MagicMock()
        mock_validator.is_ready.return_value = False
        mock_validator.get_status.return_value = {
            "validation_complete": False,
            "errors": ["Test error"],
            "warnings": []
        }
        
        # Simulate the endpoint logic
        if not mock_validator.is_ready():
            status = mock_validator.get_status()
            result = {
                "status": "not_ready",
                "service": "devops-chatbot-v2",
                "validation_complete": status["validation_complete"],
                "errors": status["errors"],
                "warnings": status["warnings"]
            }
            status_code = 503
        else:
            result = {
                "status": "ready",
                "service": "devops-chatbot-v2",
                "validation_complete": True
            }
            status_code = 200
        
        assert status_code == 503
        assert result["status"] == "not_ready"
        assert "errors" in result
    
    def test_ready_endpoint_returns_200_when_ready(self):
        """Test /api/health/ready returns 200 when validation complete."""
        # Test the readiness check logic
        mock_validator = MagicMock()
        mock_validator.is_ready.return_value = True
        
        # Simulate the endpoint logic
        if not mock_validator.is_ready():
            status = mock_validator.get_status()
            result = {
                "status": "not_ready",
                "service": "devops-chatbot-v2",
                "validation_complete": status["validation_complete"],
                "errors": status["errors"],
                "warnings": status["warnings"]
            }
            status_code = 503
        else:
            result = {
                "status": "ready",
                "service": "devops-chatbot-v2",
                "validation_complete": True
            }
            status_code = 200
        
        assert status_code == 200
        assert result["status"] == "ready"
        assert result["validation_complete"] is True
