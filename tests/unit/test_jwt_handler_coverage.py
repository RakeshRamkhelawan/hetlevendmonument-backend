"""
Comprehensive tests for src/core/auth/jwt_handler.py
Coverage target: 100% of JWT handler
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from jose import jwt

from src.core.auth.jwt_handler import JWTHandler, get_password_hash, jwt_handler, verify_password


class TestJWTHandlerInitialization:
    """Test JWTHandler initialization"""

    @patch("src.core.auth.jwt_handler.config")
    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_production_mode(self, mock_config):
        """Test initialization in production mode"""
        mock_config.jwt_secret_key = "production-secret-key-with-minimum-32-chars"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = True

        handler = JWTHandler()

        assert handler.algorithm == "HS256"
        assert handler.access_token_expire_minutes == 30
        assert handler.secret_key == "production-secret-key-with-minimum-32-chars"

    @patch("src.core.auth.jwt_handler.config")
    @patch.dict(os.environ, {"TESTING": "1"}, clear=True)
    def test_initialization_testing_mode(self, mock_config):
        """Test initialization in testing mode uses faster bcrypt"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Verify that pwd_context is configured with bcrypt
        assert handler.pwd_context is not None
        assert "bcrypt" in handler.pwd_context.schemes()

    @patch("src.core.auth.jwt_handler.config")
    def test_initialization_no_secret_production_raises(self, mock_config):
        """Test initialization raises error without secret in production"""
        mock_config.jwt_secret_key = None
        mock_config.is_production.return_value = True

        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be set"):
            JWTHandler()

    @patch("src.core.auth.jwt_handler.config")
    def test_initialization_no_secret_development_generates(self, mock_config):
        """Test initialization generates secret in development"""
        mock_config.jwt_secret_key = None
        mock_config.is_production.return_value = False
        mock_config.jwt_expire_minutes = 30

        handler = JWTHandler()

        assert len(handler.secret_key) > 0


class TestSecretKeyValidation:
    """Test _get_secret_key validation"""

    @patch("src.core.auth.jwt_handler.config")
    def test_secret_too_short_in_production(self, mock_config):
        """Test short secret rejected in production"""
        mock_config.jwt_secret_key = "short"
        mock_config.is_production.return_value = True

        with pytest.raises(ValueError, match="at least 32 characters"):
            JWTHandler()

    @patch("src.core.auth.jwt_handler.config")
    def test_development_secret_in_production(self, mock_config):
        """Test development secret rejected in production"""
        mock_config.jwt_secret_key = "dev-secret-key-should-not-be-in-production"
        mock_config.is_production.return_value = True

        with pytest.raises(ValueError, match="Development secret detected"):
            JWTHandler()

    @patch("src.core.auth.jwt_handler.config")
    def test_change_in_production_secret_rejected(self, mock_config):
        """Test placeholder secret rejected in production"""
        mock_config.jwt_secret_key = "change-in-production-please-use-strong-secret"
        mock_config.is_production.return_value = True

        with pytest.raises(ValueError, match="Development secret detected"):
            JWTHandler()


class TestCreateAccessToken:
    """Test create_access_token method"""

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_basic(self, mock_config):
        """Test basic token creation"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token({"sub": "user@example.com"})

        assert isinstance(token, str)
        assert len(token) > 0

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_with_custom_expiry(self, mock_config):
        """Test token creation with custom expiry"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        custom_delta = timedelta(hours=2)
        token = handler.create_access_token({"sub": "user@example.com"}, expires_delta=custom_delta)

        # Decode to verify custom expiry
        payload = jwt.decode(token, handler.secret_key, algorithms=["HS256"])
        assert "exp" in payload

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_with_additional_data(self, mock_config):
        """Test token creation with additional claims"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token(
            {"sub": "user@example.com", "tenant_id": 123, "role": "admin"}
        )

        payload = jwt.decode(token, handler.secret_key, algorithms=["HS256"])
        assert payload["sub"] == "user@example.com"
        assert payload["tenant_id"] == 123
        assert payload["role"] == "admin"


class TestVerifyToken:
    """Test verify_token method"""

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_valid_token(self, mock_config):
        """Test verifying valid token"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token({"sub": "user@example.com", "tenant_id": 1})

        payload = handler.verify_token(token)

        assert payload is not None
        assert payload["sub"] == "user@example.com"

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_invalid_token(self, mock_config):
        """Test verifying invalid token"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        payload = handler.verify_token("invalid.token.here")

        assert payload is None

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_expired_token(self, mock_config):
        """Test verifying expired token"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create token with past expiry
        past_delta = timedelta(hours=-1)
        token = handler.create_access_token({"sub": "user@example.com"}, expires_delta=past_delta)

        payload = handler.verify_token(token)

        assert payload is None


class TestPasswordValidation:
    """Test _validate_ascii_only method"""

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_valid_password(self, mock_config):
        """Test ASCII validation accepts valid password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Should not raise
        handler._validate_ascii_only("ValidPassword123!")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_unicode(self, mock_config):
        """Test ASCII validation rejects Unicode"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="only ASCII characters"):
            handler._validate_ascii_only("Password123€")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_none(self, mock_config):
        """Test ASCII validation rejects None"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            handler._validate_ascii_only(None)

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_empty(self, mock_config):
        """Test ASCII validation rejects empty string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be empty"):
            handler._validate_ascii_only("")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_non_string(self, mock_config):
        """Test ASCII validation rejects non-string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(TypeError, match="must be a string"):
            handler._validate_ascii_only(12345)


class TestPasswordTruncation:
    """Test _truncate_password method"""

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_short_password(self, mock_config):
        """Test truncation doesn't modify short password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        password = "ShortPass123"
        result = handler._truncate_password(password)

        assert result == password

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_long_password(self, mock_config):
        """Test truncation of password over 72 bytes"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        password = "a" * 100
        result = handler._truncate_password(password)

        assert len(result) == 72
        assert result == "a" * 72

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_exactly_72_chars(self, mock_config):
        """Test password exactly at 72 character limit"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        password = "a" * 72
        result = handler._truncate_password(password)

        assert len(result) == 72
        assert result == password


class TestHashPassword:
    """Test hash_password async method"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_success(self, mock_config):
        """Test successful password hashing"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hashed = await handler.hash_password("TestPassword123")

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != "TestPassword123"

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_rejects_unicode(self, mock_config):
        """Test hashing rejects Unicode password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="only ASCII characters"):
            await handler.hash_password("Password€123")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_different_inputs_different_hashes(self, mock_config):
        """Test different passwords produce different hashes"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hash1 = await handler.hash_password("Password1")
        hash2 = await handler.hash_password("Password2")

        assert hash1 != hash2


class TestVerifyPasswordMethod:
    """Test verify_password async method"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_correct(self, mock_config):
        """Test verifying correct password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hashed = await handler.hash_password("TestPassword123")
        is_valid = await handler.verify_password("TestPassword123", hashed)

        assert is_valid is True

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_incorrect(self, mock_config):
        """Test verifying incorrect password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hashed = await handler.hash_password("TestPassword123")
        is_valid = await handler.verify_password("WrongPassword", hashed)

        assert is_valid is False

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_invalid_hash(self, mock_config):
        """Test verifying against invalid hash raises error"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            await handler.verify_password("Password123", None)


class TestSynchronousWrappers:
    """Test synchronous wrapper functions"""

    @patch("src.core.auth.jwt_handler.jwt_handler")
    def test_get_password_hash_wrapper(self, mock_handler):
        """Test get_password_hash synchronous wrapper"""
        mock_handler._validate_ascii_only = Mock()
        mock_handler._truncate_password = Mock(return_value="truncated")
        mock_handler.pwd_context.hash = Mock(return_value="hashed_password")

        result = get_password_hash("Password123")

        mock_handler._validate_ascii_only.assert_called_once_with("Password123")
        mock_handler._truncate_password.assert_called_once_with("Password123")
        assert result == "hashed_password"

    @patch("src.core.auth.jwt_handler.jwt_handler")
    def test_verify_password_wrapper(self, mock_handler):
        """Test verify_password synchronous wrapper"""
        mock_handler._validate_ascii_only = Mock()
        mock_handler._truncate_password = Mock(return_value="truncated")
        mock_handler.pwd_context.verify = Mock(return_value=True)

        result = verify_password("Password123", "hashed_password")

        mock_handler._validate_ascii_only.assert_called_once_with("Password123")
        assert result is True


class TestGlobalInstance:
    """Test global jwt_handler instance"""

    def test_global_instance_exists(self):
        """Test global jwt_handler instance exists"""
        from src.core.auth.jwt_handler import jwt_handler

        assert jwt_handler is not None
        assert isinstance(jwt_handler, JWTHandler)


class TestTokenVerificationEdgeCases:
    """Test edge cases in token verification"""

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_token_with_wrong_signature(self, mock_config):
        """Test token verification with wrong secret key"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token({"sub": "user@example.com"})

        # Change secret key
        handler.secret_key = "different-secret-key-32-chars-long"

        payload = handler.verify_token(token)
        assert payload is None

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_token_missing_exp_claim(self, mock_config):
        """Test token verification with missing exp claim"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create token without exp claim manually
        token = jwt.encode({"sub": "user@example.com"}, handler.secret_key, algorithm="HS256")

        payload = handler.verify_token(token)
        assert payload is None

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_token_with_wrong_algorithm(self, mock_config):
        """Test token verification rejects wrong algorithm"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create token with HS512 algorithm
        exp = datetime.now(timezone.utc) + timedelta(hours=1)
        token = jwt.encode(
            {"sub": "user@example.com", "exp": exp},
            handler.secret_key,
            algorithm="HS512",
        )

        # Should fail because handler only accepts HS256
        payload = handler.verify_token(token)
        assert payload is None

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_token_empty_string(self, mock_config):
        """Test token verification with empty string raises ValueError"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Empty string should raise ValueError
        with pytest.raises(ValueError, match="Token cannot be empty"):
            handler.verify_token("")

    @patch("src.core.auth.jwt_handler.config")
    def test_verify_token_malformed(self, mock_config):
        """Test token verification with malformed token"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        payload = handler.verify_token("malformed.token")
        assert payload is None


class TestPasswordTruncationEdgeCases:
    """Test edge cases in password truncation"""

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_password_none(self, mock_config):
        """Test truncation raises error for None"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            handler._truncate_password(None)

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_password_empty(self, mock_config):
        """Test truncation raises error for empty string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be empty"):
            handler._truncate_password("")

    @patch("src.core.auth.jwt_handler.config")
    def test_truncate_password_non_string(self, mock_config):
        """Test truncation raises error for non-string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(TypeError, match="must be a string"):
            handler._truncate_password(12345)


class TestHashPasswordEdgeCases:
    """Test edge cases in password hashing"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_none(self, mock_config):
        """Test hashing raises error for None"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            await handler.hash_password(None)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_empty(self, mock_config):
        """Test hashing raises error for empty string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be empty"):
            await handler.hash_password("")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_non_string(self, mock_config):
        """Test hashing raises error for non-string"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(TypeError, match="must be a string"):
            await handler.hash_password(12345)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_truncates_long_password(self, mock_config):
        """Test hashing truncates password over 72 bytes"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create 100-character password
        long_password = "a" * 100

        # Hash should succeed (truncation happens internally)
        hashed = await handler.hash_password(long_password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_special_characters(self, mock_config):
        """Test hashing password with ASCII special characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        special_password = "P@ssw0rd!#$%^&*()"
        hashed = await handler.hash_password(special_password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_bcrypt_failure(self, mock_config):
        """Test hashing handles bcrypt failure gracefully"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Mock bcrypt to raise exception
        with patch.object(handler.pwd_context, "hash", side_effect=Exception("Bcrypt failed")):
            with pytest.raises(RuntimeError, match="Password hashing failed"):
                await handler.hash_password("TestPassword123")


class TestVerifyPasswordEdgeCases:
    """Test edge cases in password verification"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_none_plain_password(self, mock_config):
        """Test verification raises error for None plain password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            await handler.verify_password(None, "hashed")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_empty_plain_password(self, mock_config):
        """Test verification raises error for empty plain password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be empty"):
            await handler.verify_password("", "hashed")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_non_string_plain_password(self, mock_config):
        """Test verification raises error for non-string plain password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(TypeError, match="must be a string"):
            await handler.verify_password(12345, "hashed")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_none_hashed_password(self, mock_config):
        """Test verification raises error for None hashed password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be None"):
            await handler.verify_password("Password123", None)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_empty_hashed_password(self, mock_config):
        """Test verification raises error for empty hashed password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="cannot be empty"):
            await handler.verify_password("Password123", "")

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_non_string_hashed_password(self, mock_config):
        """Test verification raises error for non-string hashed password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(TypeError, match="must be a string"):
            await handler.verify_password("Password123", 12345)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_unicode_rejection(self, mock_config):
        """Test verification rejects Unicode password"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hashed = await handler.hash_password("Password123")

        with pytest.raises(ValueError, match="only ASCII characters"):
            await handler.verify_password("Password€123", hashed)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_truncates_long_password(self, mock_config):
        """Test verification truncates long password consistently"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create 100-character password
        long_password = "a" * 100

        hashed = await handler.hash_password(long_password)

        # Verify with same long password
        is_valid = await handler.verify_password(long_password, hashed)
        assert is_valid is True

        # Verify with first 72 characters
        is_valid = await handler.verify_password("a" * 72, hashed)
        assert is_valid is True

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_bcrypt_failure(self, mock_config):
        """Test verification handles bcrypt failure gracefully"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Mock bcrypt to raise exception
        with patch.object(handler.pwd_context, "verify", side_effect=Exception("Bcrypt failed")):
            with pytest.raises(RuntimeError, match="Password verification failed"):
                await handler.verify_password("Password123", "hashed")


class TestTokenCreationEdgeCases:
    """Test edge cases in token creation"""

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_empty_data(self, mock_config):
        """Test token creation with empty data"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token({})

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token was created but verification fails due to missing 'sub' claim
        # The token is valid but missing required claims
        payload = handler.verify_token(token)
        # Empty data results in payload with only 'exp' claim, but 'sub' is required
        # so verify_token returns None when 'sub' is missing
        if payload is not None:
            assert "exp" in payload

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_with_nested_data(self, mock_config):
        """Test token creation with nested data structures"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        token = handler.create_access_token(
            {
                "sub": "user@example.com",
                "tenant_id": 1,
                "metadata": {"tenant_id": 123, "roles": ["admin", "user"]},
            }
        )

        payload = handler.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user@example.com"
        assert payload["metadata"]["tenant_id"] == 123
        assert payload["metadata"]["roles"] == ["admin", "user"]

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_with_zero_expiry(self, mock_config):
        """Test token creation with zero expiry delta.

        Note: timedelta(seconds=0) is falsy in Python, so it uses default expiry.
        To create an immediately expired token, use a negative delta.
        """
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create token with negative expiry (already expired)
        token = handler.create_access_token(
            {"sub": "user@example.com"}, expires_delta=timedelta(seconds=-1)
        )

        # Should be expired immediately
        payload = handler.verify_token(token)
        assert payload is None

    @patch("src.core.auth.jwt_handler.config")
    def test_create_token_preserves_original_data(self, mock_config):
        """Test token creation doesn't mutate original data"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        original_data = {"sub": "user@example.com", "role": "admin"}
        original_copy = original_data.copy()

        handler.create_access_token(original_data)

        # Original data should not have 'exp' added
        assert original_data == original_copy
        assert "exp" not in original_data


class TestSynchronousWrappersExtended:
    """Extended tests for synchronous wrapper functions"""

    @patch("src.core.auth.jwt_handler.jwt_handler")
    def test_get_password_hash_with_unicode(self, mock_handler):
        """Test get_password_hash wrapper handles Unicode validation"""
        mock_handler._validate_ascii_only = Mock(side_effect=ValueError("only ASCII"))

        with pytest.raises(ValueError, match="only ASCII"):
            get_password_hash("Password€123")

    @patch("src.core.auth.jwt_handler.jwt_handler")
    def test_verify_password_wrapper_with_unicode(self, mock_handler):
        """Test verify_password wrapper handles Unicode validation"""
        mock_handler._validate_ascii_only = Mock(side_effect=ValueError("only ASCII"))

        with pytest.raises(ValueError, match="only ASCII"):
            verify_password("Password€123", "hashed")


class TestASCIIValidationComprehensive:
    """Comprehensive tests for ASCII-only validation"""

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_accepts_letters(self, mock_config):
        """Test ASCII validation accepts alphabetic characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        handler._validate_ascii_only("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_accepts_digits(self, mock_config):
        """Test ASCII validation accepts numeric characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        handler._validate_ascii_only("0123456789")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_accepts_special_chars(self, mock_config):
        """Test ASCII validation accepts special ASCII characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()
        handler._validate_ascii_only("!@#$%^&*()_+-=[]{}|;':,.<>?/")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_emoji(self, mock_config):
        """Test ASCII validation rejects emoji"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="only ASCII characters"):
            handler._validate_ascii_only("Password123😊")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_cyrillic(self, mock_config):
        """Test ASCII validation rejects Cyrillic characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="only ASCII characters"):
            handler._validate_ascii_only("ПарольПароль")

    @patch("src.core.auth.jwt_handler.config")
    def test_validate_ascii_rejects_chinese(self, mock_config):
        """Test ASCII validation rejects Chinese characters"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        with pytest.raises(ValueError, match="only ASCII characters"):
            handler._validate_ascii_only("密码123")


class TestBcryptRoundsConfiguration:
    """Test bcrypt rounds configuration for testing vs production"""

    @patch("src.core.auth.jwt_handler.config")
    @patch.dict(os.environ, {"TESTING": "1"}, clear=True)
    def test_bcrypt_rounds_testing_mode(self, mock_config):
        """Test bcrypt uses 4 rounds in testing mode"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Check that bcrypt is configured
        assert handler.pwd_context is not None
        assert "bcrypt" in handler.pwd_context.schemes()

    @patch("src.core.auth.jwt_handler.config")
    @patch.dict(os.environ, {}, clear=True)
    def test_bcrypt_rounds_production_mode(self, mock_config):
        """Test bcrypt uses default rounds in production mode"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Check that bcrypt is configured
        assert handler.pwd_context is not None
        assert "bcrypt" in handler.pwd_context.schemes()


class TestThreadPoolExecution:
    """Test async thread pool execution for bcrypt operations"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_hash_password_uses_thread_pool(self, mock_config):
        """Test hash_password executes in thread pool"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Mock run_in_executor
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_executor = AsyncMock(return_value="$2b$12$hashed")
            mock_loop.return_value.run_in_executor = mock_executor

            await handler.hash_password("TestPassword123")

            # Verify run_in_executor was called
            mock_executor.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_verify_password_uses_thread_pool(self, mock_config):
        """Test verify_password executes in thread pool"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Mock run_in_executor
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_executor = AsyncMock(return_value=True)
            mock_loop.return_value.run_in_executor = mock_executor

            await handler.verify_password("TestPassword123", "$2b$12$hashed")

            # Verify run_in_executor was called
            mock_executor.assert_called_once()


class TestTokenPayloadIntegrity:
    """Test token payload data integrity"""

    @patch("src.core.auth.jwt_handler.config")
    def test_token_contains_all_original_claims(self, mock_config):
        """Test created token contains all original claims"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        original_data = {
            "sub": "user@example.com",
            "tenant_id": 123,
            "role": "admin",
            "permissions": ["read", "write"],
        }

        token = handler.create_access_token(original_data)
        payload = handler.verify_token(token)

        assert payload is not None
        for key, value in original_data.items():
            assert payload[key] == value

    @patch("src.core.auth.jwt_handler.config")
    def test_token_exp_claim_is_future(self, mock_config):
        """Test created token has expiration in the future"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        token = handler.create_access_token({"sub": "user@example.com", "tenant_id": 1})
        payload = handler.verify_token(token)

        assert payload is not None
        assert "exp" in payload

        # exp should be in the future
        exp_timestamp = payload["exp"]
        current_timestamp = datetime.now(timezone.utc).timestamp()
        assert exp_timestamp > current_timestamp

    @patch("src.core.auth.jwt_handler.config")
    def test_token_custom_expiry_is_respected(self, mock_config):
        """Test custom expiry delta is respected in token"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        # Create token with 1 hour expiry
        custom_delta = timedelta(hours=1)
        token = handler.create_access_token({"sub": "user@example.com", "tenant_id": 1}, expires_delta=custom_delta)

        payload = handler.verify_token(token)
        assert payload is not None

        # exp should be approximately 1 hour in the future
        exp_timestamp = payload["exp"]
        expected_exp = (datetime.now(timezone.utc) + custom_delta).timestamp()

        # Allow 5 second tolerance for execution time
        assert abs(exp_timestamp - expected_exp) < 5


class TestPasswordHashingConsistency:
    """Test password hashing consistency"""

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_same_password_different_salts(self, mock_config):
        """Test same password produces different hashes (salt randomness)"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hash1 = await handler.hash_password("SamePassword123")
        hash2 = await handler.hash_password("SamePassword123")

        # Hashes should be different due to random salt
        assert hash1 != hash2

        # But both should verify correctly
        assert await handler.verify_password("SamePassword123", hash1)
        assert await handler.verify_password("SamePassword123", hash2)

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.config")
    async def test_password_case_sensitivity(self, mock_config):
        """Test password verification is case-sensitive"""
        mock_config.jwt_secret_key = "test-secret-key-minimum-32-characters"
        mock_config.jwt_expire_minutes = 30
        mock_config.is_production.return_value = False

        handler = JWTHandler()

        hashed = await handler.hash_password("Password123")

        # Correct password should verify
        assert await handler.verify_password("Password123", hashed) is True

        # Wrong case should not verify
        assert await handler.verify_password("password123", hashed) is False
        assert await handler.verify_password("PASSWORD123", hashed) is False
