"""
Tests for src/core/auth/auth_bearer.py
Target: 85%+ coverage
Tests: 30-40
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status


class TestAuthBearerExports:
    """Test module exports"""

    def test_oauth2_scheme_export(self):
        """Test oauth2_scheme is exported"""
        from src.core.auth.auth_bearer import oauth2_scheme

        assert oauth2_scheme is not None

    def test_get_current_user_export(self):
        """Test get_current_user is exported"""
        from src.core.auth.auth_bearer import get_current_user

        assert get_current_user is not None


class TestGetCurrentUserFunction:
    """Test get_current_user function"""

    def test_get_current_user_exists(self):
        """Test get_current_user function exists and is callable"""
        from src.core.auth.auth_bearer import get_current_user

        assert get_current_user is not None
        assert callable(get_current_user)

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_valid_token_standard_format(self, mock_verify_token):
        """Test get_current_user with valid token in standard format"""
        mock_payload = {"sub": "test@example.com"}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_user_response = MagicMock()
            mock_user_response.email = "test@example.com"
            mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            result = asyncio.run(get_current_user("valid_token", mock_db))

            assert result == mock_user_response
            mock_verify_token.assert_called_once_with("valid_token")
            mock_auth_service.get_user_by_email.assert_called_once_with(mock_db, "test@example.com")

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_valid_token_email_claim_format(self, mock_verify_token):
        """Test get_current_user when payload uses email claim as the login identifier."""
        mock_payload = {"sub": "opaque-subject", "email": "test@example.com"}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_user_response = MagicMock()
            mock_user_response.email = "test@example.com"
            mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            result = asyncio.run(get_current_user("valid_token", mock_db))

            assert result == mock_user_response
            mock_verify_token.assert_called_once_with("valid_token")
            mock_auth_service.get_user_by_email.assert_called_once_with(mock_db, "test@example.com")

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_valid_token_user_id_fallback_format(self, mock_verify_token):
        """Test get_current_user keeps extracting email from user_id when sub is not an email."""
        mock_payload = {"sub": "opaque-subject", "user_id": "user_test@example.com"}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_user_response = MagicMock()
            mock_user_response.email = "test@example.com"
            mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            result = asyncio.run(get_current_user("valid_token", mock_db))

            assert result == mock_user_response
            mock_verify_token.assert_called_once_with("valid_token")
            mock_auth_service.get_user_by_email.assert_called_once_with(mock_db, "test@example.com")

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_invalid_token(self, mock_verify_token):
        """Test get_current_user with invalid token"""
        mock_verify_token.return_value = None
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user("invalid_token", mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_no_email_in_payload(self, mock_verify_token):
        """Test get_current_user when no email found in token payload"""
        mock_payload = {"some_other_field": "value"}
        mock_verify_token.return_value = mock_payload

        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user("token_without_email", mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_user_not_found(self, mock_verify_token):
        """Test get_current_user when user is not found in database"""
        mock_payload = {"sub": "nonexistent@example.com"}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_auth_service.get_user_by_email = AsyncMock(return_value=None)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user("valid_token", mock_db))

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Could not validate credentials" in exc_info.value.detail

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_token_verification_exception(self, mock_verify_token):
        """Test get_current_user when token verification raises exception"""
        mock_verify_token.side_effect = Exception("Token verification failed")
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user("problematic_token", mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    @patch("src.core.security.security_manager.get_security_manager")
    def test_get_current_user_does_not_call_security_manager(
        self, mock_get_security_manager, mock_verify_token
    ):
        """Test get_current_user verifies tokens only through jwt_handler."""
        mock_get_security_manager.side_effect = AssertionError(
            "security_manager must not be used by auth_bearer"
        )
        mock_verify_token.return_value = {"sub": "test@example.com"}

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_user_response = MagicMock()
            mock_user_response.email = "test@example.com"
            mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            result = asyncio.run(get_current_user("valid_token", mock_db))

            assert result == mock_user_response
            mock_verify_token.assert_called_once_with("valid_token")
            mock_get_security_manager.assert_not_called()

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_get_current_user_rejects_legacy_payload_when_canonical_verifier_returns_none(
        self, mock_verify_token
    ):
        """Test legacy no-sub tokens are rejected once canonical verification fails."""
        mock_verify_token.return_value = None

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user("legacy_user_id_only_token", mock_db))

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            mock_auth_service.get_user_by_email.assert_not_called()


class TestGetCurrentUserDependency:
    """Test get_current_user_dependency wrapper"""

    def test_dependency_wrapper_exists(self):
        """Test that get_current_user_dependency wrapper exists"""
        from src.core.auth.dependencies import get_current_user_dependency

        assert get_current_user_dependency is not None
        assert callable(get_current_user_dependency)


class TestAuthBearerIntegration:
    """Test integration scenarios"""

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_successful_authentication_flow(self, mock_verify_token):
        """Test complete successful authentication flow"""
        mock_payload = {"sub": "user@example.com", "exp": 1234567890, "iat": 1234567800}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_user_response = MagicMock()
            mock_user_response.id = 1
            mock_user_response.email = "user@example.com"
            mock_user_response.role_id = 2
            mock_user_response.tenant_id = 1
            mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            result = asyncio.run(get_current_user("valid_jwt_token", mock_db))

            assert result.id == 1
            assert result.email == "user@example.com"
            assert result.role_id == 2
            assert result.tenant_id == 1

            mock_verify_token.assert_called_once_with("valid_jwt_token")
            mock_auth_service.get_user_by_email.assert_called_once_with(mock_db, "user@example.com")

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    @patch("logging.getLogger")
    def test_logging_on_token_verification_failure(self, mock_get_logger, mock_verify_token):
        """Test that logging occurs on token verification failure"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_verify_token.return_value = None
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        try:
            asyncio.run(get_current_user("invalid_token", mock_db))
        except HTTPException:
            pass

        mock_logger.warning.assert_called()

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    @patch("logging.getLogger")
    def test_logging_on_user_not_found(self, mock_get_logger, mock_verify_token):
        """Test that logging occurs when user is not found"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_payload = {"sub": "nonexistent@example.com"}
        mock_verify_token.return_value = mock_payload

        with patch("src.core.auth.auth_service") as mock_auth_service:
            mock_auth_service.get_user_by_email = AsyncMock(return_value=None)
            mock_db = MagicMock()
            import asyncio

            from src.core.auth.auth_bearer import get_current_user

            try:
                asyncio.run(get_current_user("valid_token", mock_db))
            except HTTPException:
                pass

            mock_logger.warning.assert_called()


class TestAuthBearerErrorHandling:
    """Test error handling scenarios"""

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_malformed_token_handling(self, mock_verify_token):
        """Test handling of malformed tokens"""
        mock_verify_token.return_value = None
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user("malformed.token.here", mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_empty_token_handling(self, mock_verify_token):
        """Test handling of empty tokens"""
        mock_verify_token.side_effect = ValueError("Token cannot be empty or whitespace")
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user("", mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_none_token_handling(self, mock_verify_token):
        """Test handling of None tokens"""
        mock_verify_token.side_effect = TypeError("Token must be a string")
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(None, mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_none_token_short_circuits_verify_token(self, mock_verify_token):
        """SPEC: With token=None, verify_token must NEVER be called.

        Rationale: jwt_handler.verify_token() expects str, not Optional[str].
        For type safety (mypy), we must validate token presence BEFORE calling it.
        This test proves that verify_token is never invoked when token=None.
        """
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(None, mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        # CRITICAL ASSERTION: verify_token must NOT be called
        mock_verify_token.assert_not_called()

    @patch("src.core.auth.auth_bearer.jwt_handler.verify_token")
    def test_missing_bearer_token_returns_401_with_auth_header(self, _mock_verify):
        """User behavioral test: missing token returns 401 with WWW-Authenticate header."""
        mock_db = MagicMock()
        import asyncio

        from src.core.auth.auth_bearer import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(None, mock_db))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.headers is not None, "headers must be present"
        assert "WWW-Authenticate" in exc_info.value.headers
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"
