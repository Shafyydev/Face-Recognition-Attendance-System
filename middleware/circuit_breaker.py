"""
Circuit Breaker Pattern
========================
Implements the Circuit Breaker pattern to protect the system from cascading
failures when external services (SMS gateway, APIs) become unavailable.

States:
    CLOSED   -> Normal operation. Requests pass through.
    OPEN     -> Service is down. Requests are immediately rejected.
    HALF_OPEN -> Testing recovery. A single request is allowed through.

Transitions:
    CLOSED   -> OPEN:      After `failure_threshold` consecutive failures
    OPEN     -> HALF_OPEN: After `recovery_timeout` seconds
    HALF_OPEN -> CLOSED:   On success of the test request
    HALF_OPEN -> OPEN:     On failure of the test request

Usage:
    from middleware.circuit_breaker import CircuitBreaker

    sms_breaker = CircuitBreaker(
        name="sms_gateway",
        failure_threshold=3,
        recovery_timeout=30,
    )

    # As a decorator:
    @sms_breaker
    def send_sms(to, message):
        ...

    # Or as a context manager:
    with sms_breaker:
        provider.send(number, message)
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable
from functools import wraps


class CircuitState(Enum):
    """The three states of a circuit breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when the circuit is OPEN and a request is rejected."""

    def __init__(self, breaker_name: str, remaining_seconds: float):
        self.breaker_name = breaker_name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN. "
            f"Service unavailable. Retry in {remaining_seconds:.0f}s."
        )


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker implementation.

    Args:
        name: Human-readable name for logging
        failure_threshold: Number of consecutive failures before opening
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN
        success_threshold: Successes needed in HALF_OPEN to close the circuit
        on_state_change: Optional callback(name, old_state, new_state)
        excluded_exceptions: Exception types that should NOT count as failures
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
        on_state_change: Optional[Callable] = None,
        excluded_exceptions: tuple = (),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.on_state_change = on_state_change
        self.excluded_exceptions = excluded_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._last_state_change: float = time.time()
        self._lock = threading.RLock()

        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejections = 0

    @property
    def state(self) -> CircuitState:
        """Current state of the circuit breaker."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state with logging and callback."""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

        print(
            f"[CIRCUIT BREAKER] '{self.name}': "
            f"{old_state.value.upper()} -> {new_state.value.upper()}",
            flush=True,
        )

        if self.on_state_change:
            try:
                self.on_state_change(self.name, old_state, new_state)
            except Exception:
                pass

    def _record_success(self):
        """Record a successful call."""
        with self._lock:
            self._total_successes += 1
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def _record_failure(self):
        """Record a failed call."""
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def call(self, func, *args, **kwargs):
        """
        Execute a function through the circuit breaker.

        Raises CircuitBreakerError if the circuit is OPEN.
        """
        with self._lock:
            self._total_calls += 1
            current_state = self.state  # May trigger OPEN -> HALF_OPEN

            if current_state == CircuitState.OPEN:
                self._total_rejections += 1
                remaining = self.recovery_timeout - (time.time() - self._last_failure_time)
                raise CircuitBreakerError(self.name, max(0, remaining))

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.excluded_exceptions:
            # These exceptions don't count as failures
            self._record_success()
            raise
        except Exception:
            self._record_failure()
            raise

    def __call__(self, func):
        """Use as a decorator."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper

    def __enter__(self):
        """Use as a context manager — check state on entry."""
        with self._lock:
            self._total_calls += 1
            current_state = self.state

            if current_state == CircuitState.OPEN:
                self._total_rejections += 1
                remaining = self.recovery_timeout - (time.time() - self._last_failure_time)
                raise CircuitBreakerError(self.name, max(0, remaining))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record success or failure on context manager exit."""
        if exc_type is None:
            self._record_success()
        elif self.excluded_exceptions and issubclass(exc_type, self.excluded_exceptions):
            self._record_success()
        else:
            self._record_failure()
        return False  # Don't suppress exceptions

    def reset(self):
        """Manually reset the circuit breaker to CLOSED."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0

    def stats(self) -> dict:
        """Return circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejections": self._total_rejections,
                "last_failure": self._last_failure_time,
                "last_state_change": self._last_state_change,
            }


# ---------------------------------------------------------------------------
# Pre-configured circuit breakers for the Attendance System
# ---------------------------------------------------------------------------

# SMS Gateway circuit breaker — opens after 3 failures, recovers in 30s
sms_circuit_breaker = CircuitBreaker(
    name="sms_gateway",
    failure_threshold=3,
    recovery_timeout=30,
    success_threshold=1,
    excluded_exceptions=(ValueError,),  # Don't trip on validation errors
)
