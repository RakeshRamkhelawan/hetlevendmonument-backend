"""
Unit tests for AuditService class and its methods.
Tests the core audit logging functionality with comprehensive coverage.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.core.governance.models import AuditLog
from src.core.security.security_manager import ThreatLevel
from src.core.governance.services.audit_service import (
    AuditService,
    SecurityEvent,
    log_request_audit,
    log_security_event,
)


@pytest.mark.asyncio
class TestAuditService:
    """Test suite for AuditService class"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        mock_session = AsyncMock()
        mock_session.add = Mock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.rollback = AsyncMock()
        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin_nested = MagicMock(return_value=nested_cm)
        return mock_session

    async def test_log_event_does_not_commit_outer_transaction(self, mock_db_session):
        """ADR-019: log_event must NOT commit the outer transaction.
        Uses flush() instead so callers own the commit boundary.
        """
        result = await AuditService.log_event(
            db=mock_db_session,
            event_type="AUDIT_TX_TEST",
            severity="low",
            source_ip="127.0.0.1",
            endpoint="/api/test",
            description="tx boundary test",
        )
        assert result is True
        mock_db_session.commit.assert_not_called()

    async def test_log_event_calls_flush_after_savepoint(self, mock_db_session):
        """ADR-019: log_event must call flush() to persist the savepoint without
        closing the outer transaction.
        """
        result = await AuditService.log_event(
            db=mock_db_session,
            event_type="AUDIT_FLUSH_TEST",
            severity="low",
            source_ip="127.0.0.1",
            endpoint="/api/test",
            description="flush test",
        )
        assert result is True
        mock_db_session.flush.assert_called_once()

    async def test_log_event_success(self, mock_db_session):
        """Test successful audit event logging."""
        # Arrange
        event_type = "LOGIN_SUCCESS"
        severity = ThreatLevel.LOW
        source_ip = "192.168.1.1"
        endpoint = "/api/v1/auth/login"
        description = "User logged in successfully"
        user_id = 123
        metadata = {"session_id": "abc123"}

        # Act
        result = await AuditService.log_event(
            db=mock_db_session,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            endpoint=endpoint,
            description=description,
            user_id=user_id,
            metadata=metadata,
        )

        # Assert
        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called_once()
        mock_db_session.commit.assert_not_called()

    async def test_log_event_without_optional_fields(self, mock_db_session):
        """Test audit event logging without optional user_id and metadata."""
        # Arrange
        event_type = "DATA_ACCESS"
        severity = ThreatLevel.MEDIUM
        source_ip = "192.168.1.2"
        endpoint = "/api/v1/data/users"
        description = "Accessed user data"

        # Act
        result = await AuditService.log_event(
            db=mock_db_session,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            endpoint=endpoint,
            description=description,
            # user_id and metadata are optional and omitted
        )

        # Assert
        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called_once()
        mock_db_session.commit.assert_not_called()

    async def test_log_event_with_none_metadata(self, mock_db_session):
        """Test audit event logging with explicit None metadata."""
        # Arrange
        event_type = "LOGOUT"
        severity = ThreatLevel.LOW
        source_ip = "192.168.1.3"
        endpoint = "/api/v1/auth/logout"
        description = "User logged out"
        user_id = 456
        metadata = None

        # Act
        result = await AuditService.log_event(
            db=mock_db_session,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            endpoint=endpoint,
            description=description,
            user_id=user_id,
            metadata=metadata,
        )

        # Assert
        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called_once()
        mock_db_session.commit.assert_not_called()

    async def test_log_event_handles_non_serializable_metadata(self, mock_db_session):
        """Test that non-serializable metadata is handled gracefully."""
        # Arrange
        event_type = "CONFIG_CHANGE"
        severity = ThreatLevel.MEDIUM
        source_ip = "192.168.1.4"
        endpoint = "/api/v1/admin/config"
        description = "Configuration updated"

        # Create non-serializable metadata
        class NonSerializable:
            pass

        metadata = {"bad_object": NonSerializable()}

        # Act
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            result = await AuditService.log_event(
                db=mock_db_session,
                event_type=event_type,
                severity=severity,
                source_ip=source_ip,
                endpoint=endpoint,
                description=description,
                metadata=metadata,
            )

        # Assert
        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called_once()
        mock_db_session.commit.assert_not_called()
        # Should have logged a warning about non-serializable metadata
        mock_logger.warning.assert_called_once()

    async def test_log_event_handles_database_error(self, mock_db_session):
        """Test that database errors are handled gracefully."""
        # Arrange
        mock_db_session.flush = AsyncMock(side_effect=SQLAlchemyError("Database connection failed"))

        event_type = "API_CALL"
        severity = ThreatLevel.LOW
        source_ip = "192.168.1.5"
        endpoint = "/api/v1/status"
        description = "Health check"

        # Act
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            result = await AuditService.log_event(
                db=mock_db_session,
                event_type=event_type,
                severity=severity,
                source_ip=source_ip,
                endpoint=endpoint,
                description=description,
            )

        # Assert
        assert result is False
        mock_db_session.add.assert_called_once()
        # Note: rollback is not explicitly called in the method as session management is external
        # Should have logged the database error
        mock_logger.error.assert_called_once()

    async def test_log_event_handles_runtime_error(self, mock_db_session):
        """Test that runtime errors (like uninitialized database) are handled."""
        # Arrange
        mock_db_session.add = Mock(side_effect=RuntimeError("Database not initialized"))

        event_type = "SYSTEM_EVENT"
        severity = ThreatLevel.LOW
        source_ip = "192.168.1.6"
        endpoint = "/api/v1/system"
        description = "System startup"

        # Act
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            result = await AuditService.log_event(
                db=mock_db_session,
                event_type=event_type,
                severity=severity,
                source_ip=source_ip,
                endpoint=endpoint,
                description=description,
            )

        # Assert
        assert result is False
        # Should have logged the runtime error as a warning
        mock_logger.warning.assert_called_once()

    async def test_log_event_handles_unexpected_error(self, mock_db_session):
        """Test that unexpected errors are handled gracefully."""
        # Arrange
        mock_db_session.add = Mock(side_effect=ValueError("Unexpected error"))

        event_type = "CUSTOM_EVENT"
        severity = ThreatLevel.MEDIUM
        source_ip = "192.168.1.7"
        endpoint = "/api/v1/custom"
        description = "Custom event triggered"

        # Act
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            result = await AuditService.log_event(
                db=mock_db_session,
                event_type=event_type,
                severity=severity,
                source_ip=source_ip,
                endpoint=endpoint,
                description=description,
            )

        # Assert
        assert result is False
        mock_logger.error.assert_called_once()


class TestSecurityEvent:
    """Test suite for SecurityEvent constants"""

    def test_security_event_constants(self):
        """Test that all SecurityEvent constants are properly defined."""
        assert SecurityEvent.TENANT_CONTEXT_FAILED == "tenant_context_failed"
        assert SecurityEvent.CROSS_TENANT_ATTEMPT == "cross_tenant_access_attempt"
        assert SecurityEvent.TENANT_NOT_FOUND == "tenant_not_found"
        assert SecurityEvent.TENANT_SUSPENDED == "tenant_suspended"
        assert SecurityEvent.SUPERUSER_BYPASS == "superuser_bypass"
        assert SecurityEvent.QUOTA_EXCEEDED == "quota_exceeded"
        assert SecurityEvent.INVALID_JWT == "invalid_jwt"
        assert SecurityEvent.TOKEN_EXPIRED == "token_expired"
        assert SecurityEvent.RESOURCE_NOT_FOUND_404 == "resource_not_found_404"
        assert SecurityEvent.LOGIN_SUCCESS == "LOGIN_SUCCESS"
        assert SecurityEvent.LOGIN_FAILURE == "LOGIN_FAILURE"
        assert SecurityEvent.REGISTRATION_SUCCESS == "REGISTRATION_SUCCESS"


# Integration tests with actual database
@pytest.mark.asyncio
class TestAuditServiceIntegration:
    """Integration tests for AuditService with real database session."""

    async def test_log_event_creates_database_record(self, db_session):
        """Test that log_event actually creates a record in the database."""
        # Arrange
        event_type = "INTEGRATION_TEST"
        severity = ThreatLevel.LOW
        source_ip = "127.0.0.1"
        endpoint = "/api/v1/test"
        description = "Integration test event"
        user_id = 999
        metadata = {"test": "integration"}

        # Act
        result = await AuditService.log_event(
            db=db_session,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            endpoint=endpoint,
            description=description,
            user_id=user_id,
            metadata=metadata,
        )

        # Assert
        assert result is True

        # Verify the record was actually created
        from sqlalchemy import select

        stmt = select(AuditLog).where(AuditLog.event_type == event_type)
        db_result = await db_session.execute(stmt)
        audit_log = db_result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.event_type == event_type
        assert audit_log.threat_level == severity.value
        assert audit_log.client_ip == source_ip
        assert audit_log.endpoint == endpoint
        assert audit_log.description == description
        assert audit_log.user_id == user_id
        assert audit_log.event_metadata == metadata

    async def test_multiple_log_events(self, db_session):
        """Test logging multiple events."""
        # Arrange
        events = [
            {
                "event_type": "MULTI_TEST_1",
                "severity": ThreatLevel.LOW,
                "source_ip": "127.0.0.1",
                "endpoint": "/api/v1/test1",
                "description": "First test event",
            },
            {
                "event_type": "MULTI_TEST_2",
                "severity": ThreatLevel.HIGH,
                "source_ip": "127.0.0.2",
                "endpoint": "/api/v1/test2",
                "description": "Second test event",
                "user_id": 100,
            },
        ]

        # Act & Assert
        for event_data in events:
            result = await AuditService.log_event(db=db_session, **event_data)
            assert result is True

        # Verify all records were created
        from sqlalchemy import select

        for event_data in events:
            stmt = select(AuditLog).where(AuditLog.event_type == event_data["event_type"])
            db_result = await db_session.execute(stmt)
            audit_log = db_result.scalar_one_or_none()
            assert audit_log is not None

    async def test_log_event_plain_string_severity(self, db_session):
        """Plain-string severity (ThreatLevel | str path) is stored lowercase.
        [SP-DSM-015 Dag 2 -- FA-010: coverage for Change 1 signature widening]
        """
        from sqlalchemy import select

        result = await AuditService.log_event(
            db=db_session,
            event_type="PLAIN_STRING_TEST",
            severity="high",
            source_ip="127.0.0.1",
            endpoint="/api/test",
            description="Plain string severity test",
        )
        assert result is True

        stmt = select(AuditLog).where(AuditLog.event_type == "PLAIN_STRING_TEST")
        db_result = await db_session.execute(stmt)
        audit_log = db_result.scalar_one_or_none()
        assert audit_log is not None
        assert audit_log.threat_level == "high"


# Tests for log_security_event and log_request_audit functions
@pytest.mark.asyncio
class TestLogSecurityEventFunction:
    """Test suite for log_security_event function"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        mock_session = AsyncMock()
        mock_session.add = Mock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.rollback = AsyncMock()
        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin_nested = MagicMock(return_value=nested_cm)
        return mock_session

    async def test_log_security_event_without_db(self):
        """Test log_security_event without database session."""
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.LOGIN_SUCCESS,
                user_id=123,
                details={"session": "abc123"},
            )

            # LOGIN_SUCCESS has default medium threat level, should log as WARNING
            assert mock_logger.warning.called

    async def test_log_security_event_with_db(self, mock_db_session):
        """Test log_security_event with database session."""
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.LOGIN_SUCCESS,
                user_id=123,
                details={"session": "abc123"},
                db=mock_db_session,
            )

            # LOGIN_SUCCESS has default medium threat level, should log as WARNING
            assert mock_logger.warning.called
            mock_db_session.add.assert_called_once()
            mock_db_session.flush.assert_called_once()
            mock_db_session.commit.assert_not_called()

    async def test_log_security_event_critical_level(self):
        """Test log_security_event with critical threat level."""
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.CROSS_TENANT_ATTEMPT,
                user_id=123,
                details={"target_tenant": 456},
            )

            # Critical events should log as ERROR
            assert mock_logger.error.called

    async def test_log_security_event_high_level(self):
        """Test log_security_event with high threat level."""
        with patch("src.core.governance.services.audit_service.logger") as mock_logger:
            await log_security_event(event_type=SecurityEvent.QUOTA_EXCEEDED, user_id=123)

            # High events should log as WARNING
            assert mock_logger.warning.called


@pytest.mark.asyncio
class TestLogRequestAuditFunction:
    """Test suite for log_request_audit function"""

    async def test_log_request_audit_with_explicit_fields(self):
        """Test log_request_audit with explicit request fields."""
        with patch(
            "src.core.governance.services.audit_service.log_security_event"
        ) as mock_log_security:
            await log_request_audit(
                request_path="/api/v1/test",
                request_method="GET",
                status_code=200,
                client_ip="192.168.1.1",
                user_id="user123",
            )

            # Should call log_security_event with appropriate parameters
            mock_log_security.assert_called_once()
            call_args = mock_log_security.call_args[1]
            assert call_args["event_type"] == "api_request_200"
            assert call_args["threat_level"] == "low"
            assert call_args["user_id"] is None  # "user123" is non-numeric → None
            assert call_args["ip_address"] == "192.168.1.1"

    async def test_log_request_audit_404_status(self):
        """Test log_request_audit with 404 status code."""
        with patch(
            "src.core.governance.services.audit_service.log_security_event"
        ) as mock_log_security:
            await log_request_audit(
                request_path="/api/v1/nonexistent",
                request_method="GET",
                status_code=404,
                client_ip="192.168.1.1",
            )

            # 404 should be treated as critical
            call_args = mock_log_security.call_args[1]
            assert call_args["threat_level"] == "critical"

    async def test_log_request_audit_500_status(self):
        """Test log_request_audit with 500 status code."""
        with patch(
            "src.core.governance.services.audit_service.log_security_event"
        ) as mock_log_security:
            await log_request_audit(
                request_path="/api/v1/broken",
                request_method="POST",
                status_code=500,
                client_ip="192.168.1.1",
            )

            # 500 should be treated as critical
            call_args = mock_log_security.call_args[1]
            assert call_args["threat_level"] == "critical"

    async def test_log_request_audit_401_status(self):
        """Test log_request_audit with 401 status code."""
        with patch(
            "src.core.governance.services.audit_service.log_security_event"
        ) as mock_log_security:
            await log_request_audit(
                request_path="/api/v1/protected",
                request_method="GET",
                status_code=401,
                client_ip="192.168.1.1",
            )

            # 401 should be treated as high
            call_args = mock_log_security.call_args[1]
            assert call_args["threat_level"] == "high"
