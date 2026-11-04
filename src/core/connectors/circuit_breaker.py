"""
Circuit Breaker Pattern

Voorkomt cascade failures door providers te isoleren bij herhaalde errors.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from collections.abc import Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """State van een circuit breaker."""

    CLOSED = "closed"  # Normaal - requests doorlaten
    OPEN = "open"  # Fout - requests blokkeren
    HALF_OPEN = "half_open"  # Test - 1 request toestaan


@dataclass
class CircuitBreakerConfig:
    """Configuratie voor circuit breaker."""

    # Failure thresholds
    failure_threshold: int = 5  # Aantal failures voor open
    success_threshold: int = 3  # Aantal successes voor closed (vanaf half_open)

    # Timeouts
    timeout_duration_seconds: int = 60  # Hoelang open blijven
    half_open_timeout_seconds: int = 30  # Hoelang half_open testen

    # Window settings
    failure_window_seconds: int = 60  # Tijdwindow voor failure count

    # Callbacks
    on_open: Callable[[str], Any] | None = None  # TODO(TYPE): replace Any with concrete type
    on_close: Callable[[str], Any] | None = None  # TODO(TYPE): replace Any with concrete type
    on_half_open: Callable[[str], Any] | None = None  # TODO(TYPE): replace Any with concrete type


class CircuitBreaker:
    """
    Circuit Breaker voor provider resilience.

    States:
    - CLOSED: Requests worden doorgelaten, failures worden geteld
    - OPEN: Requests worden direct geweigerd (fast fail)
    - HALF_OPEN: Een test request toestaan om te checken of service hersteld is

    Usage:
        breaker = CircuitBreaker("email_provider")

        if breaker.can_execute():
            try:
                result = await provider.execute(...)
                breaker.record_success()
            except Exception:
                breaker.record_failure()
        else:
            # Circuit is open, gebruik fallback
            return fallback_result
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._state_changed_at = datetime.now(timezone.utc)

        # Track failures in time window
        self._failures: list[datetime] = []  # List of timestamps

        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    def can_execute(self) -> bool:
        """
        Check of een request uitgevoerd mag worden.

        Returns:
            True als request mag doorgaan, False als circuit open is
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check of timeout verstreken is
            elapsed = (datetime.now(timezone.utc) - self._state_changed_at).total_seconds()
            if elapsed >= self.config.timeout_duration_seconds:
                # Transition naar half_open
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # In half_open slechts een request tegelijk
            return True

        return False

    def record_success(self) -> None:
        """Record een succesvolle request."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1

            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                logger.info(f"Circuit {self.name} closed after {self._success_count} successes")

        # Reset failure count in closed state
        if self._state == CircuitState.CLOSED:
            self._failure_count = 0
            self._failures = []

    def record_failure(self, error_message: str | None = None) -> None:
        """Record een failed request."""
        now = datetime.now(timezone.utc)

        if self._state == CircuitState.HALF_OPEN:
            # Direct terug naar open
            self._transition_to(CircuitState.OPEN)
            logger.warning(f"Circuit {self.name} opened again after failure in half_open")
            return

        if self._state == CircuitState.CLOSED:
            # Track failure
            self._failures.append(now)
            self._failure_count += 1
            self._last_failure_time = now

            # Clean oude failures buiten window
            self._clean_old_failures(now)

            # Check threshold
            if len(self._failures) >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"Circuit {self.name} opened after {len(self._failures)} failures")

    def _clean_old_failures(self, now: datetime) -> None:
        """Verwijder failures buiten het tijdwindow."""
        cutoff = now - timedelta(seconds=self.config.failure_window_seconds)
        self._failures = [f for f in self._failures if f > cutoff]

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition naar nieuwe state."""
        old_state = self._state
        self._state = new_state
        self._state_changed_at = datetime.now(timezone.utc)

        # Reset counts bij state change
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._failures = []
            if self.config.on_close:
                self.config.on_close(self.name)

        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            if self.config.on_open:
                self.config.on_open(self.name)

        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            if self.config.on_half_open:
                self.config.on_half_open(self.name)

        logger.debug(f"Circuit {self.name}: {old_state} -> {new_state}")

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": len(self._failures),
            "success_count": self._success_count,
            "last_failure": (
                self._last_failure_time.isoformat() if self._last_failure_time else None
            ),
            "state_changed_at": self._state_changed_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"CircuitBreaker({self.name}, state={self._state.value})"


class CircuitBreakerRegistry:
    """Registry voor meerdere circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get bestaande of create nieuwe circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get circuit breaker by name."""
        return self._breakers.get(name)

    def remove(self, name: str) -> None:
        """Remove circuit breaker."""
        if name in self._breakers:
            del self._breakers[name]

    def get_all_stats(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get stats van alle circuit breakers."""
        return {name: cb.get_stats() for name, cb in self._breakers.items()}
