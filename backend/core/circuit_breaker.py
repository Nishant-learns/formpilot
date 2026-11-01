"""Distributed Circuit Breaker Pattern for External Government Portals & Services.

Guarantees system resilience and fail-fast protection against 502/503/504 Bad Gateway
or Gateway Timeout storms typical of high-concurrency government portal releases.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"          # Normal operation: traffic flows freely
    OPEN = "OPEN"              # Fail-fast: requests immediately rejected
    HALF_OPEN = "HALF_OPEN"    # Probing: testing target health with canary requests


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""

    def __init__(self, breaker_name: str, retry_after: float) -> None:
        self.breaker_name = breaker_name
        self.retry_after = round(retry_after, 1)
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN. Target portal is currently degraded. "
            f"Retry after {self.retry_after}s."
        )


class CircuitBreaker:
    """Thread-safe and async-safe three-state circuit breaker."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.01, recovery_timeout)
        self.half_open_success_threshold = max(1, half_open_success_threshold)

        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._total_trips: int = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        # Check for automatic transition from OPEN to HALF_OPEN when recovery timeout elapses
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            if (time.monotonic() - self._last_failure_time) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                self._last_state_change = time.monotonic()
        return self._state

    def can_execute(self) -> bool:
        """Return True if a request is permitted to proceed, False otherwise."""
        current_state = self.state
        if current_state in {CircuitState.CLOSED, CircuitState.HALF_OPEN}:
            return True
        return False

    def time_until_retry(self) -> float:
        """Seconds remaining before breaker attempts HALF_OPEN probe."""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        remaining = self.recovery_timeout - elapsed
        return max(0.0, remaining)

    def record_success(self) -> None:
        """Signal successful communication with the target portal."""
        current_state = self.state
        if current_state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._last_state_change = time.monotonic()
        elif current_state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Signal failed communication or connection error with target portal."""
        self._last_failure_time = time.monotonic()
        current_state = self.state

        if current_state == CircuitState.HALF_OPEN:
            # Any failure during probing immediately trips breaker back to OPEN
            self._state = CircuitState.OPEN
            self._total_trips += 1
            self._success_count = 0
            self._last_state_change = time.monotonic()
        elif current_state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._total_trips += 1
                self._last_state_change = time.monotonic()

    async def execute(self, action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callable protected by the circuit breaker."""
        async with self._lock:
            if not self.can_execute():
                raise CircuitBreakerOpenError(self.name, self.time_until_retry())

        try:
            if inspect.iscoroutinefunction(action):
                result = await action(*args, **kwargs)
            else:
                result = action(*args, **kwargs)
            async with self._lock:
                self.record_success()
            return result
        except Exception:
            async with self._lock:
                self.record_failure()
            raise

    def get_metrics(self) -> Dict[str, Any]:
        """Inspection telemetry for observability cockpit and dashboard."""
        curr_state = self.state
        return {
            "name": self.name,
            "state": curr_state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "success_count": self._success_count,
            "recovery_timeout_seconds": self.recovery_timeout,
            "time_until_retry_seconds": round(self.time_until_retry(), 1) if curr_state == CircuitState.OPEN else 0.0,
            "total_trips": self._total_trips,
            "healthy": curr_state == CircuitState.CLOSED,
        }

    def reset(self) -> None:
        """Administrative manual reset."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_state_change = time.monotonic()


# Singleton breaker registry
_CIRCUIT_BREAKERS: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_success_threshold: int = 2,
) -> CircuitBreaker:
    """Retrieve or create named circuit breaker."""
    if name not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_success_threshold=half_open_success_threshold,
        )
    return _CIRCUIT_BREAKERS[name]


def get_all_circuit_breaker_metrics() -> Dict[str, Any]:
    """Retrieve metrics across all registered circuit breakers."""
    return {name: cb.get_metrics() for name, cb in _CIRCUIT_BREAKERS.items()}
