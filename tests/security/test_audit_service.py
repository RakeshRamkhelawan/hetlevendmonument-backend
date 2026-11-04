"""
Tests for Audit Service - Multi-Tenant Security Event Logging

Coverage target: 80%+
Tests audit logging, security events, and threat level mapping
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.security.security_manager import ThreatLevel
from src.core.governance.services.audit_service import (
    AuditService,
    SecurityEvent,
    log_request_audit,
    log_security_event,
)


class TestSecurityEventEnum:
    """Test SecurityEvent enum values"""

    def test_security_event_values(self):
        """All SecurityEvent values should be defined"""
        assert SecurityEvent.TENANT_CONTEXT_FAILED == "tenant_context_failed"
        assert SecurityEvent.CROSS_TENANT_ATTEMPT == "cross_tenant_access_attempt"
        assert SecurityEvent.QUOTA_EXCEEDED == "quota_exceeded"
        assert SecurityEvent.TENANT_NOT_FOUND == "tenant_not_found"
        assert SecurityEvent.TENANT_SUSPENDED == "tenant_suspended"
        assert SecurityEvent.SUPERUSER_BYPASS == "superuser_bypass"
        assert SecurityEvent.INVALID_JWT == "invalid_jwt"
        assert SecurityEvent.TOKEN_EXPIRED == "token_expired"


class TestThreatLevelEnum:
    """Test ThreatLevel enum from security_manager"""

    def test_threat_level_values(self):
        """ThreatLevel enum should have correct integer values"""
        assert ThreatLevel.LOW.value == 1
        assert ThreatLevel.MEDIUM.value == 3
        assert ThreatLevel.HIGH.value == 7
        assert ThreatLevel.CRITICAL.value == 9

    def test_threat_level_ordering(self):
        """ThreatLevel values should be ordered by severity"""
        assert ThreatLevel.LOW.value < ThreatLevel.MEDIUM.value
        assert ThreatLevel.MEDIUM.value < ThreatLevel.HIGH.value
        assert ThreatLevel.HIGH.value < ThreatLevel.CRITICAL.value


@pytest.mark.asyncio
class TestLogSecurityEvent:
    """Test log_security_event function"""

    async def test_log_without_db_session(self):
        """Should log to system logger when no db session provided"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.TENANT_CONTEXT_FAILED,
                user_id="user123",
                details={"reason": "test"},
            )

            # Should have logged to system logger
            assert mock_logger.error.called or mock_logger.warning.called or mock_logger.info.called

        clear_tenant_context()

    async def test_log_critical_event(self):
        """Critical events should log at ERROR level"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.CROSS_TENANT_ATTEMPT,
                user_id="user123",
                details={"attempted_tenant": 2},
            )

            # Critical events use ERROR level
            mock_logger.error.assert_called()

        clear_tenant_context()

    async def test_log_high_event(self):
        """High severity events should log at WARNING level"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.QUOTA_EXCEEDED,
                user_id="user123",
                details={"quota_type": "users"},
            )

            # High events use WARNING level
            mock_logger.warning.assert_called()

        clear_tenant_context()

    async def test_log_low_event(self):
        """Low severity events should log at INFO level"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.SUPERUSER_BYPASS,
                user_id="admin123",
                details={"operation": "cross_tenant_read"},
            )

            # Low events use INFO level
            mock_logger.info.assert_called()

        clear_tenant_context()

    async def test_log_with_request_info(self):
        """Should include request path and method in log"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.INVALID_JWT,
                user_id="user123",
                details={},
                request_path="/api/agents",
                request_method="GET",
            )

            # Should have logged
            assert mock_logger.error.called or mock_logger.warning.called

        clear_tenant_context()

    async def test_log_extracts_tenant_from_context(self):
        """Should extract tenant_id from context if not provided"""
        set_tenant_id(42)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.QUOTA_EXCEEDED, user_id="user123", details={}
            )

            # Should have logged
            mock_logger.warning.assert_called()

        clear_tenant_context()

    async def test_log_handles_missing_tenant_context(self):
        """Should handle missing tenant context gracefully"""
        clear_tenant_context()

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_security_event(
                event_type=SecurityEvent.INVALID_JWT, user_id="user123", details={}
            )

            # Should still log
            assert mock_logger.error.called or mock_logger.warning.called


@pytest.mark.asyncio
class TestLogRequestAudit:
    """Test log_request_audit function for suspicious requests"""

    async def test_log_suspicious_404(self):
        """Should log suspicious 404 as potential cross-tenant attempt"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/agents/999",
                request_method="GET",
                status_code=404,
                client_ip="127.0.0.1",
            )

            # Should log as ERROR (cross-tenant attempt)
            mock_logger.error.assert_called()

        clear_tenant_context()

    async def test_log_successful_request(self):
        """Should log successful requests at INFO level"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/agents",
                request_method="GET",
                status_code=200,
                client_ip="127.0.0.1",
            )

            # Should log as INFO
            mock_logger.info.assert_called()

        clear_tenant_context()

    async def test_log_403_forbidden(self):
        """Should log 403 responses"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/rbac/roles",
                request_method="GET",
                status_code=403,
                client_ip="127.0.0.1",
            )

            # Should log as WARNING
            mock_logger.warning.assert_called()

        clear_tenant_context()

    async def test_log_401_unauthorized(self):
        """Should log 401 responses"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/agents",
                request_method="GET",
                status_code=401,
                client_ip="127.0.0.1",
            )

            # Should log as WARNING
            mock_logger.warning.assert_called()

        clear_tenant_context()

    async def test_log_500_server_error(self):
        """Should log 500 errors"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/agents",
                request_method="POST",
                status_code=500,
                client_ip="127.0.0.1",
            )

            # Should log as ERROR
            mock_logger.error.assert_called()

        clear_tenant_context()

    async def test_log_with_user_agent(self):
        """Should include user agent in log details"""
        set_tenant_id(1)

        with patch("src.core.services.audit_service.logger") as mock_logger:
            await log_request_audit(
                user_id="user123",
                request_path="/api/agents",
                request_method="GET",
                status_code=200,
                client_ip="127.0.0.1",
                user_agent="Mozilla/5.0",
            )

            # Should have logged
            mock_logger.info.assert_called()

        clear_tenant_context()


class TestAuditServiceIntegration:
    """Integration tests for audit service"""

    def test_module_imports(self):
        """Audit service should export all required functions"""
        from src.core.services import audit_service

        assert hasattr(audit_service, "log_security_event")
        assert hasattr(audit_service, "log_request_audit")
        assert hasattr(audit_service, "AuditService")
        assert hasattr(audit_service, "SecurityEvent")

    def test_security_event_is_string(self):
        """SecurityEvent enum values should be strings"""
        assert isinstance(SecurityEvent.CROSS_TENANT_ATTEMPT, str)
        assert isinstance(SecurityEvent.QUOTA_EXCEEDED, str)
