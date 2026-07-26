"""Unit tests for LLM (RAGIntegration) client wiring."""
from unittest.mock import Mock, patch

import pytest

from rag_integration import RAGIntegration, get_rag_integration, reset_rag_integration


class TestRAGIntegration:
    """Test RAGIntegration LLM-only class."""

    @patch("rag_integration.OpenAIClient")
    def test_initialization_openai(self, mock_openai):
        mock_openai.return_value = Mock()
        rag = RAGIntegration(
            llm_provider="openai",
            llm_model="gpt-3.5-turbo",
            api_key="test-key",
        )
        assert rag.llm_provider == "openai"
        assert rag.llm_model == "gpt-3.5-turbo"
        mock_openai.assert_called_once()

    @patch("rag_integration.AnthropicClient")
    def test_initialization_anthropic(self, mock_anthropic):
        mock_anthropic.return_value = Mock()
        rag = RAGIntegration(
            llm_provider="anthropic",
            llm_model="claude-3-sonnet",
            api_key="test-key",
        )
        assert rag.llm_provider == "anthropic"
        mock_anthropic.assert_called_once()

    @patch("rag_integration.OpenAIClient")
    def test_get_token_usage(self, mock_openai):
        mock_llm = Mock()
        mock_llm.total_prompt_tokens = 100
        mock_llm.total_completion_tokens = 50
        mock_openai.return_value = mock_llm
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        usage = rag.get_token_usage()
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150

    @patch("rag_integration.OpenAIClient")
    def test_estimate_cost(self, mock_openai):
        mock_llm = Mock()
        mock_llm.total_prompt_tokens = 1000
        mock_llm.total_completion_tokens = 500
        mock_llm.estimate_cost.return_value = 0.0025
        mock_openai.return_value = mock_llm
        rag = RAGIntegration(llm_provider="openai", api_key="test-key")
        assert rag.estimate_cost() == 0.0025
        mock_llm.estimate_cost.assert_called_once_with(1000, 500)

    @patch("rag_integration.OpenAIClient")
    def test_get_initialization_status(self, mock_openai):
        mock_openai.return_value = Mock()
        rag = RAGIntegration(
            llm_provider="openai",
            llm_model="gpt-4",
            api_key="test-key",
        )
        status = rag.get_initialization_status()
        assert status["llm_client"]["initialized"] is True
        assert status["llm_client"]["provider"] == "openai"
        assert status["llm_client"]["model"] == "gpt-4"
        assert "memory" in status
        assert status["fully_functional"] is True

    @patch("rag_integration.OpenAIClient")
    def test_init_llm_client_import_error(self, mock_openai):
        mock_openai.side_effect = ImportError("No module named 'openai'")
        with pytest.raises(ValueError) as exc_info:
            RAGIntegration(llm_provider="openai", api_key="test-key")
        assert "library not available" in str(exc_info.value).lower()

    @patch("rag_integration.OpenAIClient")
    def test_init_llm_client_api_key_error(self, mock_openai):
        mock_openai.side_effect = Exception("Invalid API key")
        with pytest.raises(ValueError) as exc_info:
            RAGIntegration(llm_provider="openai", api_key="invalid")
        assert "api key" in str(exc_info.value).lower() or "llm client" in str(
            exc_info.value
        ).lower()


class TestGetRAGIntegration:
    """Singleton factory."""

    def teardown_method(self):
        reset_rag_integration()

    @patch("rag_integration.RAGIntegration")
    def test_get_rag_integration_creates_instance(self, mock_rag_class):
        reset_rag_integration()
        mock_instance = Mock()
        mock_rag_class.return_value = mock_instance
        result = get_rag_integration(llm_provider="openai", api_key="test-key")
        assert result == mock_instance
        mock_rag_class.assert_called_once()

    @patch("rag_integration.RAGIntegration")
    def test_get_rag_integration_returns_existing(self, mock_rag_class):
        existing = Mock()
        import rag_integration

        rag_integration._rag_integration = existing
        result = get_rag_integration()
        assert result == existing
        mock_rag_class.assert_not_called()
