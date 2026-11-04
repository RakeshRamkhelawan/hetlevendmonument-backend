"""
Security-focused unit tests for scope_validator
Tests for SEC-004: TESTING Environment Bypass Removal
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status


class TestTestingBypassRemoved:
    """Test that TESTING=1 no longer bypasses security (SEC-004)"""

    @patch.dict(os.environ, {"TESTING": "1"})
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_testing_mode_does_not_bypass_validation(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Unhappy path: TESTING=1 should NOT bypass permission checks"""
        from src.core.auth.scope_validator import require_scopes

        # Setup mocks
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup - user exists
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service - permission DENIED
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = False
            mock_rbac_service_class.return_value = mock_rbac_service

            scope_checker = require_scopes("sensitive:admin")

            # Should raise HTTPException even with TESTING=1
            with pytest.raises(HTTPException) as exc_info:
                await scope_checker(user_id=123, session=mock_session)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @patch.dict(os.environ, {"TESTING": "1"})
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_testing_mode_still_requires_tenant_context(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Unhappy path: TESTING=1 should still require tenant context"""
        from src.core.auth.scope_validator import require_scopes

        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Tenant context fails
        mock_require_tenant.side_effect = Exception("No tenant context")

        scope_checker = require_scopes("users:read")

        # Should raise HTTPException when tenant context is missing
        with pytest.raises(HTTPException) as exc_info:
            await scope_checker(user_id=123, session=mock_session)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestProperAuthorization:
    """Test that authorization works correctly without bypass"""

    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_valid_user_with_permission_granted(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Happy path: Valid user with proper permissions"""
        from src.core.auth.scope_validator import require_scopes

        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # User exists in correct tenant
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Permission granted
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            scope_checker = require_scopes("users:read")
            result = await scope_checker(user_id=123, session=mock_session)

            assert result == 123

    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_valid_user_with_permission_denied(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Unhappy path: Valid user but permission denied"""
        from src.core.auth.scope_validator import require_scopes

        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # User exists
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Permission DENIED
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = False
            mock_rbac_service_class.return_value = mock_rbac_service

            scope_checker = require_scopes("admin:delete")

            with pytest.raises(HTTPException) as exc_info:
                await scope_checker(user_id=123, session=mock_session)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestTenantIsolation:
    """Test tenant isolation enforcement"""

    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_user_not_in_tenant_rejected(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Unhappy path: User not found in tenant is rejected"""
        from src.core.auth.scope_validator import require_scopes

        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # User not found in tenant
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        scope_checker = require_scopes("users:read")

        with pytest.raises(HTTPException) as exc_info:
            await scope_checker(user_id=123, session=mock_session)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestMockBasedTesting:
    """Test that proper mocking works for tests"""

    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    async def test_proper_mocking_allows_test_bypass(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Happy path: Tests can use proper mocking instead of env bypass"""
        from src.core.auth.scope_validator import require_scopes

        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user exists
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock permission granted
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            scope_checker = require_scopes("users:read")
            result = await scope_checker(user_id=123, session=mock_session)

            assert result == 123
            # Verify RBAC service was called properly
            mock_rbac_service.has_permission.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
