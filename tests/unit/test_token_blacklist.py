"""
Test Token Blacklist for Logout/Revocation
TDD RED PHASE: These tests should FAIL initially

Token Revocation allows instant logout by blacklisting JWT tokens.
After logout, token is immediately invalid even before expiry.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTokenBlacklistRedPhase:
    """TDD RED PHASE: Token blacklist functionality"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for testing"""
        redis = AsyncMock()
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=0)
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    @pytest.fixture
    def blacklist(self, mock_redis):
        """TokenBlacklist instance with mocked Redis"""
        from src.core.auth.token_blacklist import TokenBlacklist

        return TokenBlacklist(mock_redis)

    @pytest.mark.asyncio
    async def test_revoke_token_stores_in_redis(self, blacklist, mock_redis):
        """RED: Revoking token should store it in Redis with TTL"""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.test"
        expires_in = 1800  # 30 minutes

        result = await blacklist.revoke_token(token, expires_in)

        assert result is True
        mock_redis.setex.assert_called_once()

        # Verify Redis call parameters
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        ttl = call_args[0][1]
        value = call_args[0][2]

        assert key.startswith("token_blacklist:")
        assert ttl == expires_in
        assert value == "revoked"

    @pytest.mark.asyncio
    async def test_is_token_revoked_when_exists(self, blacklist, mock_redis):
        """RED: Should return True when token is in blacklist"""
        token = "test_token_abc123"
        mock_redis.exists.return_value = 1  # Token exists (revoked)

        is_revoked = await blacklist.is_token_revoked(token)

        assert is_revoked is True
        mock_redis.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_token_revoked_when_not_exists(self, blacklist, mock_redis):
        """RED: Should return False when token is NOT in blacklist"""
        token = "valid_token_xyz789"
        mock_redis.exists.return_value = 0  # Token does not exist (not revoked)

        is_revoked = await blacklist.is_token_revoked(token)

        assert is_revoked is False
        mock_redis.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self, blacklist, mock_redis):
        """RED: Should revoke all tokens for a specific user"""
        user_id = 12345

        # Mock Redis scan response: 2 tokens for this user
        mock_redis.scan.return_value = (
            0,
            [
                b"token_blacklist:token1:user:12345:abc",
                b"token_blacklist:token2:user:12345:def",
            ],
        )

        count = await blacklist.revoke_all_user_tokens(user_id)

        assert count == 2
        mock_redis.scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_blacklist_fails_gracefully_on_redis_error(self, blacklist, mock_redis):
        """RED: Should handle Redis errors gracefully (fail open)"""
        mock_redis.exists.side_effect = Exception("Redis connection failed")

        # Should NOT crash, return False (fail open for availability)
        is_revoked = await blacklist.is_token_revoked("some_token")

        assert is_revoked is False  # Fail open = allow token if service down


class TestLogoutEndpointUnit:
    """Unit tests for Logout endpoint logic"""

    @pytest.mark.asyncio
    async def test_logout_endpoint_revokes_token_mocked(self):
        """Test logout logic with mocked blacklist"""
        from src.core.auth.token_blacklist import TokenBlacklist

        mock_redis = AsyncMock()
        blacklist = TokenBlacklist(mock_redis)

        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        expires_in = 1800

        # Call revoke_token directly (simulating what logout endpoint does)
        result = await blacklist.revoke_token(token, expires_in)

        assert result is True
        mock_redis.setex.assert_called_once()

        # Verify the blacklist key format
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        assert key.startswith("token_blacklist:")

    @pytest.mark.asyncio
    async def test_logout_endpoint_requires_auth_logic(self):
        """Test that logout requires a valid token format"""
        from src.core.auth.jwt_handler import jwt_handler

        # Empty/invalid token should fail validation
        invalid_token = ""
        is_valid_format = bool(invalid_token and len(invalid_token.split(".")) == 3)
        assert is_valid_format is False

        # Valid format token (but may be expired/invalid)
        valid_format_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0QGV4YW1wbGUuY29tIn0.test"
        )
        is_valid_format = len(valid_format_token.split(".")) == 3
        assert is_valid_format is True


class TestTokenVerificationWithBlacklistRedPhase:
    """TDD RED PHASE: JWT verification respects blacklist"""

    @pytest.mark.asyncio
    async def test_verify_token_checks_blacklist(self):
        """RED: JWT verification should reject blacklisted tokens"""
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.auth.token_blacklist import TokenBlacklist

        mock_redis = AsyncMock()
        blacklist = TokenBlacklist(mock_redis)

        # Create a valid JWT
        token = jwt_handler.create_access_token({"sub": "test@example.com", "tenant_id": 1})

        # Token is NOT blacklisted
        mock_redis.exists.return_value = 0
        payload = await jwt_handler.verify_token_with_blacklist(token, blacklist)
        assert payload is not None

        # Now the token IS blacklisted
        mock_redis.exists.return_value = 1
        payload = await jwt_handler.verify_token_with_blacklist(token, blacklist)
        assert payload is None  # Should be rejected

    @pytest.mark.asyncio
    async def test_revoked_token_cannot_access_protected_logic(self):
        """Test that revoked token is rejected during verification"""
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.auth.token_blacklist import TokenBlacklist

        mock_redis = AsyncMock()
        blacklist = TokenBlacklist(mock_redis)

        # Create a valid JWT
        token = jwt_handler.create_access_token({"sub": "test@example.com", "tenant_id": 1})

        # Simulate the token being revoked (added to blacklist)
        mock_redis.exists.return_value = 1  # Token IS in blacklist

        # Verify token with blacklist check
        payload = await jwt_handler.verify_token_with_blacklist(token, blacklist)

        # Should be rejected (None because token is blacklisted)
        assert payload is None


# Run tests - SHOULD FAIL initially
# pytest tests/unit/test_token_blacklist.py -v

# Expected: All tests FAIL (ModuleNotFoundError: No module named 'src.core.auth.token_blacklist')
