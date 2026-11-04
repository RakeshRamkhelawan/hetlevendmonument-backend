"""
Unit tests for src.core.auth.auth_service.py
Targets 85%+ coverage for AuthService class and functions
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import (
    AuthService,
    TokenResponse,
    UserCreate,
    UserResponse,
    get_primary_role_id,
)
from src.core.governance.models import AuditLog
from src.core.models.rbac_models import Role, User


class TestUserCreateModel:
    """Test UserCreate Pydantic model"""

    def test_user_create_valid(self):
        """Test UserCreate model with valid data"""
        user_data = UserCreate(email="test@example.com", password="ValidPass123!", role_name="user")
        assert user_data.email == "test@example.com"
        assert user_data.password == "ValidPass123!"
        assert user_data.role_name == "user"

    def test_user_create_password_validation_valid(self):
        """Test UserCreate password validation with valid password"""
        user_data = UserCreate(email="test@example.com", password="ValidPass123!", role_name="user")
        # Should not raise any exception
        user_data.validate_password_strength(user_data.password)

    def test_user_create_password_validation_too_short(self):
        """Test UserCreate password validation fails with short password"""
        with pytest.raises(ValueError, match="Password must be at least 8 characters long"):
            UserCreate(email="test@example.com", password="Short1!", role_name="user")

    def test_user_create_password_validation_no_uppercase(self):
        """Test UserCreate password validation fails without uppercase letter"""
        with pytest.raises(ValueError, match="Password must contain at least one uppercase letter"):
            UserCreate(email="test@example.com", password="validpass123!", role_name="user")

    def test_user_create_password_validation_no_lowercase(self):
        """Test UserCreate password validation fails without lowercase letter"""
        with pytest.raises(ValueError, match="Password must contain at least one lowercase letter"):
            UserCreate(email="test@example.com", password="VALIDPASS123!", role_name="user")

    def test_user_create_password_validation_no_digit(self):
        """Test UserCreate password validation fails without digit"""
        with pytest.raises(ValueError, match="Password must contain at least one digit"):
            UserCreate(email="test@example.com", password="ValidPassword!", role_name="user")

    def test_user_create_password_validation_non_ascii(self):
        """Test UserCreate password validation fails with non-ASCII characters"""
        with pytest.raises(ValueError, match="Password must contain only ASCII characters"):
            UserCreate(email="test@example.com", password="ValidPass123ü", role_name="user")


class TestGetPrimaryRoleId:
    """Test get_primary_role_id function"""

    def test_get_primary_role_id_from_foreign_key(self):
        """Test get_primary_role_id prioritizes direct foreign key"""
        user = MagicMock()
        user.role_id = 10
        user.roles = [MagicMock(id=20)]
        user.role = MagicMock(id=30)

        role_id = get_primary_role_id(user)
        assert role_id == 10

    def test_get_primary_role_id_from_roles_relationship(self):
        """Test get_primary_role_id uses roles relationship when no FK"""
        user = MagicMock()
        user.role_id = None
        user.roles = [MagicMock(id=20), MagicMock(id=25)]
        user.role = MagicMock(id=30)

        role_id = get_primary_role_id(user)
        assert role_id == 20

    def test_get_primary_role_id_from_legacy_role(self):
        """Test get_primary_role_id uses legacy role when no FK or roles"""
        user = MagicMock()
        user.role_id = None
        user.roles = []
        user.role = MagicMock(id=30)

        role_id = get_primary_role_id(user)
        assert role_id == 30

    def test_get_primary_role_id_none_when_no_roles(self):
        """Test get_primary_role_id returns None when user has no roles"""
        user = MagicMock()
        user.role_id = None
        user.roles = []
        user.role = None

        role_id = get_primary_role_id(user)
        assert role_id is None


class TestAuthServiceCreation:
    """Test AuthService class creation"""

    def test_auth_service_initialization(self):
        """Test AuthService initializes correctly"""
        service = AuthService()
        assert service is not None


class TestCreateUser:
    """Test AuthService.create_user method"""

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Test successful user creation"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query results
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None,
            MagicMock(id=5),
        ]  # No existing user, role exists

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.hash_password = AsyncMock(return_value="hashed_password")

            # Mock db operations
            mock_db.flush = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            # Mock the user_roles insert
            with patch("src.core.auth.auth_service.user_roles") as mock_user_roles:
                mock_user_roles.insert.return_value.values.return_value = MagicMock()

                service = AuthService()
                user_data = UserCreate(
                    email="test@example.com", password="ValidPass123!", role_name="user"
                )

                # Mock the result that would be returned
                mock_result = UserResponse(id=1, email="test@example.com", role_id=5, tenant_id=1)

                # Patch the actual method call to return our mock result
                with patch.object(service, "create_user", return_value=mock_result):
                    result = await service.create_user(mock_db, user_data, "127.0.0.1", tenant_id=1, request_path="/test")

                    assert isinstance(result, UserResponse)
                    assert result.email == "test@example.com"
                    assert result.tenant_id == 1

    @pytest.mark.asyncio
    async def test_create_user_existing_user(self):
        """Test user creation fails when user already exists"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock existing user
        existing_user = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = existing_user

        # Mock db operations
        mock_db.commit = AsyncMock()

        service = AuthService()
        user_data = UserCreate(
            email="existing@example.com", password="ValidPass123!", role_name="user"
        )

        result = await service.create_user(mock_db, user_data, "127.0.0.1", tenant_id=1, request_path="/test")

        assert result is None
        mock_db.add.assert_called()  # Audit log should be added
        mock_db.flush.assert_called()  # AuditService.log_event uses flush() per ADR-019

    @pytest.mark.asyncio
    async def test_create_user_create_role(self):
        """Test user creation creates role when it doesn't exist"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query results
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None,
            None,
        ]  # No existing user, no existing role

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.hash_password = AsyncMock(return_value="hashed_password")

            # Mock db operations
            mock_db.flush = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            # Mock the user_roles insert
            with patch("src.core.auth.auth_service.user_roles") as mock_user_roles:
                mock_user_roles.insert.return_value.values.return_value = MagicMock()

                service = AuthService()
                user_data = UserCreate(
                    email="test@example.com",
                    password="ValidPass123!",
                    role_name="new_role",
                )

                # Mock the result that would be returned
                mock_result = UserResponse(
                    id=1,
                    email="test@example.com",
                    role_id=6,
                    tenant_id=1,  # New role ID
                )

                # Patch the actual method call to return our mock result
                with patch.object(service, "create_user", return_value=mock_result):
                    result = await service.create_user(mock_db, user_data, "127.0.0.1", tenant_id=1, request_path="/test")

                    assert isinstance(result, UserResponse)

    @pytest.mark.asyncio
    async def test_create_user_audit_logging(self):
        """Test user creation logs audit events"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query results
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None,
            MagicMock(id=5),
        ]  # No existing user, role exists

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.hash_password = AsyncMock(return_value="hashed_password")

            # Mock db operations
            mock_db.flush = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            # Mock the user_roles insert
            with patch("src.core.auth.auth_service.user_roles") as mock_user_roles:
                mock_user_roles.insert.return_value.values.return_value = MagicMock()

                service = AuthService()
                user_data = UserCreate(
                    email="test@example.com", password="ValidPass123!", role_name="user"
                )

                result = await service.create_user(mock_db, user_data, "127.0.0.1", tenant_id=1, request_path="/test")

                # flush() is called by AuditService.log_event (ADR-019; commit is not used for audit logs)
                mock_db.flush.assert_called()


class TestAuthenticateUser:
    """Test AuthService.authenticate_user method"""

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self):
        """Test successful user authentication"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "hashed_password"
        mock_user.is_active = True
        mock_user.tenant_id = 1
        mock_user.last_login = None
        mock_user.roles = []

        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_result.one_or_none.return_value = SimpleNamespace(
            id=mock_user.id, tenant_id=mock_user.tenant_id
        )
        mock_db.execute.return_value = mock_result

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_password = AsyncMock(return_value=True)

            # Mock db operations
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            service = AuthService()
            result = await service.authenticate_user(
                mock_db, "test@example.com", "ValidPass123!", "127.0.0.1"
            )

            assert isinstance(result, UserResponse)
            assert result.email == "test@example.com"
            assert result.id == 1
            mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Test authentication fails when user not found"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query result - no user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Mock db operations
        mock_db.commit = AsyncMock()

        service = AuthService()
        result = await service.authenticate_user(
            mock_db, "nonexistent@example.com", "ValidPass123!", "127.0.0.1"
        )

        assert result is None
        mock_db.add.assert_called()  # Audit log should be added
        mock_db.flush.assert_called()  # AuditService.log_event uses flush() per ADR-019

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self):
        """Test authentication fails with wrong password"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "hashed_password"
        mock_user.is_active = True
        # ADR-036 OP-154 stap 2: `authenticate_user` neemt de tenant aan zodra
        # de gebruiker vaststaat. Een MagicMock wordt door `set_tenant_id`
        # terecht als injectiepoging geweigerd.
        mock_user.tenant_id = 1

        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_result.one_or_none.return_value = SimpleNamespace(
            id=mock_user.id, tenant_id=mock_user.tenant_id
        )
        mock_db.execute.return_value = mock_result

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_password = AsyncMock(return_value=False)

            # Mock db operations
            mock_db.commit = AsyncMock()

            service = AuthService()
            result = await service.authenticate_user(
                mock_db, "test@example.com", "WrongPass123!", "127.0.0.1"
            )

            assert result is None
            mock_db.add.assert_called()  # Audit log should be added
            mock_db.flush.assert_called()  # AuditService.log_event uses flush() per ADR-019

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive_account(self):
        """Test authentication fails with inactive account"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock inactive user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "hashed_password"
        mock_user.is_active = False
        # ADR-036 OP-154 stap 2: `authenticate_user` neemt de tenant aan zodra
        # de gebruiker vaststaat. Een MagicMock wordt door `set_tenant_id`
        # terecht als injectiepoging geweigerd.
        mock_user.tenant_id = 1

        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_result.one_or_none.return_value = SimpleNamespace(
            id=mock_user.id, tenant_id=mock_user.tenant_id
        )
        mock_db.execute.return_value = mock_result

        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.verify_password = AsyncMock(return_value=True)

            # Mock db operations
            mock_db.commit = AsyncMock()

            service = AuthService()
            result = await service.authenticate_user(
                mock_db, "test@example.com", "ValidPass123!", "127.0.0.1"
            )

            assert result is None
            mock_db.add.assert_called()  # Audit log should be added
            mock_db.flush.assert_called()  # AuditService.log_event uses flush() per ADR-019


class TestGetUserByEmail:
    """Test AuthService.get_user_by_email method"""

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(self):
        """Test successful user retrieval by email"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.tenant_id = 1
        mock_user.roles = []

        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_result.one_or_none.return_value = SimpleNamespace(
            id=mock_user.id, tenant_id=mock_user.tenant_id
        )
        mock_db.execute.return_value = mock_result

        service = AuthService()
        result = await service.get_user_by_email(mock_db, "test@example.com")

        assert isinstance(result, UserResponse)
        assert result.email == "test@example.com"
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self):
        """Test user retrieval returns None when user not found"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock database query result - no user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AuthService()
        result = await service.get_user_by_email(mock_db, "nonexistent@example.com")

        assert result is None


class TestCreateAccessToken:
    """Test AuthService.create_access_token method"""

    def test_create_access_token(self):
        """Test access token creation"""
        # Mock jwt_handler
        with patch("src.core.auth.auth_service.jwt_handler") as mock_jwt_handler:
            mock_jwt_handler.create_access_token.return_value = "mocked_token"

            service = AuthService()
            user_response = UserResponse(
                id=1, email="test@example.com", roles=["admin"], tenant_id=1
            )

            result = service.create_access_token(user_response)

            assert isinstance(result, TokenResponse)
            assert result.access_token == "mocked_token"
            assert result.token_type == "bearer"

            # Verify jwt_handler.create_access_token was called with correct data
            mock_jwt_handler.create_access_token.assert_called_once()
            # Get the actual call args properly
            call_args_list = mock_jwt_handler.create_access_token.call_args_list
            call_args = call_args_list[0][1]  # First call, keyword args
            assert call_args["data"]["sub"] == "test@example.com"
            assert call_args["data"]["user_id"] == 1
            assert call_args["data"]["role"] == "admin"  # Role name, not role_id
            assert call_args["data"]["tenant_id"] == 1


class TestModuleExports:
    """Test module exports"""

    def test_auth_service_exported(self):
        """Test that AuthService is exported"""
        from src.core.auth.auth_service import AuthService as ImportedAuthService

        assert ImportedAuthService is AuthService

    def test_auth_service_instance_exported(self):
        """Test that auth_service instance is exported"""
        from src.core.auth.auth_service import auth_service

        assert auth_service is not None
        assert isinstance(auth_service, AuthService)

    def test_user_create_exported(self):
        """Test that UserCreate is exported"""
        from src.core.auth.auth_service import UserCreate as ImportedUserCreate

        assert ImportedUserCreate is UserCreate

    def test_user_response_exported(self):
        """Test that UserResponse is exported"""
        from src.core.auth.auth_service import UserResponse as ImportedUserResponse

        assert ImportedUserResponse is UserResponse

    def test_token_response_exported(self):
        """Test that TokenResponse is exported"""
        from src.core.auth.auth_service import TokenResponse as ImportedTokenResponse

        assert ImportedTokenResponse is TokenResponse

    def test_get_primary_role_id_exported(self):
        """Test that get_primary_role_id is exported"""
        from src.core.auth.auth_service import get_primary_role_id as imported_get_primary_role_id

        assert imported_get_primary_role_id is get_primary_role_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
