"""
Tests for Audit Logger - Immutable Audit Trail

Sprint G: Audit Logging & Compliance
"""

import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.core.als.enterprise.audit.audit_logger import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    ComplianceReport,
    DataClassification,
    GDPRReport,
    SOC2Report,
)


class TestAuditEvent:
    """Test AuditEvent model."""

    def test_event_creation(self):
        """Test creating an audit event."""
        event = AuditEvent(
            event_id="audit-001",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.CONTRACT_EXECUTED,
            tenant_id=1,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="execute",
            details={"prana_cost": 50},
            data_classification=DataClassification.CONFIDENTIAL,
        )

        assert event.event_id == "audit-001"
        assert event.event_type == AuditEventType.CONTRACT_EXECUTED
        assert event.compute_hash() is not None
        assert len(event.event_hash) == 32

    def test_event_hash_deterministic(self):
        """Test that same data produces same hash."""
        timestamp = datetime.now(timezone.utc)

        event1 = AuditEvent(
            event_id="audit-001",
            timestamp=timestamp,
            event_type=AuditEventType.CONTRACT_EXECUTED,
            tenant_id=1,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="execute",
            details={"prana_cost": 50},
            data_classification=DataClassification.CONFIDENTIAL,
            previous_hash="0" * 32,
        )

        event2 = AuditEvent(
            event_id="audit-001",
            timestamp=timestamp,
            event_type=AuditEventType.CONTRACT_EXECUTED,
            tenant_id=1,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="execute",
            details={"prana_cost": 50},
            data_classification=DataClassification.CONFIDENTIAL,
            previous_hash="0" * 32,
        )

        assert event1.compute_hash() == event2.compute_hash()

    def test_event_immutability(self):
        """Test that events are immutable."""
        event = AuditEvent(
            event_id="audit-001",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.CONTRACT_EXECUTED,
            tenant_id=1,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="execute",
            details={},
            data_classification=DataClassification.CONFIDENTIAL,
        )

        # Attempting to modify should fail
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            event.actor_id = "hacker"

    def test_event_to_dict(self):
        """Test event serialization."""
        event = AuditEvent(
            event_id="audit-001",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            event_type=AuditEventType.DATA_ACCESS,
            tenant_id=1,
            actor_id="user-001",
            actor_type="user",
            resource_type="data",
            resource_id="data-001",
            action="read",
            details={"purpose": "reporting"},
            data_classification=DataClassification.RESTRICTED,
        )

        data = event.to_dict()

        assert data["event_id"] == "audit-001"
        assert data["event_type"] == "data_access"
        assert data["data_classification"] == "restricted"
        assert "event_hash" in data


class TestAuditLogger:
    """Test AuditLogger functionality."""

    @pytest.fixture
    def logger(self):
        """Create an AuditLogger instance."""
        return AuditLogger(tenant_id=1)

    @pytest.mark.asyncio
    async def test_log_event(self, logger):
        """Test logging an event."""
        event = await logger.log_event(
            event_type=AuditEventType.CONTRACT_PROPOSED,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="propose",
            details={"prana_cost": 50},
        )

        assert event.event_id.startswith("audit_")
        assert event.tenant_id == 1
        assert len(logger._events) == 1

    @pytest.mark.asyncio
    async def test_log_contract_event(self, logger):
        """Test logging contract event."""
        event = await logger.log_contract_event(
            event_type=AuditEventType.CONTRACT_AGREED,
            contract_id="contract-001",
            actor_id="agent-001",
            details={"terms": "accepted"},
        )

        assert event.resource_type == "contract"
        assert event.resource_id == "contract-001"
        assert event.data_classification == DataClassification.CONFIDENTIAL

    @pytest.mark.asyncio
    async def test_log_data_access(self, logger):
        """Test logging data access."""
        event = await logger.log_data_access(
            actor_id="user-001",
            data_type="user_profile",
            data_id="profile-001",
            is_pii=True,
            purpose="customer_support",
        )

        assert event.event_type == AuditEventType.PII_ACCESS
        assert event.data_classification == DataClassification.RESTRICTED
        assert event.details["purpose"] == "customer_support"

    @pytest.mark.asyncio
    async def test_log_security_event(self, logger):
        """Test logging security event."""
        event = await logger.log_security_event(
            event_type=AuditEventType.AUTHENTICATION_FAILURE,
            actor_id="user-001",
            details={"reason": "invalid_password"},
            ip_address="192.168.1.1",
        )

        assert event.event_type == AuditEventType.AUTHENTICATION_FAILURE
        assert event.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_hash_chain(self, logger):
        """Test that events form a hash chain."""
        event1 = await logger.log_event(
            event_type=AuditEventType.CONTRACT_PROPOSED,
            actor_id="agent-001",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="propose",
            details={},
        )

        event2 = await logger.log_event(
            event_type=AuditEventType.CONTRACT_AGREED,
            actor_id="agent-002",
            actor_type="agent",
            resource_type="contract",
            resource_id="contract-001",
            action="agree",
            details={},
        )

        # Second event should reference first event's hash
        assert event2.previous_hash == event1.event_hash

    @pytest.mark.asyncio
    async def test_get_events_by_type(self, logger):
        """Test querying events by type."""
        await logger.log_contract_event(AuditEventType.CONTRACT_PROPOSED, "c-001", "agent-001", {})
        await logger.log_contract_event(AuditEventType.CONTRACT_AGREED, "c-002", "agent-002", {})
        await logger.log_data_access("user-001", "data", "d-001")

        contract_events = logger.get_events(event_type=AuditEventType.CONTRACT_PROPOSED)
        assert len(contract_events) == 1

    @pytest.mark.asyncio
    async def test_get_events_by_resource(self, logger):
        """Test querying events by resource."""
        await logger.log_contract_event(AuditEventType.CONTRACT_PROPOSED, "c-001", "agent-001", {})
        await logger.log_contract_event(AuditEventType.CONTRACT_AGREED, "c-001", "agent-002", {})
        await logger.log_contract_event(AuditEventType.CONTRACT_PROPOSED, "c-002", "agent-001", {})

        events = logger.get_events(resource_id="c-001")
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_events_by_time(self, logger):
        """Test querying events by time range."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Create events at different times
        event1 = AuditEvent(
            event_id="audit-001",
            timestamp=old_time,
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
        event2 = AuditEvent(
            event_id="audit-002",
            timestamp=recent_time,
            event_type=AuditEventType.CONTRACT_AGREED,
            tenant_id=1,
            actor_id="agent-002",
            actor_type="agent",
            resource_type="contract",
            resource_id="c-002",
            action="agree",
            details={},
            data_classification=DataClassification.INTERNAL,
        )

        logger._events.extend([event1, event2])

        events = logger.get_events(since=datetime.now(timezone.utc) - timedelta(hours=1))
        assert len(events) == 1
        assert events[0].event_id == "audit-002"

    @pytest.mark.asyncio
    async def test_verify_integrity_valid(self, logger):
        """Test integrity verification with valid chain."""
        for i in range(5):
            await logger.log_contract_event(
                AuditEventType.CONTRACT_PROPOSED,
                f"c-{i:03d}",
                f"agent-{i}",
                {"seq": i},
            )

        is_valid, errors = logger.verify_integrity()
        assert is_valid is True
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_invalid(self, logger):
        """Test integrity verification detects tampering."""
        await logger.log_contract_event(AuditEventType.CONTRACT_PROPOSED, "c-001", "agent-001", {})

        # Tamper with the stored event
        import dataclasses

        object.__setattr__(logger._events[0], "event_hash", "tampered")

        is_valid, errors = logger.verify_integrity()
        assert is_valid is False
        assert len(errors) > 0


class TestGDPRReport:
    """Test GDPR compliance reporting."""

    @pytest.fixture
    def logger(self):
        """Create logger with sample events."""
        return AuditLogger(tenant_id=1)

    @pytest.mark.asyncio
    async def test_generate_gdpr_report(self, logger):
        """Test GDPR report generation."""
        # Create sample data access events
        for i in range(5):
            await logger.log_data_access(
                actor_id=f"user-{i}",
                data_type="profile",
                data_id=f"profile-{i}",
                is_pii=True,
                purpose="analytics",
            )

        await logger.log_data_access(
            actor_id="user-001",
            data_type="order",
            data_id="order-001",
            is_pii=False,
            purpose="reporting",
        )

        await logger.log_event(
            event_type=AuditEventType.DATA_DELETION,
            actor_id="admin-001",
            actor_type="user",
            resource_type="user_data",
            resource_id="data-001",
            action="delete",
            details={"reason": "user_request"},
            data_classification=DataClassification.RESTRICTED,
        )

        report = await logger.generate_gdpr_report(
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
        )

        assert isinstance(report, GDPRReport)
        assert report.report_id.startswith("GDPR-")
        assert report.tenant_id == 1
        assert report.pii_accesses == 5
        assert report.total_data_accesses == 1  # Only the non-PII DATA_ACCESS
        assert report.data_deletions == 1
        assert "analytics" in report.access_by_purpose


class TestSOC2Report:
    """Test SOC2 compliance reporting."""

    @pytest.fixture
    def logger(self):
        """Create logger with sample events."""
        return AuditLogger(tenant_id=1)

    @pytest.mark.asyncio
    async def test_generate_soc2_report(self, logger):
        """Test SOC2 report generation."""
        # Create authentication events
        for i in range(10):
            await logger.log_security_event(
                AuditEventType.AUTHENTICATION_SUCCESS,
                f"user-{i}",
                {"method": "password"},
            )

        for i in range(3):
            await logger.log_security_event(
                AuditEventType.AUTHENTICATION_FAILURE,
                f"user-{i}",
                {"reason": "wrong_password"},
            )

        await logger.log_security_event(
            AuditEventType.AUTHORIZATION_DENIED,
            "user-001",
            {"resource": "admin_panel", "reason": "insufficient_permissions"},
        )

        await logger.log_event(
            event_type=AuditEventType.POLICY_VIOLATION,
            actor_id="user-002",
            actor_type="user",
            resource_type="system",
            resource_id="policy",
            action="violate",
            details={"violation_type": "data_exfiltration"},
            data_classification=DataClassification.CONFIDENTIAL,
        )

        report = await logger.generate_soc2_report(
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
        )

        assert isinstance(report, SOC2Report)
        assert report.report_id.startswith("SOC2-")
        assert report.total_authentications == 13
        assert report.failed_authentications == 3
        assert report.authorization_denials == 1
        assert report.policy_violations == 1
        assert "data_exfiltration" in report.violations_by_type


class TestComplianceReport:
    """Test combined compliance reporting."""

    @pytest.fixture
    def logger(self):
        """Create logger with sample events."""
        return AuditLogger(tenant_id=1)

    @pytest.mark.asyncio
    async def test_generate_compliance_report(self, logger):
        """Test combined compliance report."""
        # Add some events
        await logger.log_data_access("user-001", "profile", "p-001", is_pii=True)
        await logger.log_security_event(
            AuditEventType.AUTHENTICATION_SUCCESS,
            "user-001",
            {},
        )

        report = await logger.generate_compliance_report(
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
            include_gdpr=True,
            include_soc2=True,
        )

        assert isinstance(report, ComplianceReport)
        assert report.report_id.startswith("COMP-")
        assert report.gdpr_report is not None
        assert report.soc2_report is not None
        assert 0 <= report.compliance_score <= 100

    @pytest.mark.asyncio
    async def test_compliance_score_penalties(self, logger):
        """Test that compliance score reflects issues."""
        # Add many PII accesses (should reduce score)
        for i in range(200):
            await logger.log_data_access(
                f"user-{i}",
                "profile",
                f"p-{i}",
                is_pii=True,
                purpose="testing",
            )

        # Add many auth failures (should reduce score)
        for i in range(20):
            await logger.log_security_event(
                AuditEventType.AUTHENTICATION_FAILURE,
                f"user-{i}",
                {},
            )

        report = await logger.generate_compliance_report(
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
        )

        # Score should be penalized for high PII access and auth failures
        assert report.compliance_score < 100
        assert len(report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_export_to_json(self, logger):
        """Test JSON export."""
        await logger.log_contract_event(
            AuditEventType.CONTRACT_PROPOSED,
            "c-001",
            "agent-001",
            {"prana_cost": 50},
        )

        json_str = logger.export_to_json()
        data = json.loads(json_str)

        assert data["tenant_id"] == 1
        assert data["event_count"] == 1
        assert len(data["events"]) == 1


class TestAuditLoggerStatistics:
    """Test audit logger statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test statistics generation."""
        logger = AuditLogger(tenant_id=1)

        for i in range(5):
            await logger.log_contract_event(
                AuditEventType.CONTRACT_PROPOSED,
                f"c-{i}",
                f"agent-{i}",
                {},
            )

        stats = logger.get_statistics()

        assert stats["tenant_id"] == 1
        assert stats["total_events"] == 5
        assert stats["unique_actors"] == 5
        assert stats["integrity_verified"] is True
