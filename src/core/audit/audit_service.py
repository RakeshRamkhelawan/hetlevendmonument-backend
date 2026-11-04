"""
Audit Service for Security Event Logging

Logs security-related events (login, logout, token revocation, privilege changes, etc.)
to a centralized audit trail for compliance and forensics.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from src.core.middleware.tenant_context import get_tenant_id
from src.core.observability.metrics import _get_or_create_counter
from src.core.tasks.audit_tasks import write_audit_log_task

logger = logging.getLogger(__name__)

#: Hoeveel keer de hash-gekoppelde auditregel NIET in de Dramatiq-wachtrij kon worden gezet
#: (ADR-036 OP-06). Zonder dit was dit pad "fail-open" in de zin dat een aanroeper geen enkel
#: signaal kreeg dat de ADR-019-keten een rij mist -- alleen een ERROR-logregel die niemand
#: per se bewaakt. `log_security_event()` blijft zelf `True` teruggeven (de structured-log-
#: schrijf op regel 71 is wel gelukt, en geen enkele aanroeper leest de returnwaarde -- gemeten
#: met `git grep -n "= await log_security_event\|= log_security_event"`, nul treffers), maar de
#: uitzondering wordt nu ook OBSERVEERBAAR in plaats van alleen geLOGD.
AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL = _get_or_create_counter(
    "audit_hash_chain_enqueue_failures_total",
    "Aantal keer dat het hash-gekoppelde audit-schrijfverzoek niet in de wachtrij kon worden "
    "gezet (ADR-036 OP-06)",
    ["event_type"],
)


class AuditService:
    """Service for logging security-related audit events.

    Events are logged with full context for later analysis and compliance.

    GOV-002 (ADR-031/ADR-019/ADR-006): this class runs in Redis-only hot paths
    (token revocation, rate limiting, session dashboards) with no DB session in
    scope. In addition to the structured logger write below, a hash-chained
    AuditLog record is enqueued via Dramatiq (fire-and-forget, ADR-006) whenever
    a tenant_id is resolvable from the request-scoped ContextVar (ADR-003). When
    no tenant_id is resolvable (e.g. a background job with no request context),
    the write stays logger-only -- consistent with
    governance/audit.py::AuditService.log_action()'s own tenant-required
    contract (ADR-005).
    """

    def __init__(self) -> None:
        """Initialize audit service."""
        self.audit_logger = logging.getLogger("audit")

    async def log_security_event(
        self,
        event_type: str,
        user_id: int | None = None,
        target_user_id: int | None = None,
        timestamp: datetime | None = None,
        **details: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Log a security event to audit trail.

        Args:
            event_type: Type of event (token_revoked, bulk_token_revocation, login, etc.)
            user_id: User performing the action
            target_user_id: User affected by the action
            timestamp: When the event occurred
            **details: Additional event-specific details

        Returns:
            True if successfully logged, False otherwise
        """
        try:
            timestamp = timestamp or datetime.now(timezone.utc)

            # Build audit event record
            event = {
                "event_type": event_type,
                "user_id": user_id,
                "target_user_id": target_user_id,
                "timestamp": timestamp.isoformat(),
                **details,
            }

            # Log event (immediate, structured -- fail-open safety net)
            self.audit_logger.info("SECURITY EVENT", extra=event)

            tenant_id = get_tenant_id()
            if tenant_id is not None:
                try:
                    write_audit_log_task.send(
                        tenant_id=int(tenant_id),
                        action=event_type,
                        resource=f"user:{target_user_id or user_id or 'unknown'}",
                        user_id=user_id,
                        details={k: v for k, v in details.items() if k != "timestamp"},
                        description=f"{event_type} (target_user_id={target_user_id})"
                        if target_user_id
                        else event_type,
                    )
                except Exception as enqueue_exc:
                    AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL.labels(event_type=event_type).inc()
                    logger.error(
                        "Failed to enqueue hash-chained audit write: %s: %s",
                        type(enqueue_exc).__name__,
                        enqueue_exc,
                        exc_info=True,
                    )

            logger.debug("Audit event logged: %s by user %s", event_type, user_id)
            return True

        except Exception as e:
            logger.error("Failed to log security event: %s: %s", type(e).__name__, e, exc_info=True)
            return False
