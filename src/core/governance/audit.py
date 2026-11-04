"""
Audit Service
Handles the creation of immutable audit logs.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import ColumnElement, and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.ketencontext import ketencontext
from src.core.governance.models import AuditLog
from src.core.governance.audit_chain_key import mark_entry

logger = logging.getLogger(__name__)

#: Auditacties waarbij `user_id` de ACTOR is en `resource` de DOELGEBRUIKER (ADR-039: wie gaf of nam
#: een rol). Zie `audit_rows_about_user`.
ROLE_AUDIT_ACTIONS: tuple[str, ...] = ("role_assigned", "role_revoked")


def audit_rows_about_user(user_id: int | str) -> ColumnElement[bool]:
    """Filter voor AVG-inzage en -export: auditregels van OF over deze persoon.

    `user_id` van een auditregel is de actor. Bij een rolwijziging is de persoon die de rol kreeg of
    verloor het DOEL, en staat in `resource` (het gewone gebruikersnummer; zo schrijft
    `event_handlers._handle_security_audit` het weg). Wie alleen op `user_id` filtert, laat die
    persoon zijn eigen rolwijzigingen niet zien (AVG art. 15). Alleen de rolacties tellen mee voor
    `resource`: een ander soort regel met toevallig hetzelfde nummer is niet over deze persoon.
    De tenantgrens blijft bij de aanroeper (`AuditLog.tenant_id == tenant_id`).
    """
    return or_(
        AuditLog.user_id == user_id,
        and_(AuditLog.action.in_(ROLE_AUDIT_ACTIONS), AuditLog.resource == str(user_id)),
    )


class AuditService:
    """
    Service for writing audit logs.
    Ensures logs are written asynchronously and securely.
    """

    @staticmethod
    async def log_action(
        tenant_id: int | None,
        action: str,
        resource: str,
        user_id: int | None = None,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        session: AsyncSession | None = None,
        # Legacy/Security fields
        threat_level: str = "INFO",
        client_ip: str = "SYSTEM",
        endpoint: str = "INTERNAL",
        description: str | None = None,
        event_type: str | None = None,
    ) -> AuditLog | None:
        """
        Log an action to the audit trail.

        Args:
            tenant_id: The tenant context (integer)
            action: The action performed (e.g., "CREATE", "DELETE")
            resource: The resource affected (e.g., "user:123", "agent:456")
            user_id: The user who performed the action (optional for system actions)
            details: Additional context (JSON serializable)
            session: Optional existing session (if part of a transaction)
            threat_level: Security threat level (default: INFO)
            client_ip: Client IP address (default: SYSTEM)
            endpoint: API endpoint or internal source (default: INTERNAL)
            description: Human readable description (default: "{action} on {resource}")
            event_type: Optional category distinct from `action` for filtering/reporting
                (e.g. action="gdpr_delete_all", event_type="gdpr_delete_failed" on the
                failure path). Defaults to `action` when not provided.

        Returns:
            AuditLog entry if session provided, None otherwise

        Note: This method does not self-guard. Callers must wrap in best_effort (Pattern 3).
        """
        tenant_id_int = int(tenant_id) if tenant_id is not None else None

        if tenant_id_int is None:
            logger.warning(
                "Audit log skipped: tenant_id is None for action=%s resource=%s",
                action,
                resource,
            )
            return None

        log_entry = AuditLog(
            tenant_id=tenant_id_int,
            action=action,
            resource=resource,
            details=details or {},
            event_type=event_type or action,
            threat_level=threat_level,
            client_ip=client_ip,
            endpoint=endpoint,
            description=description or f"{action} on {resource}",
            event_metadata=details or {},
            user_id=user_id,
        )

        # De tijdstempel wordt EXPLICIET gezet (niet via server_default), zodat de hash
        # reproduceerbaar is bij herverificatie. Dat gebeurt hieronder NA het slot.
        if session and tenant_id_int is not None:
            try:
                # Advisory lock serializes chain writes per tenant -- prevents forked chain.
                # begin_nested() requires an active transaction (standard for FastAPI Depends(get_db)).
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant_id_int}
                )
                # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste rij
                # ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde volgorde. Een
                # tijdstempel die VOOR het slot wordt gekozen, kan na die van een latere schrijver worden
                # geketend: op tijd VOOR hem, in de keten ACHTER hem, en dan meldt verify_chain manipulatie
                # op een gave keten. Binnen het slot is elke tijdstempel later dan die van de vorige
                # schrijver. De tijdstempel zit in de hash en staat er hier VOOR het hashen; wat er
                # gehasht wordt is niet veranderd. Zelfde vorm als AuditService.log_event.
                log_entry.timestamp = datetime.now(timezone.utc)
                async with session.begin_nested():
                    from src.core.governance.hash_chain import HashChainVerifier  # noqa: PLC0415

                    async with ketencontext(session, tenant_id_int):
                        prev_result = await session.execute(
                            select(AuditLog.audit_hash)
                            .where(
                                AuditLog.tenant_id == tenant_id_int,
                                AuditLog.audit_hash.isnot(None),
                            )
                            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                            .limit(1)
                        )
                        _previous_hash: str | None = prev_result.scalar_one_or_none()
                    _verifier = HashChainVerifier(db_session=session)
                    log_entry.previous_hash = _previous_hash
                    # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                    # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                    # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                    mark_entry(log_entry)
                    log_entry.audit_hash = _verifier._compute_hash(log_entry, _previous_hash)
            except Exception as _e:
                logger.error(
                    "audit: hash chain populatie mislukt tenant %s: %s: %s",
                    tenant_id_int,
                    type(_e).__name__,
                    _e,
                    exc_info=True,
                )
                # log_entry wordt alsnog weggeschreven zonder hash (degraded mode)

        # Een regel ZONDER keten (de ketenlookup faalde al voor het slot) heeft hier nog geen
        # tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
        if session and log_entry.timestamp is None:
            log_entry.timestamp = datetime.now(timezone.utc)
        if session:
            session.add(log_entry)
            return log_entry
        else:
            # Without a session, we can't reliably create audit logs due to
            # foreign key constraints and transaction isolation.
            # Callers should always pass a session.
            logger.warning(
                "Audit log skipped: no session provided for action=%s resource=%s",
                action,
                resource,
            )
            return None


# Global instance not needed as methods are static, but can be useful for DI
audit_service = AuditService()
