"""Governance event bus handlers -- subscribe to shared events and write to DB.

All handlers create their own DB session so that event dataclasses
never carry AsyncSession references (ADR-034 / SP-DSM-006).
"""

from __future__ import annotations

import logging

from src.core.governance.audit import audit_service
from src.core.shared.events.governance_bus import governance_bus
from src.core.shared.events.governance_events import (
    AuditLogEmitEvent,
    ConsentAuditEvent,
    SecurityAuditEvent,
)
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


async def _handle_audit_log_emit(event: AuditLogEmitEvent) -> None:
    from src.core.database.database import db_manager

    if not db_manager.is_initialized() or db_manager.async_session_maker is None:
        logger.debug("Skipping AuditLogEmitEvent: db_manager not initialized")
        return
    async with db_manager.async_session_maker() as session:
        async with best_effort("AuditLogEmitEvent"):
            await audit_service.log_action(
                tenant_id=event.tenant_id,
                action=event.event_type,
                resource=event.endpoint,
                details={**event.event_metadata, "client_ip": event.client_ip},
                session=session,
                threat_level=event.threat_level,
                client_ip=event.client_ip,
                endpoint=event.endpoint,
                description=event.description,
            )
            await session.commit()


async def _handle_security_audit(event: SecurityAuditEvent) -> None:
    from src.core.database.database import db_manager

    if not db_manager.is_initialized() or db_manager.async_session_maker is None:
        logger.debug("Skipping SecurityAuditEvent: db_manager not initialized")
        return
    async with db_manager.async_session_maker() as session:
        async with best_effort("SecurityAuditEvent"):
            await audit_service.log_action(
                tenant_id=event.tenant_id,
                action=event.event_type,
                resource=event.entity_id,
                user_id=event.user_id,
                details={**event.details, "action": event.action},
                session=session,
                threat_level="MEDIUM",
                endpoint="SECURITY",
                description=f"{event.action}: {event.event_type} on {event.entity_id}",
            )
            await session.commit()


async def _handle_consent_audit(event: ConsentAuditEvent) -> None:
    from src.core.database.database import db_manager

    if not db_manager.is_initialized() or db_manager.async_session_maker is None:
        logger.debug("Skipping ConsentAuditEvent: db_manager not initialized")
        return
    async with db_manager.async_session_maker() as session:
        async with best_effort("ConsentAuditEvent"):
            await audit_service.log_action(
                tenant_id=event.tenant_id,
                action=event.action,
                resource=event.consent_type,
                details={**event.details, **({"user_id": event.user_id} if event.user_id else {})},
                session=session,
                endpoint="CONSENT",
                description=f"{event.action} on {event.consent_type}",
            )
            await session.commit()


def register_governance_event_handlers() -> None:
    """Subscribe all governance handlers to the shared event bus.

    Call once after db_manager is initialized, before accepting requests.
    """
    governance_bus.subscribe(AuditLogEmitEvent, _handle_audit_log_emit)
    governance_bus.subscribe(SecurityAuditEvent, _handle_security_audit)
    governance_bus.subscribe(ConsentAuditEvent, _handle_consent_audit)
    logger.info("Governance event handlers registered (3 subscriptions)")
