"""
Unit tests for src.core.auth.oauth2_service.py
Targets 85%+ coverage for OAuth2Service class and functions
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.oauth2_service import OAuth2Service, TokenBlacklist, logger, oauth2_service
from src.core.models.rbac_models import User


class TestTokenBlacklistModel:
    """Test TokenBlacklist SQLAlchemy model"""

    def test_token_blacklist_repr(self):
        """Test TokenBlacklist __repr__ method"""
        from datetime import datetime, timezone

        blacklist_entry = TokenBlacklist(
            jti="test-jti-12345678",
            user_id=1,
            token_hash="test-hash",
            expires_at=datetime.now(timezone.utc),
            revoked_by=1,
            reason="test",
        )

        repr_str = repr(blacklist_entry)
        assert "TokenBlacklist" in repr_str
        assert "user_id=1" in repr_str
        # The jti might be truncated in the repr, so we just check it's there
        assert "jti=" in repr_str


class TestOAuth2ServiceInitialization:
    """Test OAuth2Service class initialization"""

    def test_oauth2_service_initialization(self):
        """Test OAuth2Service initializes correctly"""
        service = OAuth2Service()
        assert service is not None
        assert hasattr(service, "jwt_handler")
        assert hasattr(service, "access_token_expire_minutes")
        assert hasattr(service, "refresh_token_expire_days")

    def test_oauth2_service_config_values(self):
        """Test OAuth2Service uses config values"""
        with patch("src.core.auth.oauth2_service.config") as mock_config:
            mock_config.jwt_expire_minutes = 30
            mock_config.refresh_token_expire_days = 14

            service = OAuth2Service()
            assert service.access_token_expire_minutes == 30
            assert service.refresh_token_expire_days == 14

    def test_oauth2_service_default_config_values(self):
        """Test OAuth2Service uses default values when config is None"""
        with patch("src.core.auth.oauth2_service.config") as mock_config:
            mock_config.jwt_expire_minutes = None
            mock_config.refresh_token_expire_days = None

            service = OAuth2Service()
            assert service.access_token_expire_minutes == 60  # default
            assert service.refresh_token_expire_days == 7  # default


class TestCreateTokens:
    """Test OAuth2Service.create_tokens method"""

    @pytest.mark.asyncio
    async def test_create_tokens_success(self):
        """Test successful token creation"""
        service = OAuth2Service()

        # Mock internal methods
        with (
            patch.object(service, "_create_access_token") as mock_create_access_token,
            patch.object(service, "_create_refresh_token") as mock_create_refresh_token,
        ):
            mock_create_access_token.return_value = "mock_access_token"
            mock_create_refresh_token.return_value = "mock_refresh_token"

            result = await service.create_tokens(
                user_id=1,
                email="test@example.com",
                role_ids=[1, 2],
                scopes=["read", "write"],
                tenant_id=1,
            )

            assert isinstance(result, dict)
            assert result["access_token"] == "mock_access_token"
            assert result["refresh_token"] == "mock_refresh_token"
            assert result["token_type"] == "Bearer"
            assert "expires_in" in result

            mock_create_access_token.assert_called_once_with(
                user_id=1,
                email="test@example.com",
                role_ids=[1, 2],
                scopes=["read", "write"],
                tenant_id=1,
            )
            # OP-182: de tenant gaat nu MEE naar de refresh-fabriek. Deze toets pinde het
        # defect vast: _create_refresh_token had tenant_id=1 als default en werd
        # zonder tenant aangeroepen, waardoor elk refresh-token in tenant 1 kwam.
        mock_create_refresh_token.assert_called_once_with(1, 1)

    @pytest.mark.asyncio
    async def test_create_tokens_default_values(self):
        """Test token creation with default values"""
        service = OAuth2Service()

        # Mock internal methods
        with (
            patch.object(service, "_create_access_token") as mock_create_access_token,
            patch.object(service, "_create_refresh_token") as mock_create_refresh_token,
        ):
            mock_create_access_token.return_value = "mock_access_token"
            mock_create_refresh_token.return_value = "mock_refresh_token"

            result = await service.create_tokens(user_id=1, email="test@example.com")

            assert isinstance(result, dict)
            mock_create_access_token.assert_called_once_with(
                user_id=1, email="test@example.com", role_ids=[], scopes=[], tenant_id=1
            )


class TestCreateAccessToken:
    """Test OAuth2Service._create_access_token method"""

    @pytest.mark.asyncio
    async def test_create_access_token(self):
        """Test access token creation"""
        service = OAuth2Service()

        # Mock jwt_handler
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
            mock_jwt_handler.create_access_token.assert_called_once()

            # Check that the payload contains expected fields
            call_args = mock_jwt_handler.create_access_token.call_args[0][0]
            assert call_args["sub"] == "1"
            assert call_args["email"] == "test@example.com"
            assert call_args["role_ids"] == [1, 2]
            assert isinstance(call_args["role_ids"], list)
            assert all(isinstance(r, int) for r in call_args["role_ids"])
            assert call_args["scopes"] == ["read", "write"]
            assert isinstance(call_args["scopes"], list)
            assert all(isinstance(s, str) for s in call_args["scopes"])
            assert call_args["tenant_id"] == 1
            assert "jti" in call_args
            assert "iat" in call_args
            assert "exp" in call_args


class TestCreateRefreshToken:
    """Test OAuth2Service._create_refresh_token method"""

    @pytest.mark.asyncio
    async def test_create_refresh_token(self):
        """Test refresh token creation"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_refresh_token.return_value = "mock_refresh_token"

            token = await service._create_refresh_token(user_id=1, tenant_id=1)

            assert token == "mock_refresh_token"
            # OP-182: uit de REFRESH-fabriek, niet uit de access-fabriek.
            mock_jwt_handler.create_refresh_token.assert_called_once()
            mock_jwt_handler.create_access_token.assert_not_called()

            # Check that the payload contains expected fields
            call_args = mock_jwt_handler.create_refresh_token.call_args[0][0]
            assert call_args["sub"] == "1"
            # Het soort zit in de JOSE-header `typ`, niet in een body-claim.
            assert "type" not in call_args
            assert "jti" in call_args
            assert "iat" in call_args
            assert "exp" in call_args


class TestRefreshAccessToken:
    """Test OAuth2Service.refresh_access_token method"""

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self):
        """Test successful access token refresh"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "type": "refresh",
                "sub": "1",
                "role_ids": [1, 2],
                "scopes": ["read", "write"],
                "jti": "test-jti",
            }

            # Mock _is_token_blacklisted to return False; er is ook geen "alle sessies"-grens
            with (
                patch.object(service, "_is_token_blacklisted", return_value=False),
                patch.object(service, "is_uitgegeven_voor_intrekking", return_value=False),
            ):
                # Mock database session
                mock_db = AsyncMock(spec=AsyncSession)

                # Mock database query result
                mock_user = MagicMock(spec=User)
                mock_user.id = 1
                mock_user.email = "test@example.com"
                mock_user.tenant_id = 1

                # Sinds ADR-036 OP-154 stap 2b doet `refresh_access_token` TWEE
                # opzoekingen: eerst via `pre_auth_lookup` alleen `(id, tenant_id)`
                # (`.one_or_none()`), daarna met de klant aangenomen de volle rij
                # (`.scalar_one_or_none()`). Zonder een ingerichte omzeilverbinding levert
                # `pre_auth_lookup` gewoon de meegegeven sessie op, dus beide lopen over
                # deze ene mock.
                mock_kolommen = MagicMock()
                mock_kolommen.id = mock_user.id
                mock_kolommen.tenant_id = mock_user.tenant_id

                mock_result = MagicMock()
                mock_result.one_or_none.return_value = mock_kolommen
                mock_result.scalar_one_or_none.return_value = mock_user
                mock_db.execute.return_value = mock_result

                # Mock _create_access_token
                with patch.object(service, "_create_access_token") as mock_create_access_token:
                    mock_create_access_token.return_value = "new_access_token"

                    result = await service.refresh_access_token("refresh_token", mock_db)

                    assert result is not None
                    assert result["access_token"] == "new_access_token"
                    assert result["token_type"] == "Bearer"
                    mock_create_access_token.assert_called_once_with(
                        user_id=1,
                        email="test@example.com",
                        role_ids=[1, 2],
                        scopes=["read", "write"],
                        tenant_id=1,
                    )

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_token(self):
        """Test refresh fails with invalid token"""
        service = OAuth2Service()

        # Mock jwt_handler to return None (invalid token)
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = None

            mock_db = AsyncMock(spec=AsyncSession)
            result = await service.refresh_access_token("invalid_token", mock_db)

            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_access_token_wrong_type(self):
        """Test refresh fails with wrong token type"""
        service = OAuth2Service()

        # Mock jwt_handler to return token with wrong type
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {"type": "access", "sub": "1"}

            mock_db = AsyncMock(spec=AsyncSession)
            result = await service.refresh_access_token("access_token", mock_db)

            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_access_token_blacklisted(self):
        """Test refresh fails with blacklisted token"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "type": "refresh",
                "sub": "1",
                "jti": "blacklisted-jti",
            }

            # Mock _is_token_blacklisted to return True
            with patch.object(service, "_is_token_blacklisted", return_value=True):
                mock_db = AsyncMock(spec=AsyncSession)
                result = await service.refresh_access_token("blacklisted_token", mock_db)

                assert result is None

    @pytest.mark.asyncio
    async def test_refresh_access_token_user_not_found(self):
        """Test refresh fails when user not found"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "type": "refresh",
                "sub": "999",
                "jti": "test-jti",
            }

            # Mock _is_token_blacklisted to return False
            with patch.object(service, "_is_token_blacklisted", return_value=False):
                # Mock database session
                mock_db = AsyncMock(spec=AsyncSession)

                # Niet gevonden: de EERSTE opzoeking (`pre_auth_lookup`) levert al
                # niets op, en dan hoort de tweede er nooit te komen.
                mock_result = MagicMock()
                mock_result.one_or_none.return_value = None
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute.return_value = mock_result

                result = await service.refresh_access_token("refresh_token", mock_db)

                assert result is None


def _niet_ingetrokken() -> MagicMock:
    """Een databaseantwoord waarin de jti nog NIET op de blacklist staat."""
    antwoord = MagicMock()
    antwoord.scalar_one_or_none.return_value = None
    return antwoord


class TestRevokeToken:
    """Test OAuth2Service.revoke_token method"""

    @pytest.mark.asyncio
    async def test_revoke_token_success(self):
        """Test successful token revocation"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "jti": "test-jti",
                "exp": datetime.now(timezone.utc).timestamp() + 3600,
            }

            # Mock _hash_token
            with patch.object(service, "_hash_token", return_value="hashed_token"):
                # Mock database session
                mock_db = AsyncMock(spec=AsyncSession)
                mock_db.commit = AsyncMock()
                mock_db.execute.return_value = _niet_ingetrokken()

                result = await service.revoke_token(
                    token="valid_token", user_id=1, db=mock_db, reason="logout"
                )

                assert result is True
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()

                # Check that TokenBlacklist was created with correct values
                added_entry = mock_db.add.call_args[0][0]
                assert isinstance(added_entry, TokenBlacklist)
                assert added_entry.jti == "test-jti"
                assert added_entry.user_id == 1
                assert added_entry.token_hash == "hashed_token"
                assert added_entry.revoked_by == 1
                assert added_entry.reason == "logout"

    @pytest.mark.asyncio
    async def test_revoke_token_invalid_token(self):
        """Test revocation fails with invalid token"""
        service = OAuth2Service()

        # Mock jwt_handler to return None (invalid token)
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = None

            mock_db = AsyncMock(spec=AsyncSession)
            # Note: rollback may not be called for invalid token since no DB operation occurs
            # mock_db.rollback = AsyncMock()

            result = await service.revoke_token(token="invalid_token", user_id=1, db=mock_db)

            assert result is False
            # For invalid token, no DB operations should occur
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_token_missing_jti(self):
        """Test revocation fails with token missing JTI"""
        service = OAuth2Service()

        # Mock jwt_handler to return token without JTI
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "exp": datetime.now(timezone.utc).timestamp() + 3600
                # Missing "jti" field
            }

            mock_db = AsyncMock(spec=AsyncSession)
            # Note: rollback may not be called since no DB operation occurs
            # mock_db.rollback = AsyncMock()

            result = await service.revoke_token(token="token_without_jti", user_id=1, db=mock_db)

            assert result is False
            # For missing JTI, no DB operations should occur
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_token_missing_exp(self):
        """Test revocation fails with token missing expiration"""
        service = OAuth2Service()

        # Mock jwt_handler to return token without expiration
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "jti": "test-jti"
                # Missing "exp" field
            }

            mock_db = AsyncMock(spec=AsyncSession)
            # Note: rollback may not be called since no DB operation occurs
            # mock_db.rollback = AsyncMock()

            result = await service.revoke_token(token="token_without_exp", user_id=1, db=mock_db)

            assert result is False
            # For missing exp, no DB operations should occur
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_token_database_error(self):
        """Test revocation handles database errors"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "jti": "test-jti",
                "exp": datetime.now(timezone.utc).timestamp() + 3600,
            }

            # Mock _hash_token
            with patch.object(service, "_hash_token", return_value="hashed_token"):
                # Mock database session to raise exception
                mock_db = AsyncMock(spec=AsyncSession)
                mock_db.execute.return_value = _niet_ingetrokken()
                mock_db.add.side_effect = Exception("Database error")
                mock_db.rollback = AsyncMock()

                result = await service.revoke_token(token="valid_token", user_id=1, db=mock_db)

                assert result is False
                mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_token_names_holder_and_revoker_separately(self):
        service = OAuth2Service()
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "jti": "test-jti",
                "exp": datetime.now(timezone.utc).timestamp() + 3600,
            }
            with patch.object(service, "_hash_token", return_value="hashed_token"):
                mock_db = AsyncMock(spec=AsyncSession)
                mock_db.execute.return_value = _niet_ingetrokken()

                result = await service.revoke_token(
                    token="valid_token", user_id=7, db=mock_db, revoked_by=3
                )

                added_entry = mock_db.add.call_args[0][0]
                assert result is True
                assert (added_entry.user_id, added_entry.revoked_by) == (7, 3)

    @pytest.mark.asyncio
    async def test_revoke_token_that_is_already_revoked_counts_as_success_without_a_second_row(
        self,
    ):
        service = OAuth2Service()
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "jti": "test-jti",
                "exp": datetime.now(timezone.utc).timestamp() + 3600,
            }
            mock_db = AsyncMock(spec=AsyncSession)
            al_ingetrokken = MagicMock()
            al_ingetrokken.scalar_one_or_none.return_value = object()
            mock_db.execute.return_value = al_ingetrokken

            result = await service.revoke_token(token="valid_token", user_id=1, db=mock_db)

            assert result is True
            mock_db.add.assert_not_called()


class TestIsTokenValid:
    """Test OAuth2Service.is_token_valid method"""

    @pytest.mark.asyncio
    async def test_is_token_valid_success(self):
        """Test valid token is recognized as valid"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {"jti": "test-jti"}

            # Mock _is_token_blacklisted to return False
            with patch.object(service, "_is_token_blacklisted", return_value=False):
                # Mock database session
                mock_db = AsyncMock(spec=AsyncSession)

                result = await service.is_token_valid("valid_token", mock_db)

                assert result is True

    @pytest.mark.asyncio
    async def test_is_token_valid_invalid_signature(self):
        """Test invalid token is recognized as invalid"""
        service = OAuth2Service()

        # Mock jwt_handler to return None (invalid signature)
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = None

            # Mock database session
            mock_db = AsyncMock(spec=AsyncSession)

            result = await service.is_token_valid("invalid_token", mock_db)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_token_valid_missing_jti(self):
        """Test token without JTI is recognized as invalid"""
        service = OAuth2Service()

        # Mock jwt_handler to return token without JTI
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {}
            # Missing "jti" field

            # Mock database session
            mock_db = AsyncMock(spec=AsyncSession)

            result = await service.is_token_valid("token_without_jti", mock_db)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_token_valid_blacklisted(self):
        """Test blacklisted token is recognized as invalid"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {"jti": "blacklisted-jti"}

            # Mock _is_token_blacklisted to return True
            with patch.object(service, "_is_token_blacklisted", return_value=True):
                # Mock database session
                mock_db = AsyncMock(spec=AsyncSession)

                result = await service.is_token_valid("blacklisted_token", mock_db)

                assert result is False


class TestIsTokenBlacklisted:
    """Test OAuth2Service._is_token_blacklisted method"""

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_true(self):
        """Test blacklisted token is detected"""
        service = OAuth2Service()

        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query result - token is blacklisted
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Any object means found
        mock_db.execute.return_value = mock_result

        result = await service._is_token_blacklisted("blacklisted-jti", mock_db)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_false(self):
        """Test non-blacklisted token is not detected"""
        service = OAuth2Service()

        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query result - token not found (None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service._is_token_blacklisted("valid-jti", mock_db)

        assert result is False


class TestCleanupExpiredTokens:
    """Test OAuth2Service.cleanup_expired_tokens method"""

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens_success(self):
        """Test successful cleanup of expired tokens"""
        service = OAuth2Service()

        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()

        # Mock delete result
        mock_result = MagicMock()
        mock_result.rowcount = 5  # 5 tokens deleted
        mock_db.execute.return_value = mock_result

        result = await service.cleanup_expired_tokens(mock_db)

        assert result == 5
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens_database_error(self):
        """Test cleanup handles database errors"""
        service = OAuth2Service()

        # Mock database session to raise exception
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute.side_effect = Exception("Database error")
        mock_db.rollback = AsyncMock()

        result = await service.cleanup_expired_tokens(mock_db)

        assert result == 0
        mock_db.rollback.assert_called_once()


class TestHashToken:
    """Test OAuth2Service._hash_token method"""

    def test_hash_token(self):
        """Test token hashing produces consistent results"""
        service = OAuth2Service()

        token = "test_token_123"
        hash1 = service._hash_token(token)
        hash2 = service._hash_token(token)

        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) > 0


class TestExtractTokenClaims:
    """Test OAuth2Service.extract_token_claims method"""

    def test_extract_token_claims(self):
        """Test extraction of token claims"""
        service = OAuth2Service()

        # Mock jwt_handler
        with patch.object(service, "jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_token.return_value = {
                "sub": "1",
                "email": "test@example.com",
            }

            result = service.extract_token_claims("test_token")

            assert result == {"sub": "1", "email": "test@example.com"}
            mock_jwt_handler.verify_token.assert_called_once_with("test_token")


class TestGlobalInstance:
    """Test global oauth2_service instance"""

    def test_global_instance_exists(self):
        """Test that global oauth2_service instance exists"""
        assert oauth2_service is not None
        assert isinstance(oauth2_service, OAuth2Service)

    def test_global_instance_singleton(self):
        """Test that global oauth2_service is a singleton"""
        from src.core.auth.oauth2_service import OAuth2Service as ImportedOAuth2Service

        new_service = ImportedOAuth2Service()
        # They should be different instances
        assert new_service is not oauth2_service


class TestModuleExports:
    """Test module exports"""

    def test_oauth2_service_exported(self):
        """Test that OAuth2Service is exported"""
        from src.core.auth.oauth2_service import OAuth2Service as ImportedOAuth2Service

        assert ImportedOAuth2Service is OAuth2Service

    def test_token_blacklist_exported(self):
        """Test that TokenBlacklist is exported"""
        from src.core.auth.oauth2_service import TokenBlacklist as ImportedTokenBlacklist

        assert ImportedTokenBlacklist is TokenBlacklist

    def test_oauth2_service_instance_exported(self):
        """Test that oauth2_service instance is exported"""
        from src.core.auth.oauth2_service import oauth2_service as imported_oauth2_service

        assert imported_oauth2_service is oauth2_service

    def test_logger_exported(self):
        """Test that logger is exported"""
        from src.core.auth.oauth2_service import logger as imported_logger

        assert imported_logger is logger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
