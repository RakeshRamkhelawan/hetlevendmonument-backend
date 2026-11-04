"""Learning audit helper -- emits AuditLogEmitEvent via governance_bus.

This is the shared-layer replacement for governance/learning_audit.py.
It emits events instead of writing directly to AuditLog so that shared
code does not depend on governance models.

Signature is backward-compatible: callers that pass `session` will
have it silently ignored (the handler creates its own session).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_learning_audit_event(
    *,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None,
    user_id: int | None = None,
    session: AsyncSession | None = None,  # ignored -- handler creates own session
) -> None:
    """Emit a learning audit event via the governance event bus."""
    if tenant_id is None:
        return
    try:
        from src.core.shared.events.governance_bus import governance_bus
        from src.core.shared.events.governance_events import AuditLogEmitEvent

        event = AuditLogEmitEvent(
            tenant_id=tenant_id,
            event_type=action,
            threat_level="LOW",
            client_ip="internal",
            endpoint="LEARNING",
            description=f"{action} on {resource}",
            event_metadata=details or {},
        )
        await governance_bus.emit(event)
    except Exception as exc:
        logger.warning(
            "learning audit emit failed for action=%s: %s: %s",
            action,
            type(exc).__name__,
            exc,
        )
