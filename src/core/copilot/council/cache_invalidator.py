"""
Event-driven cache invalidation for Officer verdicts.

Subscribes to three event types that may change verdict outcomes:
- rbac.role_changed       -> flush tenant cache
- toolbroker.allowlist_updated -> flush tenant cache
- tenant.policy_updated   -> flush tenant cache

Rate-limit per tenant prevents DoS via event spam (H-8):
max 1 flush per tenant per 10s.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.core.copilot.council.cache import OfficerVerdictCache

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Event-driven cache invalidation for Officer verdicts.

    Contains rate-limit per tenant to prevent DoS via event spam
    (H-8): max 1 flush per tenant per 10s.
    """

    _RATE_LIMIT_S = 10

    def __init__(self, cache: OfficerVerdictCache) -> None:
        self._cache = cache
        # In-memory rate-limit map; sufficient because invalidation is idempotent.
        self._last_flush: dict[int, float] = {}

    def _allow_flush(self, tenant_id: int) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        last = self._last_flush.get(tenant_id, 0)
        if now - last < self._RATE_LIMIT_S:
            logger.warning(
                "cache flush rate-limited tenant=%d (last_flush=%.1fs ago)",
                tenant_id,
                now - last,
            )
            return False
        self._last_flush[tenant_id] = now
        return True

    async def on_role_changed(self, event: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        tenant_id = event.get("tenant_id")
        if not isinstance(tenant_id, int):
            logger.warning("on_role_changed: invalid tenant_id %r", tenant_id)
            return
        if not self._allow_flush(tenant_id):
            return
        deleted = await self._cache.invalidate_tenant(tenant_id)
        logger.info(
            "cache invalidated due to rbac.role_changed tenant=%d deleted=%d",
            tenant_id,
            deleted,
        )

    async def on_allowlist_updated(self, event: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        tenant_id = event.get("tenant_id")
        if not isinstance(tenant_id, int):
            logger.warning("on_allowlist_updated: invalid tenant_id %r", tenant_id)
            return
        if not self._allow_flush(tenant_id):
            return
        deleted = await self._cache.invalidate_tenant(tenant_id)
        logger.info(
            "cache invalidated due to toolbroker.allowlist_updated tenant=%d deleted=%d",
            tenant_id,
            deleted,
        )

    async def on_policy_updated(self, event: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        tenant_id = event.get("tenant_id")
        if not isinstance(tenant_id, int):
            logger.warning("on_policy_updated: invalid tenant_id %r", tenant_id)
            return
        if not self._allow_flush(tenant_id):
            return
        deleted = await self._cache.invalidate_tenant(tenant_id)
        logger.info(
            "cache invalidated due to tenant.policy_updated tenant=%d deleted=%d",
            tenant_id,
            deleted,
        )


class SimpleEventBus:
    """Lightweight in-memory pub/sub for cache invalidation events.

    Not persistent; handlers run in-process only.
    Errors are logged but do not stop other handlers.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def subscribe(self, event_type: str, handler: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(
            "simple_event_bus_subscribe event_type=%s handler=%s",
            event_type,
            handler.__name__,
        )

    def unsubscribe(self, event_type: str, handler: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            logger.debug("simple_event_bus_no_handlers event_type=%s", event_type)
            return
        for handler in handlers:
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "simple_event_bus_handler_error event_type=%s handler=%s error=%s",
                    event_type,
                    getattr(handler, "__name__", str(handler)),
                    exc,
                    exc_info=True,
                )

    def clear(self) -> None:
        self._subscribers.clear()


# Singleton instance for application-wide cache invalidation events
_event_bus_instance: SimpleEventBus | None = None


def get_cache_invalidation_event_bus() -> SimpleEventBus:
    """Return the singleton SimpleEventBus instance for cache invalidation."""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = SimpleEventBus()
    return _event_bus_instance


def reset_cache_invalidation_event_bus() -> None:
    """Reset the singleton instance (useful for tests)."""
    global _event_bus_instance
    if _event_bus_instance is not None:
        _event_bus_instance.clear()
        _event_bus_instance = None
