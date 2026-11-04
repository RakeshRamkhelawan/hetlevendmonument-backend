#!/usr/bin/env python3
"""
Security Audit Service - OWASP A09: Security Logging and Monitoring Failures

Comprehensive security audit logging with:
- Persistent database storage with hash chain integrity
- Suspicious activity detection (brute force, privilege escalation, etc.)
- Configurable alerting thresholds
- Log tampering detection

This service addresses OWASP Top 10 2021 - A09 by implementing:
1. Comprehensive logging of security-relevant events
2. Integrity protection via cryptographic hash chain
3. Anomaly detection for suspicious patterns
4. Automated alerting for critical events
"""

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from collections.abc import Callable

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.ketencontext import ketencontext
from src.core.governance.models import AuditLog
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import SecurityAlert
from src.core.security.types import AlertStatus, SecurityEventType, ThreatLevel
from src.core.utils.best_effort import best_effort
from src.core.governance.audit_chain_key import mark_entry

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _extract_count_row(row: Any) -> tuple[str, int]:  # TODO(TYPE): replace Any with concrete type
    """
    Extract key and count from database row tuple.

    Handles missing or None values gracefully for aggregate query results.

    Args:
        row: Tuple from database query result (key, count)

    Returns:
        Tuple of (key as string, count as int)
    """
    row_data: tuple[Any, ...] = tuple(row)  # TODO(TYPE): replace Any with concrete type
    key = str(row_data[0]) if len(row_data) > 0 and row_data[0] is not None else ""
    val = int(row_data[1]) if len(row_data) > 1 else 0
    return key, val


# ============================================================================
# DETECTION RULES CONFIGURATION
# ============================================================================


@dataclass
class DetectionRule:
    """Configuration for suspicious activity detection"""

    name: str
    event_types: list[SecurityEventType]
    threshold: int  # Number of events to trigger
    window_seconds: int  # Time window for counting
    severity: ThreatLevel
    description: str
    auto_block: bool = False  # Whether to auto-block IP


# Default detection rules (can be overridden per-tenant)
DEFAULT_DETECTION_RULES: list[DetectionRule] = [
    DetectionRule(
        name="brute_force_login",
        event_types=[SecurityEventType.LOGIN_FAILED],
        threshold=5,
        window_seconds=300,  # 5 minutes
        severity=ThreatLevel.HIGH,
        description="Multiple failed login attempts detected",
        auto_block=True,
    ),
    DetectionRule(
        name="rapid_password_reset",
        event_types=[SecurityEventType.PASSWORD_RESET_REQUESTED],
        threshold=3,
        window_seconds=600,  # 10 minutes
        severity=ThreatLevel.MEDIUM,
        description="Multiple password reset requests detected",
    ),
    DetectionRule(
        name="privilege_escalation_attempts",
        event_types=[
            SecurityEventType.PRIVILEGE_ESCALATION,
            SecurityEventType.ACCESS_DENIED,
        ],
        threshold=3,
        window_seconds=300,
        severity=ThreatLevel.CRITICAL,
        description="Potential privilege escalation attempt detected",
    ),
    DetectionRule(
        name="injection_attempts",
        event_types=[
            SecurityEventType.SQL_INJECTION_ATTEMPT,
            SecurityEventType.XSS_ATTEMPT,
            SecurityEventType.PATH_TRAVERSAL_ATTEMPT,
        ],
        threshold=1,  # Single attempt is concerning
        window_seconds=60,
        severity=ThreatLevel.CRITICAL,
        description="Injection attack attempt detected",
        auto_block=True,
    ),
    DetectionRule(
        name="rate_limit_abuse",
        event_types=[SecurityEventType.RATE_LIMIT_EXCEEDED],
        threshold=10,
        window_seconds=300,
        severity=ThreatLevel.MEDIUM,
        description="Excessive rate limit violations",
    ),
    DetectionRule(
        name="cross_tenant_access",
        event_types=[SecurityEventType.CROSS_TENANT_ACCESS],
        threshold=1,
        window_seconds=60,
        severity=ThreatLevel.CRITICAL,
        description="Cross-tenant access attempt detected",
    ),
    DetectionRule(
        name="bulk_data_export",
        event_types=[SecurityEventType.DATA_EXPORTED, SecurityEventType.BULK_OPERATION],
        threshold=5,
        window_seconds=600,
        severity=ThreatLevel.HIGH,
        description="Unusual bulk data operations detected",
    ),
]


# ============================================================================
# SECURITY AUDIT SERVICE
# ============================================================================


class SecurityAuditService:
    """
    Comprehensive security audit logging service.

    Provides:
    - Persistent audit logging with integrity protection
    - Real-time suspicious activity detection
    - Configurable alerting with thresholds
    - Hash chain for log tampering detection
    """

    def __init__(
        self,
        detection_rules: list[DetectionRule] | None = None,
        alert_callbacks: list[Callable[..., Any]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Initialize security audit service.

        Args:
            detection_rules: Custom detection rules (uses defaults if None)
            alert_callbacks: Functions to call when alerts are generated
        """
        self.detection_rules = detection_rules or DEFAULT_DETECTION_RULES
        self.alert_callbacks = alert_callbacks or []

        # In-memory cache for real-time detection (complement to DB queries)
        self._event_cache: dict[str, list[datetime]] = defaultdict(list)
        self._cache_max_age = timedelta(minutes=15)
        self._last_hash: str | None = None

        logger.info(
            "Security Audit Service initialized with %d detection rules",
            len(self.detection_rules),
        )

    # ========================================================================
    # CORE AUDIT LOGGING
    # ========================================================================

    async def log_event(
        self,
        db: AsyncSession,
        event_type: SecurityEventType,
        severity: ThreatLevel,
        source_ip: str,
        endpoint: str,
        description: str,
        user_id: int | None = None,
        tenant_id: int | None = None,
        resource: str | None = None,
        action: str | None = None,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        success: bool = True,
        error_code: str | None = None,
        request_id: str | None = None,
        user_agent: str | None = None,
        response_status: int | None = None,
        response_time_ms: int | None = None,
    ) -> str | None:
        """
        Log a security event to the database with integrity protection.

        Args:
            db: AsyncSession for database operations
            event_type: Type of security event
            severity: Threat level
            source_ip: Client IP address
            endpoint: API endpoint accessed
            description: Human-readable description
            user_id: User ID (if authenticated)
            tenant_id: Tenant ID (auto-detected if not provided)
            resource: Resource being accessed
            action: HTTP method or operation
            details: Additional structured data
            success: Whether operation succeeded
            error_code: Error code if failed
            request_id: Correlation ID
            user_agent: Client user agent
            response_status: HTTP response status
            response_time_ms: Response time in milliseconds

        Returns:
            Event ID if successful, None if failed
        """
        try:
            # Auto-detect tenant if not provided
            if tenant_id is None:
                tenant_id = get_tenant_id()
            if tenant_id is None:
                logger.warning(
                    "Security audit log skipped: no tenant_id resolvable for event_type=%s",
                    event_type.value,
                )
                return None
            tenant_id_int = int(tenant_id)

            # Generate unique event ID
            event_id = str(uuid.uuid4())

            # Validate and serialize details
            if details:
                try:
                    json.dumps(details)
                except (TypeError, ValueError):
                    logger.warning("Details not JSON-serializable, converting")
                    details = {"raw": str(details)}

            # Create the log entry
            # Note: We use the existing AuditLog model from governance
            audit_entry = AuditLog(
                tenant_id=tenant_id_int,
                event_type=event_type.value,
                threat_level=severity.value,
                user_id=user_id,
                client_ip=source_ip,
                endpoint=endpoint,
                description=description,
                resource=resource,
                action=action,
                details=details,
                event_metadata={
                    "event_id": event_id,
                    "success": success,
                    "error_code": error_code,
                    "request_id": request_id,
                    "user_agent": user_agent,
                    "response_status": response_status,
                    "response_time_ms": response_time_ms,
                },
            )
            # De tijdstempel wordt hieronder gezet, NA het slot (zie daar).

            _committed = False
            async with best_effort("security audit log", db_session=db):
                # GOV-004 (ADR-019): populate the real hash-chain columns via the
                # canonical HashChainVerifier + per-tenant advisory lock, replacing
                # the old in-memory _last_hash/JSON-metadata scheme. Best-effort:
                # degraded mode (entry written without a hash) if the chain lookup
                # fails, so a hash-chain outage never blocks audit persistence.
                try:
                    await db.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant_id_int}
                    )
                    # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste rij
                    # ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde volgorde. Een
                    # tijdstempel die VOOR het slot wordt gekozen, kan na die van een latere schrijver worden
                    # geketend: op tijd VOOR hem, in de keten ACHTER hem, en dan meldt verify_chain manipulatie
                    # op een gave keten. Binnen het slot is elke tijdstempel later dan die van de vorige
                    # schrijver. De tijdstempel zit in de hash en staat er hier VOOR het hashen; wat er
                    # gehasht wordt is niet veranderd. Zelfde vorm als AuditService.log_event.
                    audit_entry.timestamp = datetime.now(timezone.utc)
                    async with ketencontext(db, tenant_id_int):
                        prev_result = await db.execute(
                            select(AuditLog.audit_hash)
                            .where(
                                AuditLog.tenant_id == tenant_id_int,
                                AuditLog.audit_hash.isnot(None),
                            )
                            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                            .limit(1)
                        )
                        previous_hash = prev_result.scalar_one_or_none()
                    verifier = HashChainVerifier(db_session=db)
                    audit_entry.previous_hash = previous_hash
                    # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                    # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                    # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                    mark_entry(audit_entry)
                    audit_entry.audit_hash = verifier._compute_hash(audit_entry, previous_hash)
                except Exception as hash_exc:
                    logger.error(
                        "security audit: hash chain populatie mislukt tenant %s: %s: %s",
                        tenant_id_int,
                        type(hash_exc).__name__,
                        hash_exc,
                        exc_info=True,
                    )

                # Een regel ZONDER keten (de ketenlookup faalde al voor het slot) heeft hier nog geen
                # tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
                if audit_entry.timestamp is None:
                    audit_entry.timestamp = datetime.now(timezone.utc)
                db.add(audit_entry)
                await db.commit()
                _committed = True

            if _committed:
                # Update in-memory cache for real-time detection
                cache_key = f"{source_ip}:{event_type.value}"
                self._event_cache[cache_key].append(datetime.now(timezone.utc))
                self._cleanup_cache()

                # Check for suspicious patterns using a committed event_id
                await self._check_detection_rules(
                    db, event_type, source_ip, user_id, tenant_id_int, event_id
                )

                logger.debug(
                    "Logged security event: %s (severity: %s)",
                    event_type.value,
                    severity.value,
                )

                return event_id
            return None

        except Exception as e:
            logger.error(
                "Unexpected error logging security event: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None

    def _compute_log_hash(
        self, event_id: str, event_type: str, description: str, source_ip: str
    ) -> str:
        """Compute SHA-256 hash for log integrity verification."""
        content = f"{event_id}:{event_type}:{description}:{source_ip}:{self._last_hash or ''}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _cleanup_cache(self) -> None:
        """Remove old entries from in-memory event cache."""
        cutoff = datetime.now(timezone.utc) - self._cache_max_age
        for key in list(self._event_cache.keys()):
            self._event_cache[key] = [ts for ts in self._event_cache[key] if ts > cutoff]
            if not self._event_cache[key]:
                del self._event_cache[key]

    # ========================================================================
    # SUSPICIOUS ACTIVITY DETECTION
    # ========================================================================

    async def _check_detection_rules(
        self,
        db: AsyncSession,
        event_type: SecurityEventType,
        source_ip: str,
        user_id: int | None,
        tenant_id: int | None,
        event_id: str,
    ) -> None:
        """Check all detection rules against current event."""
        for rule in self.detection_rules:
            if event_type in rule.event_types:
                # Check in-memory cache first (faster)
                cache_key = f"{source_ip}:{event_type.value}"
                recent_events = self._event_cache.get(cache_key, [])

                cutoff = datetime.now(timezone.utc) - timedelta(seconds=rule.window_seconds)
                matching_events = [ts for ts in recent_events if ts > cutoff]

                if len(matching_events) >= rule.threshold:
                    await self._create_alert(
                        db=db,
                        rule=rule,
                        source_ip=source_ip,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        triggering_event_id=event_id,
                        event_count=len(matching_events),
                    )

    async def _create_alert(
        self,
        db: AsyncSession,
        rule: DetectionRule,
        source_ip: str,
        user_id: int | None,
        tenant_id: int | None,
        triggering_event_id: str,
        event_count: int,
    ) -> None:
        """Create a security alert based on detection rule."""
        try:
            alert_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            alert = SecurityAlert(
                tenant_id=tenant_id or 0,  # System alerts use tenant 0
                alert_id=alert_id,
                alert_type=rule.event_types[0].value,  # Primary event type
                severity=rule.severity.value,
                title=f"Security Alert: {rule.name}",
                description=rule.description,
                details={
                    "rule_name": rule.name,
                    "threshold": rule.threshold,
                    "window_seconds": rule.window_seconds,
                    "auto_block": rule.auto_block,
                },
                detection_rule=rule.name,
                event_count=event_count,
                first_event_at=now - timedelta(seconds=rule.window_seconds),
                last_event_at=now,
                source_ip=source_ip,
                user_id=user_id,
                related_event_ids=[triggering_event_id],
                status=AlertStatus.NEW.value,
                auto_response_taken=rule.auto_block,
                auto_response_details={"blocked_ip": source_ip} if rule.auto_block else None,
            )

            _committed = False
            async with best_effort("security alert creation", db_session=db):
                db.add(alert)
                await db.commit()
                _committed = True

            if _committed:
                logger.warning(
                    "SECURITY ALERT [%s]: %s - IP: %s, User: %s, Events: %d",
                    rule.severity.value.upper(),
                    rule.description,
                    source_ip,
                    user_id,
                    event_count,
                )

                # Notify callbacks only for committed alerts
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(
                            "Alert callback failed: %s: %s", type(e).__name__, e, exc_info=True
                        )

        except Exception as e:
            logger.error(
                "Failed to create security alert: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )

    # ========================================================================
    # QUERY & REPORTING
    # ========================================================================

    async def get_recent_events(
        self,
        db: AsyncSession,
        tenant_id: int | None = None,
        event_types: list[SecurityEventType] | None = None,
        severity: ThreatLevel | None = None,
        hours: int = 24,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        Query recent audit events with filters.

        Args:
            db: AsyncSession for database operations
            tenant_id: Filter by tenant (uses context if not provided)
            event_types: Filter by event types
            severity: Minimum severity level
            hours: Time window in hours
            limit: Maximum results

        Returns: list[Any] of matching audit log entries  # TODO(TYPE): replace Any with concrete type
        """
        try:
            if tenant_id is None:
                tenant_id = get_tenant_id()
            if tenant_id is None:
                raise RuntimeError(
                    "Tenant context required for AuditLog queries. "
                    "Call get_recent_events with an explicit tenant_id or ensure TenantMiddleware has run."
                )

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

            # Build query
            query = select(AuditLog).where(AuditLog.timestamp > cutoff)

            # Always apply tenant filter (AuditLog is excluded from ORM auto-filter)
            query = query.where(AuditLog.tenant_id == tenant_id)

            if event_types:
                type_values = [et.value for et in event_types]
                query = query.where(AuditLog.event_type.in_(type_values))

            if severity:
                # Filter by severity level (threat_level field)
                severity_order = {
                    ThreatLevel.INFO.value: 1,
                    ThreatLevel.LOW.value: 2,
                    ThreatLevel.MEDIUM.value: 3,
                    ThreatLevel.HIGH.value: 4,
                    ThreatLevel.CRITICAL.value: 5,
                }
                min_level = severity_order.get(severity.value, 1)
                query = query.where(
                    AuditLog.threat_level.in_(
                        [k for k, v in severity_order.items() if v >= min_level]
                    )
                )

            query = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)

            result = await db.execute(query)
            logs: list[AuditLog] = list(result.scalars().all())
            return logs

        except SQLAlchemyError as e:
            logger.error("Failed to query audit events: %s", e)
            return []

    async def get_alerts(
        self,
        db: AsyncSession,
        tenant_id: int | None = None,
        status: AlertStatus | None = None,
        severity: ThreatLevel | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SecurityAlert]:
        """
        Query security alerts with filters.

        Args:
            db: AsyncSession
            tenant_id: Filter by tenant
            status: Filter by alert status
            severity: Minimum severity level
            limit: Maximum results

        Returns: list[Any] of matching alerts  # TODO(TYPE): replace Any with concrete type
        """
        try:
            if tenant_id is None:
                tenant_id = get_tenant_id()
            if tenant_id is None:
                raise RuntimeError(
                    "Tenant context required for SecurityAlert queries. "
                    "Call get_alerts with an explicit tenant_id or ensure TenantMiddleware has run."
                )

            query = select(SecurityAlert).where(SecurityAlert.tenant_id == tenant_id)

            if status:
                query = query.where(SecurityAlert.status == status.value)

            if severity:
                # Filter by minimum severity
                severity_order = {
                    ThreatLevel.INFO.value: 1,
                    ThreatLevel.LOW.value: 2,
                    ThreatLevel.MEDIUM.value: 3,
                    ThreatLevel.HIGH.value: 4,
                    ThreatLevel.CRITICAL.value: 5,
                }
                min_level = severity_order.get(severity.value, 1)
                query = query.where(
                    SecurityAlert.severity.in_(
                        [k for k, v in severity_order.items() if v >= min_level]
                    )
                )

            query = query.order_by(SecurityAlert.created_at.desc()).limit(limit).offset(offset)

            result = await db.execute(query)
            alerts: list[SecurityAlert] = list(result.scalars().all())
            return alerts

        except SQLAlchemyError as e:
            logger.error("Failed to query security alerts: %s", e)
            return []

    async def acknowledge_alert(
        self, db: AsyncSession, alert_id: str, user_id: int, notes: str | None = None
    ) -> bool:
        """Acknowledge a security alert."""
        try:
            query = select(SecurityAlert).where(SecurityAlert.alert_id == alert_id)
            result = await db.execute(query)
            alert = result.scalar_one_or_none()

            if not alert:
                return False

            alert.status = AlertStatus.ACKNOWLEDGED.value
            alert.acknowledged_by = user_id
            alert.acknowledged_at = datetime.now(timezone.utc)
            if notes:
                alert.resolution_notes = notes

            await db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error("Failed to acknowledge alert: %s", e)
            await db.rollback()
            return False

    async def resolve_alert(
        self,
        db: AsyncSession,
        alert_id: str,
        user_id: int,
        resolution_notes: str,
        false_positive: bool = False,
    ) -> bool:
        """Resolve a security alert."""
        try:
            query = select(SecurityAlert).where(SecurityAlert.alert_id == alert_id)
            result = await db.execute(query)
            alert = result.scalar_one_or_none()

            if not alert:
                return False

            alert.status = (
                AlertStatus.FALSE_POSITIVE.value if false_positive else AlertStatus.RESOLVED.value
            )
            alert.resolved_by = user_id
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolution_notes = resolution_notes

            await db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error("Failed to resolve alert: %s", e)
            await db.rollback()
            return False

    async def get_security_summary(
        self, db: AsyncSession, tenant_id: int | None = None, hours: int = 24
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate security summary report.

        Returns:
            Summary statistics and metrics
        """
        try:
            if tenant_id is None:
                tenant_id = get_tenant_id()
            if tenant_id is None:
                raise RuntimeError(
                    "Tenant context required for AuditLog queries. "
                    "Call get_security_summary with an explicit tenant_id or ensure TenantMiddleware has run."
                )

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

            # Count events by severity
            severity_query = select(AuditLog.threat_level, func.count(AuditLog.id)).where(
                AuditLog.timestamp > cutoff
            )
            # Always apply tenant filter (AuditLog is excluded from ORM auto-filter)
            severity_query = severity_query.where(AuditLog.tenant_id == tenant_id)
            severity_query = severity_query.group_by(AuditLog.threat_level)

            severity_result = await db.execute(severity_query)
            severity_counts: dict[str, int] = {}
            for row in severity_result.all():
                key, val = _extract_count_row(row)
                severity_counts[key] = val

            # Count events by type
            type_query = select(AuditLog.event_type, func.count(AuditLog.id)).where(
                AuditLog.timestamp > cutoff
            )
            # Always apply tenant filter (AuditLog is excluded from ORM auto-filter)
            type_query = type_query.where(AuditLog.tenant_id == tenant_id)
            type_query = type_query.group_by(AuditLog.event_type)

            type_result = await db.execute(type_query)
            type_counts: dict[str, int] = {}
            for row in type_result.all():
                key, val = _extract_count_row(row)
                type_counts[key] = val

            # Get open alerts count
            alert_query = select(func.count(SecurityAlert.id)).where(
                SecurityAlert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value])
            )
            # Always apply tenant filter
            alert_query = alert_query.where(SecurityAlert.tenant_id == tenant_id)

            alert_result = await db.execute(alert_query)
            open_alerts = alert_result.scalar() or 0

            # Determine overall security status
            critical_count = severity_counts.get(str(ThreatLevel.CRITICAL.value), 0)
            high_count = severity_counts.get(str(ThreatLevel.HIGH.value), 0)

            if critical_count > 5 or open_alerts > 10:
                status = "critical"
            elif critical_count > 0 or high_count > 10:
                status = "warning"
            else:
                status = "healthy"

            total_events: int = sum(int(v) for v in severity_counts.values())
            return {
                "period_hours": hours,
                "tenant_id": tenant_id,
                "total_events": total_events,
                "events_by_severity": severity_counts,
                "events_by_type": type_counts,
                "open_alerts": open_alerts,
                "security_status": status,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        except SQLAlchemyError as e:
            logger.error("Failed to generate security summary: %s", e)
            return {"error": str(e), "security_status": "unknown"}

    # ========================================================================
    # LOG INTEGRITY VERIFICATION
    # ========================================================================

    async def verify_log_integrity(
        self, db: AsyncSession, tenant_id: int | None = None, limit: int = 1000
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Verify integrity of audit log hash chain.

        Detects any tampering with log entries by validating the real
        audit_hash/previous_hash columns via the canonical HashChainVerifier
        (GOV-004) -- the same class used to populate them at write time. Entries
        written before GOV-004 (audit_hash is None) predate hash-chain columns
        entirely and are skipped rather than reported as tampered.

        Returns:
            Verification results including any detected tampering
        """
        try:
            if tenant_id is None:
                tenant_id = get_tenant_id()
            if tenant_id is None:
                raise RuntimeError(
                    "Tenant context required for AuditLog queries. "
                    "Call verify_log_integrity with an explicit tenant_id or ensure TenantMiddleware has run."
                )
            tenant_id_int = int(tenant_id)

            query = select(AuditLog)
            # Always apply tenant filter (AuditLog is excluded from ORM auto-filter)
            query = query.where(AuditLog.tenant_id == tenant_id_int)
            # `id` als tiebreak, net als de zes SCHRIJVERS (ADR-036 OP-110). Deze verifier was
            # als enige van de vier vergeten, terwijl de commitboodschap "alle vier" claimde --
            # betrapt door de blinde ronde van 2026-08-10. Gemeten zonder tiebreak: VIJF valse
            # manipulatiemeldingen op een ongeschonden keten van drie met gelijke tijdstempels.
            # HET VENSTER BEGINT BIJ DE NIEUWSTE RIJEN (ADR-036 OP-122).
            #
            # Hier stond `timestamp.asc()`, dus dit endpoint keek naar de OUDSTE `limit` rijen.
            # Een aanvaller wist zijn sporen in de RECENTE regels, en die werden dus nooit
            # bekeken -- terwijl de docstring "Detects log tampering attempts" belooft. Het
            # endpoint heeft geen `offset` en geen datumfilter, dus een beheerder kon het venster
            # ook niet zelf verplaatsen; een hogere `limit` maakte het alleen groter vanaf
            # hetzelfde oudste beginpunt.
            query = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit)

            result = await db.execute(query)
            # Terug naar chronologische volgorde: de traversal loopt van oud naar nieuw, want zo
            # is de keten geschreven.
            logs = list(reversed(list(result.scalars().all())))

            if not logs:
                # Zelfde vorm als het andere pad. Zonder deze twee sleutels verschilt het
                # contract per uitkomst en moet elke aanroeper `.get()` met een default gebruiken.
                return {
                    "verified": True,
                    "tampering_detected": False,
                    "unhashed_entries": 0,
                    "entries_checked": 0,
                    "message": "No logs to verify",
                }

            verifier = HashChainVerifier(db_session=db)
            tampered_entries: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Chain-linkage baseline. Legacy pre-GOV-004 rows (audit_hash IS NULL) leave
            # this None, so the row immediately after a legacy row starts a fresh
            # verifiable sub-chain rather than reporting a link mismatch -- this is the
            # expected one-time transition edge at the legacy/hash-chained boundary.
            previous_hash: str | None = None

            # DE BASISLIJN ZAAIEN (ADR-036 OP-122, zelfde oplossing als `verify_chain` sinds
            # 2026-08-10). Nu het venster bij de nieuwste rijen begint, wijst de `previous_hash`
            # van de eerste rij IN het venster naar een rij ERBUITEN. Startte de traversal met
            # een lege basislijn, dan week de hercompute af en heette dat MANIPULATIE -- op een
            # volkomen gave keten. Exact dezelfde lookup als de zes schrijvers doen.
            oudste = logs[0]
            if oudste.timestamp is not None:
                voorloper = await db.execute(
                    select(AuditLog.audit_hash)
                    .where(
                        AuditLog.tenant_id == tenant_id_int,
                        AuditLog.audit_hash.isnot(None),
                        AuditLog.timestamp < oudste.timestamp,
                    )
                    .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                    .limit(1)
                )
                previous_hash = voorloper.scalar_one_or_none()

            unhashed_entries = 0

            for log in logs:
                # EEN GAT IS GEEN MANIPULATIE (ADR-036 OP-108).
                #
                # Hier stond de controle op de link BUITEN deze guard, en dat meldde een
                # ongehashte rij ten onrechte als `previous_hash_mismatch` -- zijn eigen
                # `previous_hash` is immers ook NULL. En de basislijn werd daarna op `None`
                # gezet, waardoor de VOLGENDE, gehashte rij tegen de verkeerde voorganger werd
                # herberekend en als `hash_mismatch` opdook. Een gat leverde dus twee valse
                # meldingen op, net als in `get_chain_status`.
                #
                # De juiste regel is die van de zes schrijvers: overslaan en de basislijn NIET
                # verzetten.
                if log.audit_hash is None:
                    unhashed_entries += 1
                    continue

                # Independent checks (not elif): a forged entry can have both a broken
                # previous_hash link AND a recomputed-mismatched audit_hash -- report both.
                if previous_hash is not None and log.previous_hash != previous_hash:
                    tampered_entries.append(
                        {
                            "id": log.id,
                            "event_type": log.event_type,
                            "issue": "previous_hash_mismatch",
                        }
                    )
                expected_hash = verifier._compute_hash(log, previous_hash)
                if expected_hash != log.audit_hash:
                    tampered_entries.append(
                        {
                            "id": log.id,
                            "event_type": log.event_type,
                            "issue": "hash_mismatch",
                        }
                    )

                previous_hash = log.audit_hash

            return {
                # Gaten tellen mee in het oordeel maar zijn apart te lezen -- hetzelfde
                # onderscheid als `ChainVerificationResult`, anders spreken de endpoints elkaar
                # tegen (ADR-036 OP-108).
                "verified": len(tampered_entries) == 0 and unhashed_entries == 0,
                "tampering_detected": len(tampered_entries) > 0,
                "unhashed_entries": unhashed_entries,
                "entries_checked": len(logs),
                "tampered_entries": tampered_entries,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }

        except SQLAlchemyError as e:
            logger.error("Failed to verify log integrity: %s", e)
            return {"verified": False, "error": str(e)}


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Global service instance
_security_audit_service: SecurityAuditService | None = None


def get_security_audit_service() -> SecurityAuditService:
    """Get global security audit service instance."""
    global _security_audit_service
    if _security_audit_service is None:
        _security_audit_service = SecurityAuditService()
    return _security_audit_service


async def log_security_event(
    db: AsyncSession,
    event_type: SecurityEventType,
    source_ip: str,
    endpoint: str,
    description: str,
    severity: ThreatLevel = ThreatLevel.INFO,
    **kwargs: Any,
) -> str | None:
    """
    Convenience function to log a security event.

    Args:
        db: Database session
        event_type: Type of security event
        source_ip: Client IP address
        endpoint: API endpoint
        description: Event description
        severity: Threat level (default: INFO)
        **kwargs: Additional parameters passed to log_event

    Returns:
        Event ID if successful
    """
    service = get_security_audit_service()
    return await service.log_event(
        db=db,
        event_type=event_type,
        severity=severity,
        source_ip=source_ip,
        endpoint=endpoint,
        description=description,
        **kwargs,
    )
