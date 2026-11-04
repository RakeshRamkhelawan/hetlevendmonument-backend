"""
TDD RED PHASE: Audit Logging for Token Revocations

Tests for logging all token revocation events for compliance/security auditing.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuditLoggingRedPhase:
    """TDD RED PHASE: Audit logging for token revocations"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis = AsyncMock()
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=0)
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service"""
        return AsyncMock()

    @pytest.fixture
    def blacklist_with_audit(self, mock_redis, mock_audit_service):
        """TokenBlacklist with audit logging"""
        from src.core.auth.token_blacklist import TokenBlacklist

        blacklist = TokenBlacklist(mock_redis)
        blacklist.audit_service = mock_audit_service
        return blacklist

    @pytest.mark.asyncio
    async def test_token_revocation_logged_to_audit(self, blacklist_with_audit, mock_audit_service):
        """RED: Token revocation should be logged to audit trail"""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_test_token"
        expires_in = 1800
        user_id = 42

        # Revoke token
        await blacklist_with_audit.revoke_token(token, expires_in, user_id=user_id)

        # Should call audit service
        mock_audit_service.log_security_event.assert_called_once()
        call_args = mock_audit_service.log_security_event.call_args

        # Verify audit event details
        event_type = call_args[1].get("event_type")
        assert event_type == "token_revoked"
        assert call_args[1].get("user_id") == user_id
        assert "token_fingerprint" in call_args[1]

    @pytest.mark.asyncio
    async def test_bulk_revocation_logged_with_count(
        self, blacklist_with_audit, mock_audit_service
    ):
        """RED: Bulk user token revocation should log count"""
        user_id = 123
        token_count = 5

        # Mock scan to return multiple tokens
        blacklist_with_audit.redis.scan = AsyncMock(
            return_value=(0, [f"token_{i}".encode() for i in range(token_count)])
        )

        # Revoke all
        await blacklist_with_audit.revoke_all_user_tokens(user_id)

        # Should log with count
        mock_audit_service.log_security_event.assert_called()
        call_args = mock_audit_service.log_security_event.call_args

        assert call_args[1].get("event_type") == "bulk_token_revocation"
        assert call_args[1].get("tokens_revoked") == token_count
        assert call_args[1].get("target_user_id") == user_id

    @pytest.mark.asyncio
    async def test_logout_event_includes_timestamp(self, blacklist_with_audit, mock_audit_service):
        """RED: Logout events should include precise timestamp"""
        token = "test_token_123"

        await blacklist_with_audit.revoke_token(token, 1800, user_id=10)

        # Check audit event has timestamp
        call_args = mock_audit_service.log_security_event.call_args
        assert "timestamp" in call_args[1]
        assert isinstance(call_args[1]["timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_admin_revocation_marked_differently(
        self, blacklist_with_audit, mock_audit_service
    ):
        """RED: Admin revocations should have different audit level"""
        user_id = 99
        admin_id = 1

        # Mock redis.scan to return some keys
        blacklist_with_audit.redis.scan = AsyncMock(
            return_value=(0, [b"token_key1", b"token_key2"])
        )

        await blacklist_with_audit.revoke_all_user_tokens(user_id, revoked_by=admin_id)

        # Should mark as admin action
        call_args = mock_audit_service.log_security_event.call_args
        assert call_args[1].get("revoked_by") == admin_id
        assert call_args[1].get("is_admin_action") is True

    @pytest.mark.asyncio
    async def test_audit_logging_doesnt_block_revocation(
        self, blacklist_with_audit, mock_audit_service
    ):
        """RED: Audit logging failure should NOT prevent token revocation"""
        mock_audit_service.log_security_event.side_effect = Exception("Audit service down")

        token = "test_token_456"

        # Should still revoke token even if audit fails
        result = await blacklist_with_audit.revoke_token(token, 1800, user_id=10)

        # Token still revoked (fail-open pattern)
        assert result is True

        # But error logged
        assert mock_audit_service.log_security_event.called


class TestAuditEventTypes:
    """TDD RED PHASE: Audit event types and details"""

    @pytest.fixture
    def mock_redis_local(self):
        """Create local Redis mock with proper methods"""
        redis = AsyncMock()
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=0)
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    @pytest.mark.asyncio
    async def test_audit_event_contains_ip_address(self, mock_redis_local):
        """RED: Audit event should track IP address of logout"""
        from src.core.auth.token_blacklist import TokenBlacklist

        blacklist = TokenBlacklist(mock_redis_local)
        mock_audit = AsyncMock()
        blacklist.audit_service = mock_audit

        client_ip = "192.168.1.100"
        await blacklist.revoke_token("token", 1800, user_id=5, client_ip=client_ip)

        # Verify audit was called with client_ip
        mock_audit.log_security_event.assert_called_once()
        call_args = mock_audit.log_security_event.call_args
        assert call_args[1].get("client_ip") == client_ip

    @pytest.mark.asyncio
    async def test_audit_stores_token_fingerprint(self, mock_redis_local):
        """RED: Store token fingerprint (not full token) for audit"""
        from src.core.auth.token_blacklist import TokenBlacklist

        blacklist = TokenBlacklist(mock_redis_local)
        mock_audit = AsyncMock()
        blacklist.audit_service = mock_audit

        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.very_long_token_payload.signature"

        await blacklist.revoke_token(token, 1800, user_id=7)

        # Should store fingerprint, not full token
        mock_audit.log_security_event.assert_called_once()
        call_args = mock_audit.log_security_event.call_args
        logged_token = call_args[1].get("token_fingerprint")

        # Fingerprint should be shorter and contain "..."
        assert len(logged_token) < len(token)  # Should be shortened
        assert "..." in logged_token  # Should have ellipsis
