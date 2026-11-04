"""
Audit Logger - Immutable Audit Trail for ALS 2.0

Provides enterprise-grade audit logging with:
- Immutable, append-only audit events
- SHA-256 hash chain for tamper evidence
- GDPR data access logging
- SOC2 control logging
- Compliance report generation

Usage:
    logger = AuditLogger(tenant_id=1)

    # Log contract event
    await logger.log_contract_event(
        event_type=AuditEventType.CONTRACT_EXECUTED,
        contract_id="contract-001",
        actor_id="agent-001",
        details={"prana_cost": 50}
    )

    # Generate compliance report
    report = await logger.generate_gdpr_report(
        start_date=datetime.now(timezone.utc) - timedelta(days=30)
    )
"""

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, cast

logger = logging.getLogger("AuditLogger")


class AuditEventType(Enum):
    """Types of auditable events."""

    # Contract events
    CONTRACT_PROPOSED = "contract_proposed"
    CONTRACT_AGREED = "contract_agreed"
    CONTRACT_REJECTED = "contract_rejected"
    CONTRACT_EXECUTED = "contract_executed"
    CONTRACT_SETTLED = "contract_settled"
    CONTRACT_FAILED = "contract_failed"
    CONTRACT_VETOED = "contract_vetoed"
    CONTRACT_OVERRIDDEN = "contract_overridden"

    # Data access events (GDPR)
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    PII_ACCESS = "pii_access"

    # Security events (SOC2)
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_DENIED = "authorization_denied"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    POLICY_VIOLATION = "policy_violation"

    # Administrative events
    POLICY_CHANGED = "policy_changed"
    CONFIG_CHANGED = "config_changed"
    AGENT_REGISTERED = "agent_registered"
    AGENT_UNREGISTERED = "agent_unregistered"

    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    ERROR_OCCURRED = "error_occurred"


class DataClassification(Enum):
    """Data classification levels for GDPR."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # PII


@dataclass(frozen=True)
class AuditEvent:
    """
    Immutable audit event.

    All audit events are frozen (immutable) and include:
    - Unique event ID
    - Timestamp
    - Event type
    - Actor information
    - Data classification
    - SHA-256 hash for integrity
    - Hash chain to previous event
    """

    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    tenant_id: int
    actor_id: str
    actor_type: str  # "agent", "user", "system"
    resource_type: str  # "contract", "data", "policy"
    resource_id: str
    action: str
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    data_classification: DataClassification
    correlation_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    previous_hash: str = "0" * 32
    event_hash: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.event_hash is None:
            object.__setattr__(self, "event_hash", self.compute_hash())

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of event data."""
        data = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "details": self.details,
            "data_classification": self.data_classification.value,
            "correlation_id": self.correlation_id,
            "previous_hash": self.previous_hash,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "details": self.details,
            "data_classification": self.data_classification.value,
            "correlation_id": self.correlation_id,
            "ip_address": self.ip_address,
            "event_hash": self.event_hash,
            "previous_hash": self.previous_hash,
        }


@dataclass
class GDPRReport:
    """GDPR compliance report."""

    report_id: str
    generated_at: datetime
    tenant_id: int
    period_start: datetime
    period_end: datetime

    # Data access statistics
    total_data_accesses: int
    pii_accesses: int
    data_modifications: int
    data_deletions: int
    data_exports: int

    # Access by purpose
    access_by_purpose: dict[str, int]

    # Data subject requests
    data_subject_requests: int
    requests_fulfilled: int
    avg_response_time_hours: float

    # Retention compliance
    records_past_retention: int
    auto_deletions: int

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return asdict(self)


@dataclass
class SOC2Report:
    """SOC2 compliance report."""

    report_id: str
    generated_at: datetime
    tenant_id: int
    period_start: datetime
    period_end: datetime

    # Access control
    total_authentications: int
    failed_authentications: int
    authorization_denials: int

    # Session management
    active_sessions: int
    avg_session_duration_minutes: float
    sessions_terminated_abnormally: int

    # Policy violations
    policy_violations: int
    violations_by_type: dict[str, int]

    # System availability
    uptime_percentage: float
    system_starts: int
    system_shutdowns: int

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return asdict(self)


@dataclass
class ComplianceReport:
    """Combined compliance report."""

    report_id: str
    generated_at: datetime
    tenant_id: int
    period_start: datetime
    period_end: datetime
    gdpr_report: GDPRReport | None = None
    soc2_report: SOC2Report | None = None

    # Overall compliance score
    compliance_score: float = 0.0

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "tenant_id": self.tenant_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "gdpr_report": self.gdpr_report.to_dict() if self.gdpr_report else None,
            "soc2_report": self.soc2_report.to_dict() if self.soc2_report else None,
            "compliance_score": self.compliance_score,
            "recommendations": self.recommendations,
        }


class AuditLogger:
    """
    Enterprise-grade audit logger.

    Provides immutable, tamper-evident audit logging with
    hash chaining for compliance and security.

    Note: This is an in-memory implementation for Sprint G.
    Production would use PostgreSQL with append-only tables.
    """

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self._events: list[AuditEvent] = []
        self._events_by_type: dict[AuditEventType, list[AuditEvent]] = defaultdict(list)
        self._events_by_resource: dict[str, list[AuditEvent]] = defaultdict(list)
        self._events_by_actor: dict[str, list[AuditEvent]] = defaultdict(list)
        self._event_hashes: set[str] = set()
        self._last_hash: str = "0" * 32

        logger.info(f"AuditLogger initialized for tenant {tenant_id}")

    async def log_event(
        self,
        event_type: AuditEventType,
        actor_id: str,
        actor_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        data_classification: DataClassification = DataClassification.INTERNAL,
        correlation_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditEvent:
        """
        Log an audit event.

        Returns the created AuditEvent.
        """
        import uuid

        event_id = f"audit_{uuid.uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc)

        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            tenant_id=self.tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details,
            data_classification=data_classification,
            correlation_id=correlation_id or event_id,
            ip_address=ip_address,
            user_agent=user_agent,
            previous_hash=self._last_hash,
        )

        # Store event
        self._events.append(event)
        self._events_by_type[event_type].append(event)
        self._events_by_resource[resource_id].append(event)
        self._events_by_actor[actor_id].append(event)
        if event.event_hash is not None:
            self._event_hashes.add(event.event_hash)
            self._last_hash = event.event_hash

        logger.debug(f"Audit event logged: {event_type.value}")

        return event

    async def log_contract_event(
        self,
        event_type: AuditEventType,
        contract_id: str,
        actor_id: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        correlation_id: str | None = None,
    ) -> AuditEvent:
        """Convenience method for logging contract events."""
        return await self.log_event(
            event_type=event_type,
            actor_id=actor_id,
            actor_type="agent",
            resource_type="contract",
            resource_id=contract_id,
            action=event_type.value,
            details=details,
            data_classification=DataClassification.CONFIDENTIAL,
            correlation_id=correlation_id,
        )

    async def log_data_access(
        self,
        actor_id: str,
        data_type: str,
        data_id: str,
        is_pii: bool = False,
        purpose: str = "",
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> AuditEvent:
        """Log data access for GDPR compliance."""
        return await self.log_event(
            event_type=AuditEventType.PII_ACCESS if is_pii else AuditEventType.DATA_ACCESS,
            actor_id=actor_id,
            actor_type="user" if "user" in actor_id else "agent",
            resource_type=data_type,
            resource_id=data_id,
            action="access",
            details={"purpose": purpose, **(details or {})},
            data_classification=(
                DataClassification.RESTRICTED if is_pii else DataClassification.CONFIDENTIAL
            ),
        )

    async def log_security_event(
        self,
        event_type: AuditEventType,
        actor_id: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log security event for SOC2 compliance."""
        return await self.log_event(
            event_type=event_type,
            actor_id=actor_id,
            actor_type="user" if "user" in actor_id else "system",
            resource_type="system",
            resource_id="security",
            action=event_type.value,
            details=details,
            data_classification=DataClassification.CONFIDENTIAL,
            ip_address=ip_address,
        )

    def get_events(
        self,
        event_type: AuditEventType | None = None,
        resource_id: str | None = None,
        actor_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        data_classification: DataClassification | None = None,
    ) -> list[AuditEvent]:
        """Query audit events with filters."""
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if resource_id:
            events = [e for e in events if e.resource_id == resource_id]

        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]

        if since:
            events = [e for e in events if e.timestamp >= since]

        if until:
            events = [e for e in events if e.timestamp <= until]

        if data_classification:
            events = [e for e in events if e.data_classification == data_classification]

        return sorted(events, key=lambda e: e.timestamp)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """
        Verify the integrity of the audit log.

        Returns (is_valid, list_of_errors).
        """
        errors: list[str] = []

        for i, event in enumerate(self._events):
            # Verify event hash
            computed_hash = event.compute_hash()
            event_hash: str | None = event.event_hash
            if event_hash is None:
                errors.append(f"Event {event.event_id}: missing event hash")
                continue
            if event_hash != computed_hash:
                errors.append(
                    f"Event {event.event_id}: hash mismatch "
                    f"(stored={event_hash}, computed={computed_hash})"
                )

            # Verify chain (except for first event)
            if i > 0:
                prev_event_hash: str | None = self._events[i - 1].event_hash
                if prev_event_hash is None:
                    errors.append(f"Event {event.event_id}: previous event missing hash")
                    continue
                expected_previous: str = prev_event_hash
                if event.previous_hash != expected_previous:
                    errors.append(
                        f"Event {event.event_id}: chain break "
                        f"(previous_hash={event.previous_hash}, expected={expected_previous})"
                    )

        return len(errors) == 0, errors

    async def generate_gdpr_report(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> GDPRReport:
        """Generate GDPR compliance report."""
        import uuid

        events = self.get_events(since=period_start, until=period_end)

        # Count data accesses
        data_accesses = [e for e in events if e.event_type == AuditEventType.DATA_ACCESS]
        pii_accesses = [e for e in events if e.event_type == AuditEventType.PII_ACCESS]
        modifications = [e for e in events if e.event_type == AuditEventType.DATA_MODIFICATION]
        deletions = [e for e in events if e.event_type == AuditEventType.DATA_DELETION]
        exports = [e for e in events if e.event_type == AuditEventType.DATA_EXPORT]

        # Access by purpose
        access_by_purpose: dict[str, int] = defaultdict(int)
        for event in data_accesses + pii_accesses:
            purpose = event.details.get("purpose", "unspecified")
            access_by_purpose[purpose] += 1

        return GDPRReport(
            report_id=f"GDPR-{uuid.uuid4().hex[:8].upper()}",
            generated_at=datetime.now(timezone.utc),
            tenant_id=self.tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_data_accesses=len(data_accesses),
            pii_accesses=len(pii_accesses),
            data_modifications=len(modifications),
            data_deletions=len(deletions),
            data_exports=len(exports),
            access_by_purpose=dict(access_by_purpose),
            data_subject_requests=0,  # Would be tracked separately
            requests_fulfilled=0,
            avg_response_time_hours=0.0,
            records_past_retention=0,
            auto_deletions=0,
        )

    async def generate_soc2_report(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> SOC2Report:
        """Generate SOC2 compliance report."""
        import uuid

        events = self.get_events(since=period_start, until=period_end)

        # Authentication statistics
        auth_success = [e for e in events if e.event_type == AuditEventType.AUTHENTICATION_SUCCESS]
        auth_failure = [e for e in events if e.event_type == AuditEventType.AUTHENTICATION_FAILURE]
        auth_denials = [e for e in events if e.event_type == AuditEventType.AUTHORIZATION_DENIED]

        # Policy violations
        violations = [e for e in events if e.event_type == AuditEventType.POLICY_VIOLATION]
        violations_by_type: dict[str, int] = defaultdict(int)
        for v in violations:
            v_type = v.details.get("violation_type", "unknown")
            violations_by_type[v_type] += 1

        # System events
        system_starts = len([e for e in events if e.event_type == AuditEventType.SYSTEM_STARTUP])
        system_shutdowns = len(
            [e for e in events if e.event_type == AuditEventType.SYSTEM_SHUTDOWN]
        )

        return SOC2Report(
            report_id=f"SOC2-{uuid.uuid4().hex[:8].upper()}",
            generated_at=datetime.now(timezone.utc),
            tenant_id=self.tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_authentications=len(auth_success) + len(auth_failure),
            failed_authentications=len(auth_failure),
            authorization_denials=len(auth_denials),
            active_sessions=0,  # Would be tracked in session store
            avg_session_duration_minutes=0.0,
            sessions_terminated_abnormally=0,
            policy_violations=len(violations),
            violations_by_type=dict(violations_by_type),
            uptime_percentage=99.9,  # Would be calculated from monitoring
            system_starts=system_starts,
            system_shutdowns=system_shutdowns,
        )

    async def generate_compliance_report(
        self,
        period_start: datetime,
        period_end: datetime,
        include_gdpr: bool = True,
        include_soc2: bool = True,
    ) -> ComplianceReport:
        """Generate combined compliance report."""
        import uuid

        gdpr_report = None
        soc2_report = None

        if include_gdpr:
            gdpr_report = await self.generate_gdpr_report(period_start, period_end)

        if include_soc2:
            soc2_report = await self.generate_soc2_report(period_start, period_end)

        # Calculate overall compliance score
        compliance_score = 100.0
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if gdpr_report:
            if gdpr_report.pii_accesses > 100:
                compliance_score -= 10
                recommendations.append(
                    "High volume of PII access detected - review access controls"
                )
            if gdpr_report.data_deletions < gdpr_report.data_modifications * 0.1:
                compliance_score -= 5
                recommendations.append("Low deletion rate - verify retention policies")

        if soc2_report:
            if soc2_report.failed_authentications > soc2_report.total_authentications * 0.05:
                compliance_score -= 15
                recommendations.append(
                    "High authentication failure rate - investigate potential attacks"
                )
            if soc2_report.policy_violations > 10:
                compliance_score -= 10
                recommendations.append("Multiple policy violations - strengthen enforcement")

        return ComplianceReport(
            report_id=f"COMP-{uuid.uuid4().hex[:8].upper()}",
            generated_at=datetime.now(timezone.utc),
            tenant_id=self.tenant_id,
            period_start=period_start,
            period_end=period_end,
            gdpr_report=gdpr_report,
            soc2_report=soc2_report,
            compliance_score=max(0, compliance_score),
            recommendations=recommendations,
        )

    def get_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get audit log statistics."""
        return {
            "tenant_id": self.tenant_id,
            "total_events": len(self._events),
            "events_by_type": {
                et.value: len(events) for et, events in self._events_by_type.items()
            },
            "unique_actors": len(self._events_by_actor),
            "unique_resources": len(self._events_by_resource),
            "integrity_verified": self.verify_integrity()[0],
        }

    def export_to_json(self, since: datetime | None = None) -> str:
        """Export audit log to JSON string."""
        events = self.get_events(since=since)
        data = {
            "tenant_id": self.tenant_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "event_count": len(events),
            "events": [e.to_dict() for e in events],
        }
        return json.dumps(data, indent=2)
