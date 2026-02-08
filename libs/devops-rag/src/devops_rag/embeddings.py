"""Embedding cache for cost optimization."""

import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional


class EmbeddingCache:
    """Cache embeddings to avoid recomputing."""

    def __init__(self, cache_path: str = "/data/embeddings-cache"):
        """Initialize embedding cache.

        Args:
            cache_path: Path to cache directory
        """
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.memory_cache: Dict[str, List[float]] = {}

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text.

        Args:
            text: Input text

        Returns:
            Cache key (SHA256 hash)
        """
        return hashlib.sha256(text.encode()).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache.

        Args:
            text: Input text

        Returns:
            Embedding vector or None if not cached
        """
        cache_key = self._get_cache_key(text)

        # Check memory cache first
        if cache_key in self.memory_cache:
            return self.memory_cache[cache_key]

        # Check disk cache
        cache_file = self.cache_path / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                embedding = data.get("embedding")
                if embedding:
                    # Store in memory cache
                    self.memory_cache[cache_key] = embedding
                    return embedding
            except Exception:
                pass

        return None

    def set(self, text: str, embedding: List[float]) -> None:
        """Store embedding in cache.

        Args:
            text: Input text
            embedding: Embedding vector
        """
        cache_key = self._get_cache_key(text)

        # Store in memory cache
        self.memory_cache[cache_key] = embedding

        # Store in disk cache
        cache_file = self.cache_path / f"{cache_key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(
                    {
                        "text": text[:100],  # Store first 100 chars for reference
                        "embedding": embedding,
                    },
                    f,
                )
        except Exception:
            pass

    def clear_memory(self) -> None:
        """Clear memory cache."""
        self.memory_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Statistics dictionary
        """
        cache_files = list(self.cache_path.glob("*.json"))
        return {
            "memory_cache_size": len(self.memory_cache),
            "disk_cache_size": len(cache_files),
            "cache_path": str(self.cache_path),
        }
