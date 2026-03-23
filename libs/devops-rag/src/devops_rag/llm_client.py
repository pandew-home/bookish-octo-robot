"""LLM client abstraction for multiple providers."""

import json
import os
import re
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod


def _approx_token_count(text: str) -> int:
    """Heuristic token estimator that avoids external tokenizer deps.

    Uses both word boundaries and character length to reduce under-counting
    compared to a simple len/4 rule. Falls back to 0 for empty input.
    """

    if not text:
        return 0

    # Count non-whitespace sequences; better for code and punctuation-heavy text.
    by_word = len(re.findall(r"\S+", text))

    # Character-based fallback (~4 chars per token is a common rule of thumb).
    by_char = max(len(text) // 4, 1)

    return max(by_word, by_char)


class LLMClientBase(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate response from LLM.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens in response

        Returns:
            Generated response string
        """
        pass

    @abstractmethod
    def embed(self, text: str) -> list:
        """Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Input text

        Returns:
            Token count
        """
        pass

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for API call.

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        pass


class OpenAIClient(LLMClientBase):
    """OpenAI LLM client."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo", base_url: Optional[str] = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-3.5-turbo)
            base_url: Optional base URL for OpenAI-compatible APIs (e.g., OpenRouter)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self._client = None  # Lazy initialization

    @property
    def client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                import openai
                if not self.api_key:
                    raise RuntimeError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
                # Support custom base URL for OpenRouter or other OpenAI-compatible APIs
                # The newer OpenAI SDK (v1.0+) doesn't accept 'proxies' parameter in __init__
                try:
                    if self.base_url:
                        self._client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
                    else:
                        self._client = openai.OpenAI(api_key=self.api_key)
                except TypeError as e:
                    # Handle case where unexpected kwargs are passed (version compatibility)
                    if "proxies" in str(e) or "unexpected keyword" in str(e):
                        # Fallback: try without any extra params that might cause issues
                        if self.base_url:
                            # Create client with only essential params
                            import httpx
                            http_client = httpx.Client()
                            self._client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=http_client)
                        else:
                            self._client = openai.OpenAI(api_key=self.api_key)
                    else:
                        raise
            except ImportError:
                raise RuntimeError("OpenAI package not installed. Install with: pip install openai")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate response from OpenAI.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens in response

        Returns:
            Generated response string
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
        )

        # Track tokens
        self.total_prompt_tokens += response.usage.prompt_tokens
        self.total_completion_tokens += response.usage.completion_tokens

        return response.choices[0].message.content

    def generate_with_tools(self, messages: List[Any], tools: List[Dict]) -> Dict[str, Any]:
        """Generate a response with tool-calling support.

        Returns {"type": "text", "text": ...} when the LLM produces a final answer,
        or {"type": "tool_calls", "tool_calls": [...]} when it wants to call tools.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        self.total_prompt_tokens += response.usage.prompt_tokens
        self.total_completion_tokens += response.usage.completion_tokens

        if msg.tool_calls:
            return {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments),
                    }
                    for tc in msg.tool_calls
                ],
            }
        return {"type": "text", "text": msg.content or ""}

    def embed(self, text: str) -> list:
        """Generate embedding using OpenAI.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )

        return response.data[0].embedding

    def count_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation).

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return _approx_token_count(text)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for OpenAI API call.

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        # GPT-3.5-turbo pricing (as of 2024)
        prompt_cost_per_1k = 0.0005
        completion_cost_per_1k = 0.0015

        return (prompt_tokens / 1000 * prompt_cost_per_1k) + (
            completion_tokens / 1000 * completion_cost_per_1k
        )


class AnthropicClient(LLMClientBase):
    """Anthropic Claude LLM client."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-haiku-20240307"):
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key
            model: Model name (default: claude-3-haiku-20240307)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self._client = None  # Lazy initialization

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                if not self.api_key:
                    raise RuntimeError("Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("Anthropic package not installed. Install with: pip install anthropic")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate response from Anthropic.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens in response

        Returns:
            Generated response string
        """
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        # Track tokens
        self.total_prompt_tokens += message.usage.input_tokens
        self.total_completion_tokens += message.usage.output_tokens

        return message.content[0].text

    def generate_with_tools(self, messages: List[Any], tools: List[Dict]) -> Dict[str, Any]:
        """Generate a response with tool-calling support (Anthropic format).

        Converts OpenAI-style tool definitions to Anthropic format internally.
        Returns {"type": "text", "text": ...} or {"type": "tool_calls", ...}.
        Anthropic requires max_tokens; use 4096 as a generous default.
        """
        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = self.client.messages.create(**kwargs)
        self.total_prompt_tokens += response.usage.input_tokens
        self.total_completion_tokens += response.usage.output_tokens

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if tool_uses:
            return {
                "type": "tool_calls",
                "tool_calls": [
                    {"id": tu.id, "name": tu.name, "args": tu.input}
                    for tu in tool_uses
                ],
                "raw_content": response.content,
            }
        return {"type": "text", "text": text_blocks[0].text if text_blocks else ""}

    def embed(self, text: str) -> list:
        """Generate embedding using Anthropic.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        # Anthropic doesn't provide embeddings, use fallback
        raise NotImplementedError("Anthropic does not provide embedding API. Use OpenAI or other provider.")

    def count_tokens(self, text: str) -> int:
        """Estimate token count.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return _approx_token_count(text)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for Anthropic API call.

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        # Claude 3 Haiku pricing (as of 2024)
        prompt_cost_per_1k = 0.00025
        completion_cost_per_1k = 0.00125

        return (prompt_tokens / 1000 * prompt_cost_per_1k) + (
            completion_tokens / 1000 * completion_cost_per_1k
        )


class OllamaClient(LLMClientBase):
    """Ollama local LLM client."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        """Initialize Ollama client.

        Args:
            base_url: Ollama server base URL
            model: Model name (default: mistral)
        """
        self.base_url = base_url
        self.model = model
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

        try:
            import requests
            self.requests = requests
        except ImportError:
            self.requests = None

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate response from Ollama.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens in response

        Returns:
            Generated response string
        """
        if not self.requests:
            raise RuntimeError("requests library not installed. Install requests package.")

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "num_predict": max_tokens,
        }

        response = self.requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        return result.get("response", "")

    def embed(self, text: str) -> list:
        """Generate embedding using Ollama.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.requests:
            raise RuntimeError("requests library not installed. Install requests package.")

        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text,
        }

        response = self.requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        return result.get("embedding", [])

    def count_tokens(self, text: str) -> int:
        """Estimate token count.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return _approx_token_count(text)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for Ollama (local, no cost).

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD (always 0 for local)
        """
        return 0.0


class LLMClient:
    """Factory for creating LLM clients."""

    @staticmethod
    def create(
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> LLMClientBase:
        """Create LLM client based on provider.

        Args:
            provider: Provider name ("openai", "anthropic", "ollama")
            api_key: API key for provider
            model: Model name
            base_url: Base URL for Ollama

        Returns:
            LLMClientBase instance
        """
        provider = provider or os.getenv("AI_PROVIDER", "openai").lower()

        if provider == "openai":
            return OpenAIClient(
                api_key=api_key or os.getenv("AI_API_KEY"),
                model=model or os.getenv("AI_MODEL", "gpt-3.5-turbo"),
                base_url=base_url or os.getenv("AI_API_BASE"),
            )
        elif provider == "anthropic":
            return AnthropicClient(
                api_key=api_key or os.getenv("AI_API_KEY"),
                model=model or os.getenv("AI_MODEL", "claude-3-haiku-20240307"),
            )
        elif provider == "ollama":
            return OllamaClient(
                base_url=base_url or os.getenv("AI_API_BASE", "http://localhost:11434"),
                model=model or os.getenv("AI_MODEL", "mistral"),
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
