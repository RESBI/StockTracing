"""Simple circuit breaker for external data sources.

Usage:
    @circuit("yfinance", failure_threshold=5, recovery_timeout=60)
    def fetch(...): ...

States:
- CLOSED: normal, calls pass through; failures increment counter
- OPEN: after `failure_threshold` consecutive failures, reject for `recovery_timeout` seconds
- HALF_OPEN: after timeout, one trial call allowed; success closes, failure reopens
"""
import time
import threading
from functools import wraps
from typing import Callable


class CircuitOpenError(Exception):
    """Raised when a circuit is open (calls rejected)."""


class _Circuit:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        if self._failures < self.failure_threshold:
            return "CLOSED"
        if time.time() - self._opened_at >= self.recovery_timeout:
            return "HALF_OPEN"
        return "OPEN"

    def allow(self) -> bool:
        with self._lock:
            return self.state != "OPEN"

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.time()


_circuits: dict[str, _Circuit] = {}
_registry_lock = threading.Lock()


def _get_circuit(name: str, failure_threshold: int, recovery_timeout: int) -> _Circuit:
    with _registry_lock:
        if name not in _circuits:
            _circuits[name] = _Circuit(name, failure_threshold, recovery_timeout)
        return _circuits[name]


def circuit(name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
    """Decorator: wrap an external call with a named circuit breaker."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            c = _get_circuit(name, failure_threshold, recovery_timeout)
            state = c.state
            if state == "OPEN":
                raise CircuitOpenError(f"Circuit '{name}' is open")
            try:
                result = func(*args, **kwargs)
                c.record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception as e:
                c.record_failure()
                raise
        return wrapper
    return decorator


def circuit_status() -> dict:
    """Snapshot all circuits for observability."""
    with _registry_lock:
        return {name: {"state": c.state, "failures": c._failures} for name, c in _circuits.items()}
