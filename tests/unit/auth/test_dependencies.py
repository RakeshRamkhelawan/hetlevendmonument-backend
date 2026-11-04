"""
Unit tests for src.core.auth.dependencies.py
Targets 85%+ coverage for authentication dependencies
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import (
    get_current_user,
    get_current_user_dependency,
    get_current_user_id,
    require_permission,
    require_permission_with_tenant_bypass,
)
from src.core.auth.rbac import Permission
from src.core.models.rbac_models import User

from tests.fixtures.auth import mock_sessie_zonder_intrekking


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
    """Test get_current_user function"""

    @pytest.mark.asyncio
    async def test_get_current_user_success_sub_format(self):
        """Test get_current_user with 'sub' format token"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return payload with 'sub' format
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "test@example.com", "jti": "test-jti"}

            # Mock auth_service
            with patch("src.core.auth.dependencies.auth_service") as mock_auth_service:
                mock_user_response = MagicMock()
                mock_user_response.id = 1
                mock_user_response.email = "test@example.com"
                mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)

                from src.core.auth.dependencies import get_current_user

                result = await get_current_user(db=mock_db, token="valid_token_with_sub")

                assert result == mock_user_response
                # Check that get_user_by_email was called with the email from the token
                mock_auth_service.get_user_by_email.assert_called_once_with(
                    mock_db, email="test@example.com"
                )

    @pytest.mark.asyncio
    async def test_get_current_user_success_email_format(self):
        """Test successful user retrieval with 'email' format token"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return payload with 'email' format
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"email": "test@example.com", "jti": "test-jti"}

            # Mock auth_service
            with patch("src.core.auth.dependencies.auth_service") as mock_auth_service:
                mock_user_response = MagicMock()
                mock_user_response.id = 1
                mock_user_response.email = "test@example.com"
                mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)

                from src.core.auth.dependencies import get_current_user

                result = await get_current_user(db=mock_db, token="valid_token")

                assert result == mock_user_response

    @pytest.mark.asyncio
    async def test_get_current_user_success_user_id_format(self):
        """Test successful user retrieval with 'user_id' format token"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return payload with 'user_id' format
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"user_id": "user_test@example.com", "jti": "test-jti"}

            # Mock auth_service
            with patch("src.core.auth.dependencies.auth_service") as mock_auth_service:
                mock_user_response = MagicMock()
                mock_user_response.id = 1
                mock_user_response.email = "test@example.com"
                mock_auth_service.get_user_by_email = AsyncMock(return_value=mock_user_response)

                from src.core.auth.dependencies import get_current_user

                result = await get_current_user(db=mock_db, token="valid_token")

                assert result == mock_user_response

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test get_current_user raises HTTPException for invalid token"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return None (invalid token)
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = None

            from src.core.auth.dependencies import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=mock_db, token="invalid_token")

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Could not validate credentials"

    @pytest.mark.asyncio
    async def test_get_current_user_no_email_in_token(self):
        """Test get_current_user raises HTTPException when no email in token"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return a payload without any email/sub/user_id claim
        # "somevalue_no_at_sign" has no "@" so it won't be treated as an email
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "somevalue_no_at_sign"}

            from src.core.auth.dependencies import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=mock_db, token="token_without_email")

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Could not validate credentials"

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self):
        """Test get_current_user raises HTTPException when user not found"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock jwt_handler.verify_token to return a valid payload with email in sub
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "nonexistent@example.com"}

            # Mock auth_service to return None (user not found in DB)
            with patch("src.core.auth.dependencies.auth_service") as mock_auth_service:
                mock_auth_service.get_user_by_email = AsyncMock(return_value=None)

                from src.core.auth.dependencies import get_current_user

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(db=mock_db, token="valid_token")

                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
                assert exc_info.value.detail == "Could not validate credentials"


class TestGetCurrentUserDependency:
    """Test get_current_user_dependency function"""

    @pytest.mark.asyncio
    async def test_get_current_user_dependency(self):
        """Test get_current_user_dependency calls get_current_user correctly"""
        # Mock get_current_user
        with patch("src.core.auth.dependencies.get_current_user") as mock_get_current_user:
            mock_user_response = MagicMock()
            mock_get_current_user.return_value = mock_user_response

            # Mock dependencies
            mock_token = "mock_token"
            mock_db = AsyncMock(spec=AsyncSession)

            result = await get_current_user_dependency(token=mock_token, db=mock_db)

            assert result == mock_user_response
            mock_get_current_user.assert_called_once()
            assert mock_get_current_user.call_args.kwargs["db"] == mock_db
            assert mock_get_current_user.call_args.kwargs["token"] == mock_token


class TestGetCurrentUserId:
    """Test get_current_user_id function"""

    @pytest.mark.asyncio
    async def test_get_current_user_id_success_with_int_user_id(self):
        """Test successful user ID retrieval with integer user_id in token"""
        # Mock jwt_handler.verify_token to return payload with integer user_id
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            mock_verify_token.return_value = {
                "user_id": 123,
                "jti": "jti-unittest",
            }

            # Mock database session
            mock_session = AsyncMock(spec=AsyncSession)

            # Mock database query result
            mock_user = MagicMock(spec=User)
            mock_user.id = 123
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            result = await get_current_user_id("valid_token", mock_session)

            assert result == 123
            mock_verify_token.assert_called_once_with("valid_token")

    @pytest.mark.asyncio
    async def test_get_current_user_id_success_with_string_email(self):
        """Test successful user ID retrieval with string email in token"""
        # Mock jwt_handler.verify_token to return payload with string user_id (email)
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            mock_verify_token.return_value = {"user_id": "user_test@example.com", "jti": "test-jti"}

            # Mock database session
            mock_session = AsyncMock(spec=AsyncSession)

            # Mock database query result
            mock_user = MagicMock(spec=User)
            mock_user.id = 456
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            result = await get_current_user_id("valid_token", mock_session)

            assert result == 456

    @pytest.mark.asyncio
    async def test_get_current_user_id_success_with_sub_fallback(self):
        """Test successful user ID retrieval with sub fallback"""
        # Mock jwt_handler.verify_token to return payload with sub field
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            mock_verify_token.return_value = {"sub": "test@example.com", "jti": "test-jti"}

            # Mock database session
            mock_session = AsyncMock(spec=AsyncSession)

            # Mock database query result
            mock_user = MagicMock(spec=User)
            mock_user.id = 789
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            result = await get_current_user_id("valid_token", mock_session)

            assert result == 789

    @pytest.mark.asyncio
    async def test_get_current_user_id_missing_user_identifiers(self):
        """Test get_current_user_id raises HTTPException when no user identifiers in token"""
        mock_session = AsyncMock(spec=AsyncSession)

        # jwt_handler returns a payload with no user-identifying claims
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            # Geen user-identificatie in het token
            mock_verify_token.return_value = {"exp": 9999999999, "jti": "jti-unittest"}

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id("token_without_user_identifiers", mock_session)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert (
                "invalid" in exc_info.value.detail.lower()
                or "token" in exc_info.value.detail.lower()
            )

    @pytest.mark.asyncio
    async def test_get_current_user_id_user_not_found_by_id(self):
        """Test get_current_user_id raises HTTPException when user not found by ID"""
        mock_session = AsyncMock(spec=AsyncSession)

        # jwt_handler returns a payload with a non-existent user ID
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            # Gebruiker bestaat niet
            mock_verify_token.return_value = {"user_id": 999, "jti": "jti-unittest"}

            # Mock database to return no user
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id("token_with_invalid_user_id", mock_session)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert (
                "invalid" in exc_info.value.detail.lower()
                or "token" in exc_info.value.detail.lower()
            )

    @pytest.mark.asyncio
    async def test_get_current_user_id_user_not_found_by_email(self):
        """Test get_current_user_id raises HTTPException when user not found by email"""
        mock_session = AsyncMock(spec=AsyncSession)

        # jwt_handler returns a payload whose email does not exist in the DB
        with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify_token:
            mock_verify_token.return_value = {
                "email": "nonexistent@example.com",
                "jti": "jti-unittest",
            }

            # Mock database to return no user
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id("token_with_invalid_email", mock_session)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert (
                "invalid" in exc_info.value.detail.lower()
                or "token" in exc_info.value.detail.lower()
            )


class TestRequirePermission:
    """Test require_permission function"""

    @pytest.mark.asyncio
    async def test_require_permission_success(self):
        """Test successful permission check"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock get_async_session dependency
            with patch("src.core.auth.dependencies.get_db") as mock_get_async_session:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_get_async_session.return_value = mock_session

                # Mock tenant context
                with patch(
                    "src.core.auth.dependencies.require_tenant_id"
                ) as mock_require_tenant_id:
                    mock_require_tenant_id.return_value = 1

                    # Mock database query result
                    mock_user = MagicMock(spec=User)
                    mock_user.id = 123
                    mock_user.tenant_id = 1
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none.return_value = mock_user
                    # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                    # Zonder deze routering levert die query ook `mock_result` op en concludeert
                    # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                    mock_sessie_zonder_intrekking(mock_session, mock_result)

                    # Mock RBAC service
                    with patch("src.core.auth.dependencies.RBACService") as mock_rbac_service_class:
                        mock_rbac_service = MagicMock()
                        mock_rbac_service.has_permission = AsyncMock(return_value=True)
                        mock_rbac_service_class.return_value = mock_rbac_service

                        # Create permission checker
                        permission_checker = require_permission(Permission.READ)

                        # Call the inner function
                        result = await permission_checker(user_id=123, session=mock_session)

                        assert result == 123
                        mock_rbac_service.has_permission.assert_called_once_with(123, "*", "read")

    @pytest.mark.asyncio
    async def test_require_permission_tenant_mismatch(self):
        """Test permission check fails with tenant mismatch"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock database session
            mock_session = AsyncMock(spec=AsyncSession)

            # Mock tenant context to raise exception (simulating tenant mismatch)
            with patch("src.core.auth.dependencies.require_tenant_id") as mock_require_tenant_id:
                mock_require_tenant_id.side_effect = HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User not found in tenant context. Possible tenant mismatch.",
                )

                # Mock database query result - user in different tenant
                mock_user = MagicMock(spec=User)
                mock_user.id = 123
                mock_user.tenant_id = 2  # Different tenant
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_user
                # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                # Zonder deze routering levert die query ook `mock_result` op en concludeert
                # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                mock_sessie_zonder_intrekking(mock_session, mock_result)

                # Create permission checker
                permission_checker = require_permission(Permission.READ)

                with pytest.raises(HTTPException) as exc_info:
                    await permission_checker(user_id=123, session=mock_session)

                assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
                # The error message should mention tenant mismatch or user not found in tenant context
                assert (
                    "tenant" in exc_info.value.detail.lower()
                    or "user not found" in exc_info.value.detail.lower()
                )

    @pytest.mark.asyncio
    async def test_require_permission_user_not_found(self):
        """Test permission check fails when user not found"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock get_async_session dependency
            with patch("src.core.auth.dependencies.get_db") as mock_get_async_session:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_get_async_session.return_value = mock_session

                # Mock tenant context
                with patch(
                    "src.core.auth.dependencies.require_tenant_id"
                ) as mock_require_tenant_id:
                    mock_require_tenant_id.return_value = 1

                    # Mock database query result - user not found
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none.return_value = None
                    # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                    # Zonder deze routering levert die query ook `mock_result` op en concludeert
                    # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                    mock_sessie_zonder_intrekking(mock_session, mock_result)

                    # Create permission checker
                    permission_checker = require_permission(Permission.READ)

                    with pytest.raises(HTTPException) as exc_info:
                        await permission_checker(user_id=123, session=mock_session)

                    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
                    assert "tenant mismatch" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_require_permission_denied(self):
        """Test permission check fails when user lacks permission"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock get_async_session dependency
            with patch("src.core.auth.dependencies.get_db") as mock_get_async_session:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_get_async_session.return_value = mock_session

                # Mock tenant context
                with patch(
                    "src.core.auth.dependencies.require_tenant_id"
                ) as mock_require_tenant_id:
                    mock_require_tenant_id.return_value = 1

                    # Mock database query result
                    mock_user = MagicMock(spec=User)
                    mock_user.id = 123
                    mock_user.tenant_id = 1
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none.return_value = mock_user
                    # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                    # Zonder deze routering levert die query ook `mock_result` op en concludeert
                    # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                    mock_sessie_zonder_intrekking(mock_session, mock_result)

                    # Mock RBAC service
                    with patch("src.core.auth.dependencies.RBACService") as mock_rbac_service_class:
                        mock_rbac_service = MagicMock()
                        mock_rbac_service.has_permission = AsyncMock(return_value=False)
                        mock_rbac_service_class.return_value = mock_rbac_service

                        # Create permission checker
                        permission_checker = require_permission(Permission.ADMIN)

                        with pytest.raises(HTTPException) as exc_info:
                            await permission_checker(user_id=123, session=mock_session)

                        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
                        assert "missing permission" in exc_info.value.detail.lower()


class TestRequirePermissionWithTenantBypass:
    """Test require_permission_with_tenant_bypass function"""

    @pytest.mark.asyncio
    async def test_require_permission_with_tenant_bypass_superuser(self):
        """Test permission check passes for superuser with tenant bypass"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock database session
            mock_session = AsyncMock(spec=AsyncSession)

            # Mock user with superuser privileges
            mock_user = MagicMock(spec=User)
            mock_user.id = 123
            mock_user.is_superuser = True
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
            # Zonder deze routering levert die query ook `mock_result` op en concludeert
            # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
            mock_sessie_zonder_intrekking(mock_session, mock_result)

            # Mock tenant context
            with patch("src.core.auth.dependencies.get_tenant_id") as mock_get_tenant_id:
                mock_get_tenant_id.return_value = 1

                # Mock audit service - patch at the correct location
                with patch("src.core.governance.services.audit_service.log_security_event"):
                    # Create permission checker with superuser bypass
                    permission_checker = require_permission_with_tenant_bypass(
                        Permission.ADMIN, allow_super_admin=True
                    )

                    # Call the inner function
                    result = await permission_checker(user_id=123, session=mock_session)

                    assert result == 123

    @pytest.mark.asyncio
    async def test_require_permission_with_tenant_bypass_normal_user(self):
        """Test permission check falls back to normal check for non-superuser"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock get_async_session dependency
            with patch("src.core.auth.dependencies.get_db") as mock_get_async_session:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_get_async_session.return_value = mock_session

                # Mock database query result for normal user
                mock_user = MagicMock(spec=User)
                mock_user.id = 123
                mock_user.is_superuser = False
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_user
                # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                # Zonder deze routering levert die query ook `mock_result` op en concludeert
                # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                mock_sessie_zonder_intrekking(mock_session, mock_result)

                # Mock tenant context
                with patch(
                    "src.core.auth.dependencies.require_tenant_id"
                ) as mock_require_tenant_id:
                    mock_require_tenant_id.return_value = 1

                    # Mock database query for tenant check
                    mock_user2 = MagicMock(spec=User)
                    mock_user2.id = 123
                    mock_user2.tenant_id = 1
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none.return_value = mock_user2
                    mock_session.execute.return_value = mock_result2

                    # Mock RBAC service
                    with patch("src.core.auth.dependencies.RBACService") as mock_rbac_service_class:
                        mock_rbac_service = MagicMock()
                        mock_rbac_service.has_permission = AsyncMock(return_value=True)
                        mock_rbac_service_class.return_value = mock_rbac_service

                        # Create permission checker without superuser bypass
                        permission_checker = require_permission_with_tenant_bypass(
                            Permission.READ, allow_super_admin=True
                        )

                        # Call the inner function
                        result = await permission_checker(user_id=123, session=mock_session)

                        assert result == 123

    @pytest.mark.asyncio
    async def test_require_permission_with_tenant_bypass_user_not_found(self):
        """Test permission check fails when user not found"""
        # Mock get_current_user_id dependency
        with patch("src.core.auth.dependencies.get_current_user_id") as mock_get_current_user_id:
            mock_get_current_user_id.return_value = 123

            # Mock get_async_session dependency
            with patch("src.core.auth.dependencies.get_db") as mock_get_async_session:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_get_async_session.return_value = mock_session

                # Mock database query result - user not found
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                # OP-260: beide auth-ingangen raadplegen sinds 2026-09-19 EERST de blacklist.
                # Zonder deze routering levert die query ook `mock_result` op en concludeert
                # de code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
                mock_sessie_zonder_intrekking(mock_session, mock_result)

                # Create permission checker with superuser bypass
                permission_checker = require_permission_with_tenant_bypass(
                    Permission.ADMIN, allow_super_admin=True
                )

                with pytest.raises(HTTPException) as exc_info:
                    await permission_checker(user_id=123, session=mock_session)

                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
                assert exc_info.value.detail == "User not found"


class TestModuleExports:
    """Test module exports"""

    def test_get_current_user_exported(self):
        """Test that get_current_user is exported"""
        from src.core.auth.dependencies import get_current_user as imported_get_current_user

        assert imported_get_current_user is get_current_user

    def test_get_current_user_dependency_exported(self):
        """Test that get_current_user_dependency is exported"""
        from src.core.auth.dependencies import (
            get_current_user_dependency as imported_get_current_user_dependency,
        )

        assert imported_get_current_user_dependency is get_current_user_dependency

    def test_get_current_user_id_exported(self):
        """Test that get_current_user_id is exported"""
        from src.core.auth.dependencies import get_current_user_id as imported_get_current_user_id

        assert imported_get_current_user_id is get_current_user_id

    def test_require_permission_exported(self):
        """Test that require_permission is exported"""
        from src.core.auth.dependencies import require_permission as imported_require_permission

        assert imported_require_permission is require_permission

    def test_require_permission_with_tenant_bypass_exported(self):
        """Test that require_permission_with_tenant_bypass is exported"""
        from src.core.auth.dependencies import (
            require_permission_with_tenant_bypass as imported_require_permission_with_tenant_bypass,
        )

        assert (
            imported_require_permission_with_tenant_bypass is require_permission_with_tenant_bypass
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
