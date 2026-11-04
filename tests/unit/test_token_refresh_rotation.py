"""
TDD RED PHASE: Token Refresh with Rotation

Tests for secure token refresh with automatic rotation.
Ensures old tokens are invalidated and new tokens are issued.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import JWTError


class TestTokenRefreshRedPhase:
    """TDD RED PHASE: Token refresh with rotation"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis = AsyncMock()
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=0)
        redis.delete = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_jwt_service(self):
        """Mock JWT service"""
        service = MagicMock()
        service.verify_token = MagicMock()
        service.create_access_token = MagicMock(return_value="new_token_xyz")
        return service

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service"""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_refresh_token_returns_new_token(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: Refresh endpoint should return new token"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        old_token = "old_token_abc"
        mock_jwt_service.verify_token.return_value = {"sub": "user123", "exp": 9999999}

        result = await service.refresh_token(old_token)

        # Should return new token
        assert result == "new_token_xyz"
        mock_jwt_service.create_access_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_invalidates_old_token(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: Refresh should invalidate old token immediately"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        old_token = "old_token_abc"
        mock_jwt_service.verify_token.return_value = {"sub": "user123", "exp": 9999999}

        await service.refresh_token(old_token)

        # Old token should be blacklisted
        mock_redis.setex.assert_called_once()
        # Verify it's being blacklisted with TTL
        call_args = mock_redis.setex.call_args
        assert call_args[0][0].startswith("token_refresh_blacklist:")

    @pytest.mark.asyncio
    async def test_refresh_logs_token_rotation_event(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: Token rotation should be logged to audit"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        old_token = "old_token_abc"
        user_id = 42
        mock_jwt_service.verify_token.return_value = {
            "sub": f"user{user_id}",
            "exp": 9999999,
        }

        await service.refresh_token(old_token)

        # Should log token rotation event
        mock_audit_service.log_security_event.assert_called()
        call_args = mock_audit_service.log_security_event.call_args
        assert call_args[1].get("event_type") == "token_rotated"
        assert call_args[1].get("user_id") == user_id

    @pytest.mark.asyncio
    async def test_refresh_rejects_expired_token(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: Refresh should reject expired tokens"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        old_token = "expired_token"
        mock_jwt_service.verify_token.side_effect = JWTError("Token expired")

        with pytest.raises(JWTError):
            await service.refresh_token(old_token)

    @pytest.mark.asyncio
    async def test_refresh_rejects_already_refreshed_token(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: Should reject token that was already refreshed"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        token = "token_already_refreshed"

        # Token is in refresh blacklist (was refreshed before)
        mock_redis.exists = AsyncMock(return_value=1)

        with pytest.raises(ValueError, match="Token already refreshed"):
            await service.refresh_token(token)

    @pytest.mark.asyncio
    async def test_refresh_new_token_has_fresh_expiry(
        self, mock_redis, mock_jwt_service, mock_audit_service
    ):
        """RED: New token should have fresh expiry time"""
        from src.core.auth.token_refresh import TokenRefreshService

        service = TokenRefreshService(
            redis_client=mock_redis,
            jwt_service=mock_jwt_service,
            audit_service=mock_audit_service,
        )

        old_token = "old_token_abc"
        mock_jwt_service.verify_token.return_value = {"sub": "user123", "exp": 9999999}

        await service.refresh_token(old_token)

        # Should create token with fresh expiry
        mock_jwt_service.create_access_token.assert_called_once()
        call_args = mock_jwt_service.create_access_token.call_args
        # fresh flag is in the data dict (first positional arg)
        data_arg = call_args[0][0] if call_args[0] else call_args[1].get("data", {})
        assert data_arg.get("fresh") is True


class TestTokenRefreshEndpoint:
    """TDD RED PHASE: Token refresh endpoint"""

    # Waren inline `pytest.skip()`-aanroepen als eerste statement. Omgezet naar markers (ADR-036
    # OP-201): een runtime-skip is voor pytest pas bij het UITVOEREN zichtbaar, dus de ratchet in
    # `scripts/count_disabled_tests.py` -- die de verzamelde items telt -- zag ze niet.
    # Semantisch identiek: de skip was onontkoombaar, de tests deden niets anders.
    @pytest.mark.skip(reason="Integration test - implement in GREEN phase")
    @pytest.mark.asyncio
    async def test_refresh_endpoint_requires_auth(self):
        """RED: /refresh endpoint should require JWT auth"""

    @pytest.mark.skip(reason="Integration test - implement in GREEN phase")
    @pytest.mark.asyncio
    async def test_refresh_endpoint_returns_new_token_in_cookie(self):
        """RED: Endpoint should set new token in secure httponly cookie"""
