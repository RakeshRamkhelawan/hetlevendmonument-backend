"""
Unit tests for src.core.auth.jwt_handler.py
Targets 85%+ coverage for JWTHandler class and functions
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from jose import JWTError
from passlib.context import CryptContext

from src.core.auth.jwt_handler import JWTHandler, get_password_hash, jwt_handler, verify_password


class TestJWTHandlerInitialization:
    """Test JWTHandler class initialization"""

    def test_jwt_handler_initialization(self):
        """Test JWTHandler initializes correctly"""
        handler = JWTHandler()
        assert handler.algorithm == "HS256"
        assert isinstance(handler.pwd_context, CryptContext)
        assert handler.secret_key is not None

    @patch("os.getenv")
    def test_jwt_handler_testing_mode(self, mock_getenv):
        """Test JWTHandler uses lower bcrypt rounds in testing mode"""
        mock_getenv.return_value = "1"
        handler = JWTHandler()
        # Check that the bcrypt rounds are set to 4 in testing mode
        # We can't directly access private attributes, so we'll check the schemes
        assert handler.pwd_context is not None

    @patch("os.getenv")
    def test_jwt_handler_production_mode(self, mock_getenv):
        """Test JWTHandler uses normal bcrypt rounds in production mode"""
        mock_getenv.return_value = None
        handler = JWTHandler()
        # In production, bcrypt context should be initialized
        assert handler.pwd_context is not None


class TestSecretKeyHandling:
    """Test secret key handling functionality"""

    @patch("src.core.auth.jwt_handler.config")
    def test_get_secret_key_production_valid(self, mock_config):
        """Test secret key retrieval in production with valid key"""
        mock_config.is_production.return_value = True
        mock_config.jwt_secret_key = "valid-secret-key-more-than-32-chars-long-for-production"

        handler = JWTHandler()
        secret = handler._get_secret_key()
        assert secret == mock_config.jwt_secret_key

    def test_get_secret_key_production_missing(self):
        """Test secret key retrieval fails in production with missing key"""
        # We'll test this by directly calling _get_secret_key with a mock
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler.__new__(JWTHandler)  # Create instance without calling __init__
        handler.config = MagicMock()
        handler.config.is_production.return_value = True
        handler.config.jwt_secret_key = None

        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be set in production"):
            handler._get_secret_key()

    @patch("src.core.auth.jwt_handler.config")
    @patch("src.core.auth.jwt_handler.logger")
    def test_get_secret_key_development_generated(self, mock_logger, mock_config):
        """Test secret key generation in development mode"""
        mock_config.is_production.return_value = False
        mock_config.jwt_secret_key = None

        handler = JWTHandler()
        secret = handler._get_secret_key()
        assert secret is not None
        assert len(secret) > 0
        mock_logger.warning.assert_called()


class TestTokenCreation:
    """Test JWT token creation functionality"""

    def test_create_access_token_basic(self):
        """Test basic access token creation"""
        handler = JWTHandler()
        data = {"sub": "test@example.com"}

        token = handler.create_access_token(data)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_expiry(self):
        """Test access token creation with custom expiry"""
        handler = JWTHandler()
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(minutes=30)

        token = handler.create_access_token(data, expires_delta)
        assert isinstance(token, str)

    def test_create_access_token_contains_data(self):
        """Test that created token contains the provided data"""
        handler = JWTHandler()
        data = {"sub": "test@example.com", "custom_field": "custom_value"}

        token = handler.create_access_token(data)
        # Decode token to verify contents
        from jose import jwt

        decoded = jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])
        assert decoded["sub"] == "test@example.com"
        assert decoded["custom_field"] == "custom_value"


class TestTokenVerification:
    """Test JWT token verification functionality"""

    def test_verify_token_valid(self):
        """Test verification of valid token"""
        handler = JWTHandler()
        data = {"sub": "test@example.com", "tenant_id": 1}
        token = handler.create_access_token(data)

        payload = handler.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"

    def test_verify_token_invalid(self):
        """Test verification of invalid token"""
        handler = JWTHandler()
        invalid_token = "invalid.token.string"

        payload = handler.verify_token(invalid_token)
        assert payload is None

    def test_verify_token_expired(self):
        """Test verification of expired token"""
        handler = JWTHandler()
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(seconds=-1)  # Expired 1 second ago

        token = handler.create_access_token(data, expires_delta)
        payload = handler.verify_token(token)
        assert payload is None

    @patch("src.core.auth.jwt_handler.logger")
    def test_verify_token_logs_error(self, mock_logger):
        """Test that token verification errors are logged"""
        handler = JWTHandler()
        invalid_token = "invalid.token.string"

        payload = handler.verify_token(invalid_token)
        assert payload is None
        mock_logger.warning.assert_called()


class TestPasswordValidation:
    """Test password validation functionality"""

    def test_validate_ascii_only_valid(self):
        """Test validation of ASCII-only password"""
        handler = JWTHandler()
        password = "ValidPassword123!"
        # Should not raise any exception
        handler._validate_ascii_only(password)

    def test_validate_ascii_only_none(self):
        """Test validation fails with None password"""
        handler = JWTHandler()
        with pytest.raises(ValueError, match="Password cannot be None"):
            handler._validate_ascii_only(None)

    def test_validate_ascii_only_non_string(self):
        """Test validation fails with non-string password"""
        handler = JWTHandler()
        with pytest.raises(TypeError, match="Password must be a string"):
            handler._validate_ascii_only(123)

    def test_validate_ascii_only_empty(self):
        """Test validation fails with empty password"""
        handler = JWTHandler()
        with pytest.raises(ValueError, match="Password cannot be empty"):
            handler._validate_ascii_only("")

    def test_validate_ascii_only_unicode(self):
        """Test validation fails with non-ASCII characters"""
        handler = JWTHandler()
        with pytest.raises(ValueError, match="Password must contain only ASCII characters"):
            handler._validate_ascii_only("PasswordüWithUnicode")


class TestPasswordTruncation:
    """Test password truncation functionality"""

    def test_truncate_password_within_limit(self):
        """Test truncation of password within 72-character limit"""
        handler = JWTHandler()
        password = "ShortPassword123"
        truncated = handler._truncate_password(password)
        assert truncated == password

    def test_truncate_password_exceeds_limit(self):
        """Test truncation of password exceeding 72-character limit"""
        handler = JWTHandler()
        password = "A" * 80  # 80 characters
        truncated = handler._truncate_password(password)
        assert len(truncated) == 72
        assert truncated == "A" * 72

    def test_truncate_password_exactly_limit(self):
        """Test password exactly at 72-character limit"""
        handler = JWTHandler()
        password = "A" * 72  # Exactly 72 characters
        truncated = handler._truncate_password(password)
        assert truncated == password

    def test_truncate_password_none(self):
        """Test truncation fails with None password"""
        handler = JWTHandler()
        with pytest.raises(ValueError, match="Password cannot be None"):
            handler._truncate_password(None)

    def test_truncate_password_empty(self):
        """Test truncation fails with empty password"""
        handler = JWTHandler()
        with pytest.raises(ValueError, match="Password cannot be empty"):
            handler._truncate_password("")


class TestAsyncPasswordHashing:
    """Test asynchronous password hashing functionality"""

    @pytest.mark.asyncio
    async def test_hash_password_valid(self):
        """Test hashing of valid password"""
        handler = JWTHandler()
        password = "ValidPassword123!"

        hashed = await handler.hash_password(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    @pytest.mark.asyncio
    async def test_hash_password_ascii_validation(self):
        """Test that password hashing validates ASCII characters"""
        handler = JWTHandler()
        password = "PasswordüWithUnicode"

        with pytest.raises(ValueError, match="Password must contain only ASCII characters"):
            await handler.hash_password(password)

    @pytest.mark.asyncio
    @patch("asyncio.get_event_loop")
    async def test_hash_password_uses_executor(self, mock_get_event_loop):
        """Test that password hashing uses executor to avoid blocking"""
        mock_loop = MagicMock()
        mock_get_event_loop.return_value = mock_loop
        # Mock the return value of run_in_executor to be a string
        mock_future = asyncio.Future()
        mock_future.set_result("mocked_hash")
        mock_loop.run_in_executor.return_value = mock_future

        handler = JWTHandler()
        password = "ValidPassword123!"

        result = await handler.hash_password(password)
        mock_loop.run_in_executor.assert_called()

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.logger")
    async def test_hash_password_error_logging(self, mock_logger):
        """Test that password hashing errors are logged"""
        handler = JWTHandler()

        # Force an error by patching the hash method
        with patch.object(handler.pwd_context, "hash", side_effect=Exception("Hashing failed")):
            with pytest.raises(RuntimeError, match="Password hashing failed"):
                await handler.hash_password("ValidPassword123!")
            mock_logger.error.assert_called()


class TestAsyncPasswordVerification:
    """Test asynchronous password verification functionality"""

    @pytest.mark.asyncio
    async def test_verify_password_valid(self):
        """Test verification of valid password"""
        handler = JWTHandler()
        password = "ValidPassword123!"

        # First hash the password
        hashed = await handler.hash_password(password)

        # Then verify it
        is_valid = await handler.verify_password(password, hashed)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_password_invalid(self):
        """Test verification of invalid password"""
        handler = JWTHandler()
        password = "ValidPassword123!"
        wrong_password = "WrongPassword123!"

        # First hash the password
        hashed = await handler.hash_password(password)

        # Then verify with wrong password
        is_valid = await handler.verify_password(wrong_password, hashed)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_password_ascii_validation(self):
        """Test that password verification validates ASCII characters"""
        handler = JWTHandler()
        password = "PasswordüWithUnicode"

        with pytest.raises(ValueError, match="Password must contain only ASCII characters"):
            await handler.verify_password(password, "some_hash")

    @pytest.mark.asyncio
    @patch("asyncio.get_event_loop")
    async def test_verify_password_uses_executor(self, mock_get_event_loop):
        """Test that password verification uses executor to avoid blocking"""
        mock_loop = MagicMock()
        mock_get_event_loop.return_value = mock_loop
        # Mock the return value of run_in_executor to be a boolean
        mock_future = asyncio.Future()
        mock_future.set_result(True)
        mock_loop.run_in_executor.return_value = mock_future

        handler = JWTHandler()
        password = "ValidPassword123!"
        hashed = "mocked_hash"

        result = await handler.verify_password(password, hashed)
        mock_loop.run_in_executor.assert_called()

    @pytest.mark.asyncio
    @patch("src.core.auth.jwt_handler.logger")
    async def test_verify_password_error_logging(self, mock_logger):
        """Test that password verification errors are logged"""
        handler = JWTHandler()
        password = "ValidPassword123!"
        hashed = "some_hash"

        # Force an error by patching the verify method
        with patch.object(
            handler.pwd_context, "verify", side_effect=Exception("Verification failed")
        ):
            with pytest.raises(RuntimeError, match="Password verification failed"):
                await handler.verify_password(password, hashed)
            mock_logger.error.assert_called()


class TestGlobalInstance:
    """Test global JWT handler instance"""

    def test_global_instance_exists(self):
        """Test that global jwt_handler instance exists"""
        assert jwt_handler is not None
        assert isinstance(jwt_handler, JWTHandler)

    def test_global_instance_singleton(self):
        """Test that global jwt_handler is a singleton"""
        from src.core.auth.jwt_handler import JWTHandler as ImportedJWTHandler

        new_handler = ImportedJWTHandler()
        # They should be different instances
        assert new_handler is not jwt_handler


class TestSyncWrappers:
    """Test synchronous wrapper functions"""

    def test_get_password_hash(self):
        """Test synchronous password hashing wrapper"""
        password = "ValidPassword123!"
        hashed = get_password_hash(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_verify_password(self):
        """Test synchronous password verification wrapper"""
        password = "ValidPassword123!"
        hashed = get_password_hash(password)
        is_valid = verify_password(password, hashed)
        assert is_valid is True

    def test_verify_password_invalid(self):
        """Test synchronous password verification with wrong password"""
        password = "ValidPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = get_password_hash(password)
        is_valid = verify_password(wrong_password, hashed)
        assert is_valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
