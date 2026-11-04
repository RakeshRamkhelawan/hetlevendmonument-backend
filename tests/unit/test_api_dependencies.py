"""
Unit tests for core/auth/dependencies.py - Authentication & DB Session Dependencies
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse

# Import the functions to be tested
from src.core.auth.dependencies import get_current_user, get_current_user_dependency


@pytest.fixture(autouse=True)
def _geen_ingetrokken_token(monkeypatch):
    """Deze tests mocken de database, dus ook de intrekkingscontrole (ADR-036 OP-188).

    `_get_user_from_token` raadpleegt sinds 2026-09-15 de blacklist op `jti`. Met een
    `AsyncMock`-database geeft `scalar_one_or_none()` een mock terug, en dat leest als
    "ingetrokken" -- de test faalt dan met een 401 die niets met zijn onderwerp te maken
    heeft. De productiecode is hier correct; de mock is te los.
    """
    from src.core.auth import oauth2_service as _mod

    async def _niet_ingetrokken(self, jti, db):  # noqa: ANN001, ANN202
        return False

    monkeypatch.setattr(_mod.OAuth2Service, "is_jti_revoked", _niet_ingetrokken)



class TestGetCurrentUser:
    """Test JWT token-based authentication using the refactored get_current_user."""

    @pytest.mark.asyncio
    @patch(
        "src.core.auth.dependencies.jwt_handler.verify_token",
        return_value={"sub": "test@example.com", "jti": "test-jti"},
    )
    async def test_get_current_user_valid_token(self, mock_verify_token):
        """Test user retrieval with valid JWT token."""
        # NOTE: dependencies.py uses jwt_handler.verify_token directly (not via get_security_manager).
        # Patch target must be the jwt_handler instance imported into the dependencies module.
        mock_db = AsyncMock(spec=AsyncSession)
        token = "valid.jwt.token"

        mock_user_response = UserResponse(id=1, email="test@example.com", tenant_id=1, role_id=1)

        with patch(
            "src.core.auth.dependencies.auth_service.get_user_by_email",
            AsyncMock(return_value=mock_user_response),
        ) as mock_get_user_by_email:
            result = await get_current_user(db=mock_db, token=token)

            assert result == mock_user_response
            mock_verify_token.assert_called_once_with(token)
            mock_get_user_by_email.assert_called_once_with(mock_db, email="test@example.com")

    @pytest.mark.asyncio
    @patch("src.core.auth.dependencies.jwt_handler.verify_token", return_value=None)
    async def test_get_current_user_invalid_token(self, mock_verify_token):
        """Test authentication fails with invalid token."""
        mock_db = AsyncMock(spec=AsyncSession)
        token = "invalid.jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=token)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch(
        "src.core.auth.dependencies.jwt_handler.verify_token",
        return_value={"sub": "not.in.db@example.com", "jti": "test-jti"},
    )
    async def test_get_current_user_user_not_found_in_db(self, mock_verify_token):
        """Test authentication fails if user from token is not in the database."""
        mock_db = AsyncMock(spec=AsyncSession)
        token = "valid.token.user.not.in.db"

        with patch(
            "src.core.auth.dependencies.auth_service.get_user_by_email",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=mock_db, token=token)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(
        "src.core.auth.dependencies.jwt_handler.verify_token",
        return_value={"user_id": "some_id"},
    )
    async def test_get_current_user_no_email_in_payload(self, mock_verify_token):
        """Test authentication fails if token payload has no email ('sub')."""
        # Payload has user_id="some_id" (no email, no sub, no numeric id) -> 401
        mock_db = AsyncMock(spec=AsyncSession)
        token = "token.without.email"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=token)

        assert exc_info.value.status_code == 401
