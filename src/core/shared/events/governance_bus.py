"""Governance event bus -- asyncio pub/sub singleton (ADR-034 s5.5).

emit() returns the number of handlers that ran successfully.
Handlers are registered per event type; failures are caught and logged.
reset_for_testing() clears all registrations for test isolation.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_HandlerFn = Callable[[Any], Awaitable[None]]  # TODO(TYPE): replace Any with concrete type


class GovernanceEventBus:
    """Simple asyncio pub/sub bus for governance domain events."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[_HandlerFn]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: _HandlerFn) -> None:
        self._handlers[event_type].append(handler)

    async def emit(self, event: Any) -> int:  # TODO(TYPE): replace Any with concrete type
        """Dispatch event to all registered handlers.

        Each handler runs independently; a failing handler is logged and skipped.
        Returns the number of handlers that completed without error.
        """
        handlers = self._handlers.get(type(event), [])
        count = 0
        for handler in handlers:
            try:
                await handler(event)
                count += 1
            except Exception as exc:
                logger.warning(
                    "governance_bus handler %s failed for %s: %s: %s",
                    handler.__name__,
                    type(event).__name__,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
        return count

    def reset_for_testing(self) -> None:
        """Clear all handler registrations -- call in test teardown only."""
        self._handlers.clear()


governance_bus: GovernanceEventBus = GovernanceEventBus()
