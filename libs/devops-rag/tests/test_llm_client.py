"""Tests for LLM client."""

import pytest

from devops_rag.llm_client import LLMClient, OllamaClient


def test_llm_client_create_ollama():
    """Test creating Ollama client."""
    client = LLMClient.create(
        provider="ollama",
        base_url="http://localhost:11434",
        model="mistral",
    )
    assert isinstance(client, OllamaClient)
    assert client.model == "mistral"


def test_ollama_client_count_tokens():
    """Test token counting."""
    client = OllamaClient()
    tokens = client.count_tokens("Hello world")
    assert tokens > 0


def test_ollama_client_estimate_cost():
    """Test cost estimation (should be 0 for local)."""
    client = OllamaClient()
    cost = client.estimate_cost(100, 50)
    assert cost == 0.0


def test_llm_client_create_invalid_provider():
    """Test creating client with invalid provider."""
    with pytest.raises(ValueError):
        LLMClient.create(provider="invalid_provider")


def test_ollama_client_initialization():
    """Test Ollama client initialization."""
    client = OllamaClient(
        base_url="http://localhost:11434",
        model="mistral",
    )
    assert client.base_url == "http://localhost:11434"
    assert client.model == "mistral"
    assert client.total_prompt_tokens == 0
    assert client.total_completion_tokens == 0
