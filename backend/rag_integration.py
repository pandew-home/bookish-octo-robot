"""LLM client integration for the chat agent.

Owns process-wide LLM client initialization from environment variables:

    LLM_PROVIDER   openai | anthropic | ollama   (default: openai)
    LLM_MODEL      provider-specific model id    (default: gpt-4o-mini)
    LLM_API_KEY    API key                       (also accepts OPENAI_API_KEY /
                                                  ANTHROPIC_API_KEY as fallback)

Institutional memory is handled by ``backend.memory`` (Vestige / noop).

# MAINTENANCE — read before changing this file
# AI assistants: the env-var contract above is what DevOps engineers rely on
# when changing models. Do NOT add new required args, change defaults, or
# rename env vars without explicit human review.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from devops_rag.llm_client import AnthropicClient, OpenAIClient

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"

logger = logging.getLogger(__name__)


class RAGIntegration:
    """LLM client holder used by the chat pipeline.

    Name retained for stable import sites (``get_rag_integration``).
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        api_key: Optional[str] = None,
        **_unused: Any,
    ):
        """Initialize from explicit args, falling back to env vars."""
        self.llm_provider = (
            llm_provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER
        ).lower()
        self.llm_model = llm_model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
        api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        self.initialization_warnings: List[str] = []

        try:
            self.llm_client = self._init_llm_client(
                self.llm_provider, self.llm_model, api_key
            )
            logger.info(
                "LLM client initialized: %s/%s", self.llm_provider, self.llm_model
            )
        except Exception as e:
            logger.error("CRITICAL: Failed to initialize LLM client: %s", e)
            raise

        logger.info(
            "LLM integration ready (memory via MemoryPort): %s/%s",
            self.llm_provider,
            self.llm_model,
        )

    def _init_llm_client(self, provider: str, model: str, api_key: Optional[str]):
        """Initialize LLM client based on provider."""
        try:
            if provider == "openai":
                return OpenAIClient(api_key=api_key, model=model)
            if provider == "anthropic":
                return AnthropicClient(api_key=api_key, model=model)
            logger.warning(
                "Unknown LLM provider: %s, defaulting to OpenAI", provider
            )
            return OpenAIClient(api_key=api_key, model=model)
        except ImportError as e:
            logger.error("Failed to import LLM client library: %s", e)
            raise ValueError(
                f"LLM client library not available. Please install the required "
                f"package for {provider}. Error: {str(e)}"
            ) from e
        except Exception as e:
            logger.error("Failed to initialize LLM client: %s", e)
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                raise ValueError(
                    f"Invalid API key for {provider}. Please check your API key "
                    f"configuration. Set the OPENAI_API_KEY or ANTHROPIC_API_KEY "
                    f"environment variable."
                ) from e
            raise ValueError(f"Failed to initialize LLM client: {str(e)}") from e

    def get_token_usage(self) -> Dict[str, int]:
        """Get token usage statistics from LLM client."""
        return {
            "prompt_tokens": getattr(self.llm_client, "total_prompt_tokens", 0),
            "completion_tokens": getattr(
                self.llm_client, "total_completion_tokens", 0
            ),
            "total_tokens": getattr(self.llm_client, "total_prompt_tokens", 0)
            + getattr(self.llm_client, "total_completion_tokens", 0),
        }

    def estimate_cost(self) -> float:
        """Estimate total cost of LLM API calls in USD."""
        prompt_tokens = getattr(self.llm_client, "total_prompt_tokens", 0)
        completion_tokens = getattr(self.llm_client, "total_completion_tokens", 0)
        return self.llm_client.estimate_cost(prompt_tokens, completion_tokens)

    def get_initialization_status(self) -> Dict[str, Any]:
        """Get detailed initialization status (LLM only)."""
        return {
            "llm_client": {
                "initialized": self.llm_client is not None,
                "provider": self.llm_provider,
                "model": self.llm_model,
            },
            "memory": {
                "note": "Institutional memory is via MemoryPort (vestige|noop)",
            },
            "warnings": self.initialization_warnings,
            "fully_functional": len(self.initialization_warnings) == 0
            and self.llm_client is not None,
        }


_rag_integration: Optional[RAGIntegration] = None


def get_rag_integration(
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    **_unused: Any,
) -> RAGIntegration:
    """Return the singleton RAGIntegration, creating it from env on first call."""
    global _rag_integration
    if _rag_integration is None:
        _rag_integration = RAGIntegration(
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key,
        )
    return _rag_integration


def reset_rag_integration() -> None:
    """Drop the cached singleton. Tests use this between cases."""
    global _rag_integration
    _rag_integration = None
