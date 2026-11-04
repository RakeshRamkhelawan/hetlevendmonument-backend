"""
Security Monitor - Real-time Security Event Monitoring

Provides real-time monitoring of security events with:
- Pattern-based threat detection
- Alert generation and escalation
- Integration with Immune System
- Anomaly detection

Usage:
    monitor = SecurityMonitor(tenant_id=1, signal_bus=signal_bus)
    await monitor.initialize()

    # Monitor will automatically detect threats and emit alerts
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
from collections.abc import Callable

from src.core.als.enterprise.audit.audit_logger import AuditEvent, AuditEventType, AuditLogger

if TYPE_CHECKING:
    from src.core.als.infrastructure.signal_bus import SignalBus

logger = logging.getLogger("SecurityMonitor")


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityAlert:
    """Security alert."""

    alert_id: str
    timestamp: datetime
    tenant_id: int
    severity: AlertSeverity
    alert_type: str
    title: str
    description: str
    source_events: list[str]  # Event IDs
    affected_resources: list[str]
    actor_id: str | None = None
    status: AlertStatus = AlertStatus.NEW
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    recommended_actions: list[str] = field(default_factory=list)


@dataclass
class ThreatPattern:
    """Threat detection pattern."""

    pattern_id: str
    name: str
    description: str
    event_types: list[AuditEventType]
    conditions: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    severity: AlertSeverity
    time_window_seconds: int
    threshold: int


class SecurityMonitor:
    """
    Real-time security event monitor.

    Monitors audit events for security threats and generates alerts.
    Can integrate with Immune System for automated response.
    """

    # Default threat patterns
    DEFAULT_PATTERNS: list[ThreatPattern] = [
        ThreatPattern(
            pattern_id="P001",
            name="Multiple Failed Authentications",
            description="Multiple authentication failures from same actor",
            event_types=[AuditEventType.AUTHENTICATION_FAILURE],
            conditions={"count": 5},
            severity=AlertSeverity.HIGH,
            time_window_seconds=300,  # 5 minutes
            threshold=5,
        ),
        ThreatPattern(
            pattern_id="P002",
            name="Unauthorized PII Access",
            description="Access to PII without proper authorization",
            event_types=[AuditEventType.PII_ACCESS],
            conditions={"unauthorized": True},
            severity=AlertSeverity.CRITICAL,
            time_window_seconds=60,
            threshold=1,
        ),
        ThreatPattern(
            pattern_id="P003",
            name="Policy Violation Spike",
            description="Multiple policy violations in short time",
            event_types=[AuditEventType.POLICY_VIOLATION],
            conditions={"count": 3},
            severity=AlertSeverity.MEDIUM,
            time_window_seconds=600,  # 10 minutes
            threshold=3,
        ),
        ThreatPattern(
            pattern_id="P004",
            name="Abnormal Data Export",
            description="Large volume of data exports",
            event_types=[AuditEventType.DATA_EXPORT],
            conditions={"count": 10},
            severity=AlertSeverity.HIGH,
            time_window_seconds=3600,  # 1 hour
            threshold=10,
        ),
        ThreatPattern(
            pattern_id="P005",
            name="Contract Veto Pattern",
            description="Multiple contract vetoes indicating potential issues",
            event_types=[AuditEventType.CONTRACT_VETOED],
            conditions={"count": 3},
            severity=AlertSeverity.MEDIUM,
            time_window_seconds=1800,  # 30 minutes
            threshold=3,
        ),
    ]

    def __init__(
        self,
        tenant_id: int,
        audit_logger: AuditLogger,
        signal_bus: Optional["SignalBus"] = None,  # Optional SignalBus for alerts
    ) -> None:
        self.tenant_id = tenant_id
        self.audit_logger = audit_logger
        self.signal_bus = signal_bus

        # Patterns
        self._patterns: dict[str, ThreatPattern] = {p.pattern_id: p for p in self.DEFAULT_PATTERNS}

        # Event history for pattern matching (circular buffer)
        self._event_history: deque[AuditEvent] = deque(maxlen=10000)

        # Active alerts
        self._alerts: dict[str, SecurityAlert] = {}

        # Monitoring state
        self._running = False
        self._monitor_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

        # Callbacks for alert handlers
        self._alert_handlers: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

        # Statistics
        self._alerts_generated = 0
        self._events_processed = 0

        logger.info(f"SecurityMonitor initialized for tenant {tenant_id}")

    async def initialize(self) -> bool:
        """Initialize security monitoring."""
        try:
            self._running = True
            self._monitor_task = asyncio.create_task(self._monitor_loop())

            logger.info("Security monitoring started")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize security monitor: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown security monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Security monitoring stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                # Check for patterns in recent events
                await self._check_patterns()

                # Clean up old events (handled by deque maxlen)

                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(5)

    async def process_event(self, event: AuditEvent) -> None:
        """Process an audit event for threat detection."""
        self._events_processed += 1
        self._event_history.append(event)

        # Immediate check for critical events
        if event.event_type in [
            AuditEventType.PII_ACCESS,
            AuditEventType.AUTHORIZATION_DENIED,
        ]:
            await self._check_immediate_threats(event)

    async def _check_immediate_threats(self, event: AuditEvent) -> None:
        """Check for immediate threats (single-event patterns)."""
        # Check for unauthorized PII access
        if event.event_type == AuditEventType.PII_ACCESS:
            if event.details.get("unauthorized"):
                await self._generate_alert(
                    alert_type="UNAUTHORIZED_PII_ACCESS",
                    severity=AlertSeverity.CRITICAL,
                    title="Unauthorized PII Access Detected",
                    description=f"Actor {event.actor_id} attempted unauthorized access to PII",
                    source_events=[event.event_id],
                    affected_resources=[event.resource_id],
                    actor_id=event.actor_id,
                    recommended_actions=[
                        "Review access controls immediately",
                        "Verify actor permissions",
                        "Consider blocking actor pending investigation",
                    ],
                )

    async def _check_patterns(self) -> None:
        """Check event history against threat patterns."""
        now = datetime.now(timezone.utc)

        for pattern in self._patterns.values():
            # Get events matching pattern types within time window
            cutoff = now - timedelta(seconds=pattern.time_window_seconds)

            matching_events = [
                e
                for e in self._event_history
                if e.event_type in pattern.event_types and e.timestamp >= cutoff
            ]

            if len(matching_events) >= pattern.threshold:
                # Pattern matched - generate alert
                await self._generate_alert_from_pattern(pattern, matching_events)

    async def _generate_alert_from_pattern(
        self,
        pattern: ThreatPattern,
        events: list[AuditEvent],
    ) -> None:
        """Generate an alert from a matched pattern."""
        # Group by actor to see if it's concentrated
        events_by_actor: dict[str, list[AuditEvent]] = defaultdict(list)
        for e in events:
            events_by_actor[e.actor_id].append(e)

        # Find actor with most events
        primary_actor = max(events_by_actor.keys(), key=lambda a: len(events_by_actor[a]))
        actor_events = events_by_actor[primary_actor]

        await self._generate_alert(
            alert_type=pattern.name.upper().replace(" ", "_"),
            severity=pattern.severity,
            title=f"Threat Detected: {pattern.name}",
            description=pattern.description,
            source_events=[e.event_id for e in events],
            affected_resources=list({e.resource_id for e in events}),
            actor_id=primary_actor,
            recommended_actions=[
                "Review recent activity for this actor",
                "Check for compromised credentials",
                "Consider temporary access restriction",
            ],
        )

    async def _generate_alert(
        self,
        alert_type: str,
        severity: AlertSeverity,
        title: str,
        description: str,
        source_events: list[str],
        affected_resources: list[str],
        actor_id: str | None = None,
        recommended_actions: list[str] | None = None,
    ) -> None:
        """Generate a security alert."""
        import uuid

        alert_id = f"SEC-{uuid.uuid4().hex[:8].upper()}"

        alert = SecurityAlert(
            alert_id=alert_id,
            timestamp=datetime.now(timezone.utc),
            tenant_id=self.tenant_id,
            severity=severity,
            alert_type=alert_type,
            title=title,
            description=description,
            source_events=source_events,
            affected_resources=affected_resources,
            actor_id=actor_id,
            recommended_actions=recommended_actions or [],
        )

        self._alerts[alert_id] = alert
        self._alerts_generated += 1

        # Log the alert
        await self.audit_logger.log_security_event(
            event_type=AuditEventType.POLICY_VIOLATION,
            actor_id="security_monitor",
            details={
                "alert_id": alert_id,
                "alert_type": alert_type,
                "severity": severity.value,
                "description": description,
            },
        )

        # Notify handlers
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

        # Emit to signal bus if available
        if self.signal_bus:
            try:
                from src.core.als.infrastructure.signal_bus import Signal, SignalTier

                signal = Signal(
                    tenant_id=self.tenant_id,
                    source_agent_id="security_monitor",
                    target_agent_ids=["chief_orchestrator", "immune_system"],
                    tier=(
                        SignalTier.REFLEX
                        if severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]
                        else SignalTier.COGNITIVE
                    ),
                    payload={
                        "type": "security_alert",
                        "alert": {
                            "id": alert_id,
                            "severity": severity.value,
                            "title": title,
                            "actor_id": actor_id,
                        },
                    },
                )
                await self.signal_bus.emit(signal)
            except Exception as e:
                logger.error(f"Failed to emit alert signal: {e}")

        logger.warning(f"Security alert generated: {alert_id} - {title}")

    def add_alert_handler(self, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add a handler for security alerts."""
        self._alert_handlers.append(handler)

    def get_alert(self, alert_id: str) -> SecurityAlert | None:
        """Get an alert by ID."""
        return self._alerts.get(alert_id)

    def get_alerts(
        self,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        since: datetime | None = None,
    ) -> list[SecurityAlert]:
        """Get alerts with filters."""
        alerts = list(self._alerts.values())

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if status:
            alerts = [a for a in alerts if a.status == status]

        if since:
            alerts = [a for a in alerts if a.timestamp >= since]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = datetime.now(timezone.utc)

        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
        return True

    def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: str,
    ) -> bool:
        """Resolve an alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_by = resolved_by
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolution_notes = resolution_notes

        logger.info(f"Alert {alert_id} resolved by {resolved_by}")
        return True

    def add_custom_pattern(self, pattern: ThreatPattern) -> None:
        """Add a custom threat pattern."""
        self._patterns[pattern.pattern_id] = pattern
        logger.info(f"Custom pattern added: {pattern.pattern_id}")

    def get_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get monitor statistics."""
        return {
            "tenant_id": self.tenant_id,
            "events_processed": self._events_processed,
            "alerts_generated": self._alerts_generated,
            "patterns_active": len(self._patterns),
            "active_alerts": len([a for a in self._alerts.values() if a.status == AlertStatus.NEW]),
            "alerts_by_severity": {
                sev.value: len([a for a in self._alerts.values() if a.severity == sev])
                for sev in AlertSeverity
            },
        }
