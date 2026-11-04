"""
Tests for Security Monitor - Real-time Security Monitoring

Sprint G: Security Event Monitoring
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core.als.enterprise.audit.audit_logger import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    DataClassification,
)
from src.core.als.enterprise.audit.security_monitor import (
    AlertSeverity,
    AlertStatus,
    SecurityAlert,
    SecurityMonitor,
    ThreatPattern,
)


@pytest.fixture
def audit_logger():
    """Create an AuditLogger instance."""
    return AuditLogger(tenant_id=1)


@pytest.fixture
def security_monitor(audit_logger):
    """Create a SecurityMonitor instance."""
    return SecurityMonitor(
        tenant_id=1,
        audit_logger=audit_logger,
    )


class TestThreatPattern:
    """Test threat pattern detection."""

    def test_default_patterns_loaded(self, security_monitor):
        """Test that default patterns are loaded."""
        assert len(security_monitor._patterns) > 0
        assert "P001" in security_monitor._patterns  # Failed auth pattern
        assert "P002" in security_monitor._patterns  # PII access pattern


class TestSecurityAlert:
    """Test SecurityAlert model."""

    def test_alert_creation(self):
        """Test creating a security alert."""
        alert = SecurityAlert(
            alert_id="SEC-001",
            timestamp=datetime.now(timezone.utc),
            tenant_id=1,
            severity=AlertSeverity.HIGH,
            alert_type="TEST_ALERT",
            title="Test Alert",
            description="This is a test alert",
            source_events=["evt-001", "evt-002"],
            affected_resources=["res-001"],
            actor_id="actor-001",
            recommended_actions=["Action 1", "Action 2"],
        )

        assert alert.alert_id == "SEC-001"
        assert alert.status == AlertStatus.NEW
        assert len(alert.recommended_actions) == 2


class TestSecurityMonitorBasic:
    """Test basic security monitor functionality."""

    @pytest.mark.asyncio
    async def test_initialization(self, security_monitor):
        """Test monitor initialization."""
        result = await security_monitor.initialize()
        assert result is True
        assert security_monitor._running is True

        await security_monitor.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self, security_monitor):
        """Test monitor shutdown."""
        await security_monitor.initialize()
        await security_monitor.shutdown()

        assert security_monitor._running is False

    @pytest.mark.asyncio
    async def test_process_event(self, security_monitor):
        """Test processing an audit event."""
        event = AuditEvent(
            event_id="audit-001",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.CONTRACT_PROPOSED,
            tenant_id=1,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="c-001",
            action="propose",
            details={},
            data_classification=DataClassification.INTERNAL,
        )

        await security_monitor.process_event(event)

        assert security_monitor._events_processed == 1
        assert len(security_monitor._event_history) == 1


class TestThreatDetection:
    """Test threat detection patterns."""

    @pytest.mark.asyncio
    async def test_detect_failed_authentication_pattern(self, security_monitor, audit_logger):
        """Test detection of multiple failed authentications."""
        await security_monitor.initialize()

        # Simulate 5 failed authentication attempts from same user
        for i in range(5):
            event = AuditEvent(
                event_id=f"audit-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.AUTHENTICATION_FAILURE,
                tenant_id=1,
                actor_id="user-001",
                actor_type="user",
                resource_type="system",
                resource_id="auth",
                action="authenticate",
                details={"reason": "wrong_password"},
                data_classification=DataClassification.INTERNAL,
            )
            await security_monitor.process_event(event)

        # Wait for pattern check
        await asyncio.sleep(6)

        # Check if alert was generated
        alerts = security_monitor.get_alerts()

        await security_monitor.shutdown()

        # Should have detected the pattern
        assert len(alerts) >= 1
        assert any("Multiple Failed Authentications" in a.title for a in alerts)

    @pytest.mark.asyncio
    async def test_detect_unauthorized_pii_access(self, security_monitor):
        """Test immediate detection of unauthorized PII access."""
        await security_monitor.initialize()

        event = AuditEvent(
            event_id="audit-001",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.PII_ACCESS,
            tenant_id=1,
            actor_id="user-001",
            actor_type="user",
            resource_type="profile",
            resource_id="profile-001",
            action="access",
            details={"unauthorized": True},
            data_classification=DataClassification.RESTRICTED,
        )

        await security_monitor.process_event(event)

        # Wait for processing
        await asyncio.sleep(1)

        alerts = security_monitor.get_alerts()

        await security_monitor.shutdown()

        # Should have generated critical alert
        assert len(alerts) >= 1
        assert any(a.severity == AlertSeverity.CRITICAL for a in alerts)

    @pytest.mark.asyncio
    async def test_detect_contract_veto_pattern(self, security_monitor):
        """Test detection of multiple contract vetoes."""
        await security_monitor.initialize()

        # Simulate 3 contract vetoes
        for i in range(3):
            event = AuditEvent(
                event_id=f"audit-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.CONTRACT_VETOED,
                tenant_id=1,
                actor_id="shadow_ceo",
                actor_type="system",
                resource_type="contract",
                resource_id=f"c-{i}",
                action="veto",
                details={"reason": "high_risk"},
                data_classification=DataClassification.CONFIDENTIAL,
            )
            await security_monitor.process_event(event)

        # Wait for pattern check
        await asyncio.sleep(6)

        alerts = security_monitor.get_alerts()

        await security_monitor.shutdown()

        # Should have detected veto pattern
        assert any("Contract Veto Pattern" in a.title for a in alerts)


class TestAlertManagement:
    """Test alert lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_alert(self, security_monitor):
        """Test retrieving an alert by ID."""
        # Manually add an alert
        alert = SecurityAlert(
            alert_id="SEC-001",
            timestamp=datetime.now(timezone.utc),
            tenant_id=1,
            severity=AlertSeverity.HIGH,
            alert_type="TEST",
            title="Test Alert",
            description="Test",
            source_events=["evt-001"],
            affected_resources=["res-001"],
        )
        security_monitor._alerts["SEC-001"] = alert

        retrieved = security_monitor.get_alert("SEC-001")

        assert retrieved is not None
        assert retrieved.alert_id == "SEC-001"

    @pytest.mark.asyncio
    async def test_get_alerts_by_severity(self, security_monitor):
        """Test filtering alerts by severity."""
        # Add alerts of different severities
        for severity in [AlertSeverity.LOW, AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
            alert = SecurityAlert(
                alert_id=f"SEC-{severity.value}",
                timestamp=datetime.now(timezone.utc),
                tenant_id=1,
                severity=severity,
                alert_type="TEST",
                title=f"{severity.value} Alert",
                description="Test",
                source_events=[],
                affected_resources=[],
            )
            security_monitor._alerts[alert.alert_id] = alert

        high_alerts = security_monitor.get_alerts(severity=AlertSeverity.HIGH)

        assert len(high_alerts) == 1
        assert high_alerts[0].severity == AlertSeverity.HIGH

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, security_monitor):
        """Test acknowledging an alert."""
        alert = SecurityAlert(
            alert_id="SEC-001",
            timestamp=datetime.now(timezone.utc),
            tenant_id=1,
            severity=AlertSeverity.HIGH,
            alert_type="TEST",
            title="Test Alert",
            description="Test",
            source_events=[],
            affected_resources=[],
        )
        security_monitor._alerts["SEC-001"] = alert

        result = security_monitor.acknowledge_alert("SEC-001", "admin-001")

        assert result is True
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "admin-001"
        assert alert.acknowledged_at is not None

    @pytest.mark.asyncio
    async def test_resolve_alert(self, security_monitor):
        """Test resolving an alert."""
        alert = SecurityAlert(
            alert_id="SEC-001",
            timestamp=datetime.now(timezone.utc),
            tenant_id=1,
            severity=AlertSeverity.HIGH,
            alert_type="TEST",
            title="Test Alert",
            description="Test",
            source_events=[],
            affected_resources=[],
        )
        security_monitor._alerts["SEC-001"] = alert

        result = security_monitor.resolve_alert(
            "SEC-001", "admin-001", "Investigation complete - false positive"
        )

        assert result is True
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_by == "admin-001"
        assert alert.resolution_notes == "Investigation complete - false positive"

    @pytest.mark.asyncio
    async def test_get_nonexistent_alert(self, security_monitor):
        """Test retrieving non-existent alert."""
        alert = security_monitor.get_alert("NONEXISTENT")

        assert alert is None


class TestCustomPatterns:
    """Test custom threat patterns."""

    @pytest.mark.asyncio
    async def test_add_custom_pattern(self, security_monitor):
        """Test adding a custom threat pattern."""
        custom_pattern = ThreatPattern(
            pattern_id="CUSTOM-001",
            name="Custom Pattern",
            description="Test custom pattern",
            event_types=[AuditEventType.DATA_EXPORT],
            conditions={"count": 5},
            severity=AlertSeverity.MEDIUM,
            time_window_seconds=300,
            threshold=5,
        )

        security_monitor.add_custom_pattern(custom_pattern)

        assert "CUSTOM-001" in security_monitor._patterns


class TestStatistics:
    """Test security monitor statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, security_monitor):
        """Test statistics generation."""
        # Process some events
        for i in range(10):
            event = AuditEvent(
                event_id=f"audit-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.CONTRACT_PROPOSED,
                tenant_id=1,
                actor_id=f"agent-{i}",
                actor_type="agent",
                resource_type="contract",
                resource_id=f"c-{i}",
                action="propose",
                details={},
                data_classification=DataClassification.INTERNAL,
            )
            await security_monitor.process_event(event)

        # Add some alerts
        for severity in [AlertSeverity.LOW, AlertSeverity.HIGH]:
            alert = SecurityAlert(
                alert_id=f"SEC-{severity.value}",
                timestamp=datetime.now(timezone.utc),
                tenant_id=1,
                severity=severity,
                alert_type="TEST",
                title="Test",
                description="Test",
                source_events=[],
                affected_resources=[],
            )
            security_monitor._alerts[alert.alert_id] = alert

        stats = security_monitor.get_statistics()

        assert stats["tenant_id"] == 1
        assert stats["events_processed"] == 10
        assert stats["alerts_generated"] == 0  # Alerts added directly, not generated
        assert stats["patterns_active"] > 0


class TestAlertHandlers:
    """Test alert handler callbacks."""

    @pytest.mark.asyncio
    async def test_add_alert_handler(self, security_monitor):
        """Test adding an alert handler."""
        handler_called = False
        received_alert = None

        def test_handler(alert):
            nonlocal handler_called, received_alert
            handler_called = True
            received_alert = alert

        security_monitor.add_alert_handler(test_handler)

        # Create an alert
        alert = SecurityAlert(
            alert_id="SEC-001",
            timestamp=datetime.now(timezone.utc),
            tenant_id=1,
            severity=AlertSeverity.HIGH,
            alert_type="TEST",
            title="Test Alert",
            description="Test",
            source_events=["evt-001"],
            affected_resources=["res-001"],
        )
        security_monitor._alerts["SEC-001"] = alert

        # Manually trigger handlers by generating an alert
        await security_monitor._generate_alert(
            alert_type="TEST",
            severity=AlertSeverity.HIGH,
            title="Test",
            description="Test",
            source_events=["evt-001"],
            affected_resources=["res-001"],
        )

        assert handler_called is True
        assert received_alert is not None
