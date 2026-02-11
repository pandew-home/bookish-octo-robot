"""
Lightweight in-memory rate limiter.

Note: This is process-local and will reset on restart. For multi-pod setups,
replace with a shared store (e.g., Redis) to enforce global limits.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after: int
    remaining: int


class RateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._requests: Dict[str, Deque[float]] = {}

    async def check_rate_limit(
        self,
        user_id: str,
        max_requests: int,
        window_seconds: int,
        endpoint: str = "default",
    ) -> Tuple[bool, int, int]:
        key = f"{endpoint}:{user_id}"
        now = time.monotonic()
        window_start = now - window_seconds

        async with self._lock:
            queue = self._requests.setdefault(key, deque())
            while queue and queue[0] < window_start:
                queue.popleft()

            if len(queue) >= max_requests:
                retry_after = max(1, int(queue[0] + window_seconds - now))
                return False, retry_after, 0

            queue.append(now)
            remaining = max_requests - len(queue)
            return True, 0, remaining


rate_limiter = RateLimiter()
