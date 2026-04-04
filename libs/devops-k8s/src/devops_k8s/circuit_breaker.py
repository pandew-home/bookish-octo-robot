"""Simple circuit breaker for Kubernetes API calls."""

import threading
import time
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker with OPEN/HALF_OPEN/CLOSED states.

    States:
        OPEN   - normal operation (calls pass through)
        CLOSED - breaker tripped (calls blocked)
        HALF_OPEN - testing recovery (one call allowed)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "OPEN"
        self._lock = threading.Lock()

    def get_state(self) -> str:
        """Return current circuit breaker state."""
        with self._lock:
            if self._state == "CLOSED":
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = "HALF_OPEN"
            return self._state

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Call *func* through the circuit breaker.

        Raises the underlying exception (so callers can handle it) when the
        breaker is OPEN or HALF_OPEN.  Raises RuntimeError when CLOSED.
        """
        state = self.get_state()
        if state == "CLOSED":
            raise RuntimeError("Circuit breaker is CLOSED — call blocked")

        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._failure_count = 0
                self._state = "OPEN"
            return result
        except Exception:
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self._failure_threshold:
                    if self._state != "CLOSED":
                        logger.warning(
                            "Circuit breaker tripped after %d failures",
                            self._failure_count,
                        )
                    self._state = "CLOSED"
            raise
