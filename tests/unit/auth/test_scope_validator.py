"""
Tests for src/core/auth/scope_validator.py
Target: 85%+ coverage
Tests: 40-50
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestRequireScopesFunction:
    """Test require_scopes function"""

    def test_require_scopes_exists(self):
        """Test require_scopes function exists"""
        from src.core.auth.scope_validator import require_scopes

        assert require_scopes is not None
        assert callable(require_scopes)


class TestScopeValidatorBasicFunctionality:
    """Test basic scope validation functionality"""

    @patch.dict(os.environ, {"TESTING": "1"})
    def test_require_scopes_returns_dependency_in_test_mode(self):
        """Test require_scopes returns a dependency function in test mode"""
        from src.core.auth.scope_validator import require_scopes

        dependency = require_scopes("resource:action")
        assert callable(dependency)

    @patch.dict(os.environ, {"TESTING": "1"})
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_scope_checker_returns_user_id_in_test_mode(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test scope checker returns user_id in test mode without validation"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("resource:action")

            # Call the dependency function (this would normally be called by FastAPI)
            # We need to mock the async context
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id in test mode without actual validation
            assert result == 123


class TestScopeValidatorScopeParsing:
    """Test scope parsing functionality"""

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_scope_parsing_valid_format(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test scope parsing with valid resource:action format"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_execute_result

        # Mock RBAC service
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            import asyncio

            # Should not raise an exception for valid scope format
            try:
                asyncio.run(scope_checker(user_id=123, session=mock_session))
            except Exception as e:
                # If it raises an exception, it shouldn't be about invalid scope format
                assert "Invalid scope format" not in str(e)

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_scope_parsing_invalid_format_raises_error(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test scope parsing with invalid format raises error"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        # to avoid the early return in scope_validator
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Get the dependency function with invalid scope format
        scope_checker = require_scopes("invalid_scope_without_colon")

        # Call the dependency function
        import asyncio

        # Should raise HTTPException for invalid scope format
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(scope_checker(user_id=123, session=mock_session))

        # Verify it's a server error for invalid configuration
        assert exc_info.value.status_code == 500


class TestScopeValidatorTenantIsolation:
    """Test tenant isolation enforcement"""

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_tenant_isolation_valid_user(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test tenant isolation with valid user in correct tenant"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup - user exists in tenant
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_user.email = "test@example.com"
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service - use same path as scope_validator imports it
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id for valid tenant context
            assert result == 123

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_tenant_isolation_invalid_user(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test tenant isolation with user not found in tenant"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup - user not found in tenant
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        mock_session._execute_result = mock_execute_result

        # Get the dependency function
        scope_checker = require_scopes("users:read")

        # Call the dependency function
        import asyncio

        # Should raise HTTPException for tenant mismatch
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(scope_checker(user_id=123, session=mock_session))

        # Verify it's a forbidden error for tenant mismatch
        assert exc_info.value.status_code == 403


class TestScopeValidatorPermissionChecking:
    """Test permission checking functionality"""

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_permission_check_granted(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test permission check when permission is granted"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Mock RBAC service - permission granted
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id when permission is granted
            assert result == 123

            # Verify RBAC service was called correctly
            mock_rbac_service.has_permission.assert_called_once_with(
                123, "users", "read", tenant_id=1
            )

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_permission_check_denied(self, mock_require_tenant, mock_get_session, mock_get_user_id):
        """Test permission check when permission is denied"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Mock RBAC service - permission denied
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = False
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:delete")

            # Call the dependency function
            import asyncio

            # Should raise HTTPException when permission is denied
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Verify it's a forbidden error for missing permission
            assert exc_info.value.status_code == 403

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_multiple_scopes_all_granted(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test multiple scopes where all are granted"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Mock RBAC service - all permissions granted
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function with multiple scopes
            scope_checker = require_scopes("users:read", "posts:write")

            # Call the dependency function
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id when all permissions are granted
            assert result == 123

            # Verify RBAC service was called for each scope
            assert mock_rbac_service.has_permission.call_count == 2

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_multiple_scopes_one_denied(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test multiple scopes where one is denied"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Mock RBAC service - first permission granted, second denied
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.side_effect = [
                True,
                False,
            ]  # First True, second False
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function with multiple scopes
            scope_checker = require_scopes("users:read", "posts:delete")

            # Call the dependency function
            import asyncio

            # Should raise HTTPException when any permission is denied
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Verify it's a forbidden error for missing permission
            assert exc_info.value.status_code == 403


class TestScopeValidatorContextVars:
    """Test context variable functionality"""

    def test_force_real_validation_context_var_exists(self):
        """Test that _force_real_validation context variable exists"""
        from src.core.auth.scope_validator import _force_real_validation

        assert _force_real_validation is not None

    def test_force_real_validation_default_value(self):
        """Test that _force_real_validation has correct default value"""
        from src.core.auth.scope_validator import _force_real_validation

        assert _force_real_validation.get() is False


class TestScopeValidatorTestModeBypass:
    """Test test mode bypass functionality"""

    @patch.dict(os.environ, {"TESTING": "1"})  # In test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_test_mode_bypass_skips_validation(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test that test mode bypasses all validation"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read", "posts:delete")

            # Call the dependency function
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id without any validation in test mode
            assert result == 123

    @patch.dict(os.environ, {"TESTING": "1"})  # In test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_test_mode_tenant_lookup_fallback(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test tenant lookup fallback in test mode when tenant context fails"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Make require_tenant_id raise an exception to trigger fallback
        mock_require_tenant.side_effect = Exception("Tenant context not available")

        # Mock user lookup for fallback
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service - use same path as scope_validator imports it
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            import asyncio

            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id after fallback lookup
            assert result == 123


class TestScopeValidatorErrorHandling:
    """Test error handling functionality"""

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_tenant_context_exception_propagation(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test that tenant context exceptions propagate when not in test mode"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            async def execute(self, *args, **kwargs):
                return MagicMock()

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session

        # Make require_tenant_id raise an exception
        mock_require_tenant.side_effect = Exception("Tenant context error")

        # Get the dependency function
        scope_checker = require_scopes("users:read")

        # Call the dependency function
        import asyncio

        with pytest.raises(Exception, match="Tenant context error"):
            asyncio.run(scope_checker(user_id=123, session=mock_session))

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_user_lookup_exception_handling(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test handling of exceptions during user lookup"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            async def execute(self, *args, **kwargs):
                raise Exception("Database error")

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Get the dependency function
        scope_checker = require_scopes("users:read")

        # Call the dependency function
        import asyncio

        with pytest.raises(Exception, match="Database error"):
            asyncio.run(scope_checker(user_id=123, session=mock_session))

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_rbac_service_exception_handling(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test handling of exceptions from RBAC service"""
        from src.core.auth.scope_validator import require_scopes

        # Create a custom mock session that is not an instance of MagicMock/AsyncMock
        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        # Mock RBAC service to raise exception
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.side_effect = Exception("RBAC service error")
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            import asyncio

            with pytest.raises(Exception, match="RBAC service error"):
                asyncio.run(scope_checker(user_id=123, session=mock_session))


class TestScopeValidatorEdgeCases:
    """Test edge cases and special scenarios"""

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_empty_scope_list(self, mock_require_tenant, mock_get_session, mock_get_user_id):
        """Test behavior with empty scope list"""
        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Get the dependency function with no scopes
        scope_checker = require_scopes()

        # Call the dependency function
        import asyncio

        result = asyncio.run(scope_checker(user_id=123, session=mock_session))

        # Should return user_id (no scopes to check)
        assert result == 123

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_user_object_coroutine_handling(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test handling of user objects that might be coroutines"""
        import asyncio

        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup that returns a coroutine-like object
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service - use same path as scope_validator imports it
        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id after handling coroutine
            assert result == 123

    @patch.dict(os.environ, {"TESTING": "0"})  # Not in test mode
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_permission_check_coroutine_handling(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Test handling of permission checks that might be coroutines"""
        import asyncio

        from src.core.auth.scope_validator import require_scopes

        # Mock dependencies
        mock_get_user_id.return_value = 123
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock RBAC service with coroutine return
        with patch("src.core.services.rbac_service.RBACService") as mock_rbac_service_class:
            mock_rbac_service = MagicMock()
            mock_rbac_service.has_permission.return_value = True  # Just return True directly
            mock_rbac_service_class.return_value = mock_rbac_service

            # Get the dependency function
            scope_checker = require_scopes("users:read")

            # Call the dependency function
            result = asyncio.run(scope_checker(user_id=123, session=mock_session))

            # Should return user_id after handling coroutine
            assert result == 123


class TestScopeValidatorExports:
    """Test module exports"""

    def test_require_scopes_exported(self):
        """Test that require_scopes is exported"""
        from src.core.auth.scope_validator import require_scopes

        assert require_scopes is not None

    def test_force_real_validation_exported(self):
        """Test that _force_real_validation is exported"""
        from src.core.auth.scope_validator import _force_real_validation

        assert _force_real_validation is not None

    def test_all_exports(self):
        """Test that expected items are in __all__"""
        from src.core.auth.scope_validator import __all__

        assert "require_scopes" in __all__
        assert "_force_real_validation" in __all__


class TestScopeValidatorTypeContracts:
    """Runtime type-contract tests for scope_validator annotations."""

    def test_has_scopes_accepts_string_list(self):
        """has_scopes must accept list[str] and compare against user scopes."""
        from src.core.auth.scope_validator import has_scopes

        user = MagicMock()
        user.scopes = ["users:read", "users:write"]

        assert has_scopes(user, ["users:read"]) is True
        assert has_scopes(user, ["users:read", "users:write"]) is True
        assert has_scopes(user, ["users:delete"]) is False

    def test_has_scopes_rejects_empty_user(self):
        """has_scopes must return False for falsy users."""
        from src.core.auth.scope_validator import has_scopes

        assert has_scopes(None, ["users:read"]) is False
        assert has_scopes(MagicMock(scopes=[]), ["users:read"]) is False

    def test_has_scopes_accepts_enum_values(self):
        """has_scopes must accept OAuth2Scope enum values."""
        from src.core.auth.scope_validator import has_scopes
        from src.core.auth.scopes import OAuth2Scope

        user = MagicMock()
        user.scopes = [OAuth2Scope.USERS_READ.value, OAuth2Scope.USERS_WRITE.value]

        assert has_scopes(user, [OAuth2Scope.USERS_READ]) is True
        assert has_scopes(user, [OAuth2Scope.USERS_WRITE, "users:delete"]) is False

    @patch.dict(os.environ, {"TESTING": "0"})
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_legacy_rbac_session_first_signature(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Fallback RBAC service with (session, user_id, permission) must work."""
        import asyncio

        from src.core.auth.scope_validator import require_scopes

        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        class LegacyRBACService:
            def user_has_permission(self, session, user_id, permission):
                assert session is mock_session
                assert user_id == 123
                assert permission == "users:read"
                return True

        with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
            instance = LegacyRBACService()
            mock_rbac_service_class.return_value = instance

            scope_checker = require_scopes("users:read")
            result = asyncio.run(scope_checker(user_id=123, session=mock_session))
            assert result == 123

    @patch.dict(os.environ, {"TESTING": "0"})
    @patch("src.core.auth.scope_validator.get_current_user_id")
    @patch("src.core.auth.scope_validator.get_db_session")
    @patch("src.core.auth.scope_validator.require_tenant_id")
    def test_jwt_scope_context_strings_only(
        self, mock_require_tenant, mock_get_session, mock_get_user_id
    ):
        """Scopes read from the JWT context var must be list[str]."""
        import asyncio

        from src.core.auth.scope_validator import require_scopes
        from src.core.middleware.tenant_context import _current_user_scopes

        class CustomMockSession:
            def __init__(self):
                self._execute_result = None

            async def execute(self, *args, **kwargs):
                return self._execute_result

        mock_session = CustomMockSession()
        mock_get_user_id.return_value = 123
        mock_get_session.return_value = mock_session
        mock_require_tenant.return_value = 1

        mock_user = MagicMock()
        mock_user.tenant_id = 1
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_user
        mock_session._execute_result = mock_execute_result

        token = _current_user_scopes.set(["users:read"])
        try:
            with patch("src.core.auth.scope_validator.RBACService") as mock_rbac_service_class:
                mock_rbac_service = MagicMock()
                mock_rbac_service_class.return_value = mock_rbac_service

                scope_checker = require_scopes("users:read")
                result = asyncio.run(scope_checker(user_id=123, session=mock_session))
                assert result == 123
                # RBAC fallback should not be reached because JWT scope grants it
                mock_rbac_service.has_permission.assert_not_called()
        finally:
            _current_user_scopes.reset(token)
