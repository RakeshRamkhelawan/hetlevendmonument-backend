"""
Security-focused unit tests for OAuth2Service
Tests for SEC-003: JWT Secret Logging Fix
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.core.auth.oauth2_service import OAuth2Service


class TestJWTSeretLoggingFix:
    """Test that JWT secrets are not logged (SEC-003)"""

    @pytest.mark.asyncio
    async def test_create_access_token_does_not_log_secret(self, caplog):
        """Happy path: Verify JWT secret is not logged in access token creation"""
        service = OAuth2Service()

        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_access_token.return_value = "mock_token"
            mock_jwt_handler.secret_key = "super_secret_key_that_should_not_be_logged"

            with caplog.at_level("INFO"):
                await service._create_access_token(
                    user_id=1,
                    email="test@example.com",
                    role_ids=[1, 2],
                    scopes=["read"],
                    tenant_id=1,
                )

            # Assert: Secret key should not appear in any log message
            for record in caplog.records:
                assert "super_secret_key" not in record.message
                assert "secret_key" not in record.message.lower()
                assert (
                    "secret" not in record.message.lower()
                    or "access token" in record.message.lower()
                )

    @pytest.mark.asyncio
    async def test_create_access_token_does_not_log_partial_secret(self, caplog):
        """Happy path: Verify partial JWT secret (first 12 chars) is not logged"""
        service = OAuth2Service()

        secret_key = "very_long_secret_key_12345"

        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_access_token.return_value = "mock_token"
            mock_jwt_handler.secret_key = secret_key

            with caplog.at_level("INFO"):
                await service._create_access_token(
                    user_id=1,
                    email="test@example.com",
                    role_ids=[1, 2],
                    scopes=["read"],
                    tenant_id=1,
                )

            # Assert: No part of the secret should be logged (check first 12 chars)
            partial_secret = secret_key[:12]
            for record in caplog.records:
                assert (
                    partial_secret not in record.message
                ), f"Partial secret found in log: {record.message}"

    @pytest.mark.asyncio
    async def test_create_tokens_does_not_log_secret(self, caplog):
        """Happy path: Verify create_tokens method doesn't log secrets"""
        service = OAuth2Service()

        with (
            patch.object(service, "_create_access_token") as mock_access,
            patch.object(service, "_create_refresh_token") as mock_refresh,
        ):
            mock_access.return_value = "access_token"
            mock_refresh.return_value = "refresh_token"

            with caplog.at_level("INFO"):
                await service.create_tokens(
                    user_id=1,
                    email="test@example.com",
                    role_ids=[1],
                    scopes=["read"],
                    tenant_id=1,
                )

            # Assert: No secrets in logs
            log_messages = " ".join([r.message for r in caplog.records])
            assert (
                "secret" not in log_messages.lower()
                or "access token created" in log_messages.lower()
            )


class TestOAuth2ServiceErrorHandling:
    """Test error handling doesn't leak secrets"""

    @pytest.mark.asyncio
    async def test_token_refresh_failure_does_not_log_secret(self, caplog):
        """Unhappy path: Verify token refresh errors don't log secrets"""
        service = OAuth2Service()

        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = None  # Invalid token

            with caplog.at_level("ERROR"):
                result = await service.refresh_access_token("invalid_token", MagicMock())

            # Assert: No secrets in error logs
            for record in caplog.records:
                assert "secret" not in record.message.lower()

            assert result is None


class TestTokenCreationHappyPath:
    """Test normal token creation functionality"""

    @pytest.mark.asyncio
    async def test_create_access_token_success(self):
        """Happy path: Access token creation works correctly"""
        service = OAuth2Service()

        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_access_token.return_value = "mock_access_token"

            token = await service._create_access_token(
                user_id=1,
                email="test@example.com",
                role_ids=[1, 2],
                scopes=["read", "write"],
                tenant_id=1,
            )

            assert token == "mock_access_token"

            # Verify payload structure
            call_args = mock_jwt_handler.create_access_token.call_args[0][0]
            assert call_args["sub"] == "1"
            assert call_args["email"] == "test@example.com"
            assert call_args["role_ids"] == [1, 2]
            assert call_args["scopes"] == ["read", "write"]
            assert call_args["tenant_id"] == 1
            assert "jti" in call_args
            assert "iat" in call_args
            assert "exp" in call_args

    @pytest.mark.asyncio
    async def test_create_refresh_token_success(self):
        """Happy path: Refresh token creation works correctly"""
        service = OAuth2Service()

        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_refresh_token.return_value = "mock_refresh_token"

            token = await service._create_refresh_token(user_id=1, tenant_id=1)

            assert token == "mock_refresh_token"

            # OP-182: een refresh token komt uit de REFRESH-fabriek, niet uit de
            # access-fabriek. Dat is de kern van de fix: het soort wordt bij de uitgifte
            # bepaald en in de JOSE-header gestempeld, niet door de aanroeper in een
            # body-claim gezet.
            mock_jwt_handler.create_access_token.assert_not_called()

            # Verify payload structure
            call_args = mock_jwt_handler.create_refresh_token.call_args[0][0]
            assert call_args["sub"] == "1"
            # De body-claim `type` is bewust WEG: het soort zit in de header `typ`.
            # Een body-claim naast de header zou een tweede, concurrerend mechanisme
            # zijn (RFC 8725 par. 3.12 eist regels die elkaar wederzijds uitsluiten).
            assert "type" not in call_args
            assert "token_type" not in call_args
            assert "tenant_id" in call_args
            assert "jti" in call_args
            assert "iat" in call_args
            assert "exp" in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
