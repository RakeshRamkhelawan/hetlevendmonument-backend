# Bestand: core/governance/services/audit_service.py
# Verplaatst van src/core/services/audit_service.py (SP-DSM-006, Group F)

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.ketencontext import ketencontext
from src.core.governance.models import AuditLog
from src.core.middleware.tenant_context import get_tenant_id
from src.core.shared.security_events import SecurityEvent as SecurityEvent
from src.core.governance.audit_chain_key import mark_entry

if TYPE_CHECKING:
    from src.core.security.security_manager import ThreatLevel

logger = logging.getLogger(__name__)


class AuditService:
    """
    Service for handling audit log operations with production-grade error handling.

    This service provides centralized audit logging to the database with:
    - Defensive error handling for database failures
    - JSON metadata validation
    - M-MDP compliant async I/O patterns
    - Graceful degradation (logs to system logger if database fails)

    Example:
        async with db_manager.get_session() as db:
            await AuditService.log_event(
                db=db,
                event_type="LOGIN_SUCCESS",
                severity=ThreatLevel.LOW,
                source_ip="192.168.1.1",
                endpoint="/api/v1/auth/login",
                description="User logged in successfully",
                user_id=123
            )
    """

    @staticmethod
    async def log_event(
        db: AsyncSession,
        event_type: str,
        severity: "ThreatLevel | str",
        source_ip: str,
        endpoint: str,
        description: str,
        user_id: int | None = None,
        tenant_id: int | None = None,
        action: str | None = None,
        resource: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        details: dict[str, object] | None = None,
    ) -> bool:
        """Log a security/system event. flush() semantics: entry is durable only when caller commits (ADR-019)."""
        if metadata:
            try:
                json.dumps(metadata)
            except (TypeError, ValueError) as e:
                logger.warning("Metadata not JSON-serializable, discarding: %s", e)
                metadata = {}
        try:
            async with db.begin_nested():
                entry = AuditLog(
                    event_type=str(getattr(event_type, "value", event_type)),
                    threat_level=str(getattr(severity, "value", severity)).lower(),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action=(str(getattr(action, "value", action)) if action else None),
                    resource=resource,
                    client_ip=source_ip,
                    endpoint=endpoint,
                    description=description,
                    event_metadata=metadata or {},
                    details=details or {},
                )
                # GOV-003 (ADR-019): populate the hash chain via the same
                # HashChainVerifier + per-tenant advisory lock as the canonical
                # governance/audit.py::AuditService.log_action() path. Best-effort:
                # degraded mode (entry written without a hash) if the chain lookup
                # fails, so a hash-chain outage never blocks audit persistence.
                if tenant_id is not None:
                    try:
                        from src.core.governance.hash_chain import (  # noqa: PLC0415
                            HashChainVerifier,
                        )

                        await db.execute(
                            text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(tenant_id)}
                        )
                        # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste
                        # rij ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde
                        # volgorde. Werd de tijdstempel VOOR het slot gekozen, dan kon regel A (eerder
                        # gekozen) na regel B worden geketend: op tijd VOOR B, in de keten ACHTER B, en
                        # meldde verify_chain manipulatie op een gave keten. Binnen het slot is elke
                        # volgende tijdstempel later dan die van de vorige schrijver (dezelfde klok), dus
                        # tijd en keten lopen gelijk. De tijdstempel zit in de hash en wordt hier VOOR het
                        # hashen gezet; wat er gehasht wordt is niet veranderd.
                        entry.timestamp = datetime.now(timezone.utc)
                        async with ketencontext(db, int(tenant_id)):
                            prev_result = await db.execute(
                                select(AuditLog.audit_hash)
                                .where(
                                    AuditLog.tenant_id == int(tenant_id),
                                    AuditLog.audit_hash.isnot(None),
                                )
                                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                                .limit(1)
                            )
                            previous_hash = prev_result.scalar_one_or_none()
                        verifier = HashChainVerifier(db_session=db)
                        entry.previous_hash = previous_hash
                        # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                        # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                        # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                        mark_entry(entry)
                        entry.audit_hash = verifier._compute_hash(entry, previous_hash)
                    except Exception as hash_exc:
                        logger.error(
                            "audit: hash chain populatie mislukt tenant %s: %s: %s",
                            tenant_id,
                            type(hash_exc).__name__,
                            hash_exc,
                            exc_info=True,
                        )
                # Een regel ZONDER keten (geen tenant, of de ketenlookup faalde voor het slot) heeft
                # hier nog geen tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
                if entry.timestamp is None:
                    entry.timestamp = datetime.now(timezone.utc)
                db.add(entry)
            await db.flush()
            logger.debug("Successfully logged audit event: %s", event_type)
            return True
        except RuntimeError as e:
            logger.warning("Audit logging unavailable (DB not initialized): %s", e)
            return False
        except SQLAlchemyError as e:
            logger.error(
                "Database error during audit logging: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error in audit logging: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False


async def log_security_event(
    event_type: str,
    user_id: int | None = None,
    tenant_id: int | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    threat_level: str = "medium",
    description: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Log security event to database and system logs (multi-tenant aware)."""
    if tenant_id is None:
        tenant_id = get_tenant_id()

    event_severity_map = {
        SecurityEvent.CROSS_TENANT_ATTEMPT: "critical",
        SecurityEvent.QUOTA_EXCEEDED: "high",
        SecurityEvent.SUPERUSER_BYPASS: "low",
        SecurityEvent.INVALID_JWT: "high",
        SecurityEvent.TOKEN_EXPIRED: "medium",
        SecurityEvent.TENANT_CONTEXT_FAILED: "high",
        SecurityEvent.TENANT_NOT_FOUND: "high",
    }
    derived_level = event_severity_map.get(event_type, threat_level)

    details_keys = list(details) if details else []
    log_message = (
        f"SECURITY EVENT [{derived_level.upper()}]: {event_type} | "
        f"user_id={user_id} | tenant_id={tenant_id} | "
        f"path={request_path} | method={request_method} | "
        f"ip={ip_address} | details_keys={details_keys}"
    )
    if derived_level == "critical":
        logger.error(log_message)
    elif derived_level in ["high", "medium"]:
        logger.warning(log_message)
    else:
        logger.info(log_message)

    if db is None:
        logger.debug("No database session provided, skipping database audit log")
        return

    try:
        severity = derived_level
        await AuditService.log_event(
            db=db,
            event_type=event_type,
            severity=severity,
            source_ip=ip_address or "unknown",
            endpoint=request_path or "unknown",
            description=description
            or (f"{event_type}: keys={list(details)}" if details else event_type),
            user_id=user_id,
            tenant_id=tenant_id,
            action=event_type,
            resource=request_path,
            metadata={"request_method": request_method, **(details or {})},
        )
    except Exception as e:
        logger.error(
            "Failed to write audit log to database: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )


async def log_request_audit(
    request: Any = None,
    response_status: int | None = None,
    user_id: str | None = None,
    tenant_id: int | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    status_code: int | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Log API request for audit trail."""
    if request is not None and response_status is not None:
        path = str(request.url.path)
        method = request.method
        code = response_status
        ip = request.client.host if request.client else None
        ua = request.headers.get("User-Agent") if hasattr(request, "headers") else None
        details = {
            "query_params": dict(request.query_params),
            "status_code": code,
            **({"user_agent": ua} if ua else {}),
        }
    else:
        path = request_path or "unknown"
        method = request_method or "UNKNOWN"
        code = status_code if status_code is not None else 0
        ip = client_ip
        ua = user_agent
        details = {"status_code": code, **({"user_agent": ua} if ua else {})}

    if code >= 500:
        level = "critical"
    elif code in [401, 403, 404]:
        level = "high" if code in [401, 403] else "critical" if code == 404 else "medium"
    elif code == 200:
        level = "low"
    else:
        level = "medium"

    await log_security_event(
        event_type=f"api_request_{code}",
        user_id=int(user_id) if user_id is not None and str(user_id).isdigit() else None,
        tenant_id=tenant_id,
        request_path=path,
        request_method=method,
        ip_address=ip,
        details=details,
        threat_level=level,
    )
