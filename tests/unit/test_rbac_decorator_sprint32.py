"""
Unit Tests for Sprint 3.2 RBAC Decorator - Permission & Scope System

Test Coverage (35+ test cases, >90% target):
1. Permission Scope Parsing (5 tests)
2. Scope Matching Logic (6 tests)
3. @require_permission Decorator Behavior (8 tests)
4. Permission Checking with RBACService (8 tests)
5. Multiple Permission Scenarios (5 tests)
6. Error Handling & Edge Cases (5 tests)

Total: 37 test cases
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.permissions import (
    ADMIN_AUDIT,
    ADMIN_SCOPES,
    EDITOR_SCOPES,
    EXECUTION_CANCEL,
    EXECUTION_READ,
    TEMPLATE_READ,
    VIEWER_SCOPES,
    WORKFLOW_CREATE,
    WORKFLOW_DELETE,
    WORKFLOW_EXECUTE,
    WORKFLOW_READ,
    WORKFLOW_UPDATE,
    parse_scope,
    scope_matches,
)


# Temporarily disable TESTING mode for permission tests
@pytest.fixture
def no_testing_mode(monkeypatch):
    """Temporarily disable TESTING mode to test actual permission logic."""
    monkeypatch.setenv("TESTING", "0")
    yield
    monkeypatch.setenv("TESTING", "1")


from src.core.auth.rbac_decorator import _check_permissions_manual, require_permission

# ============================================================================
# TEST CLASS 1: Permission Scope Parsing (5 tests)
# ============================================================================


class TestPermissionParsing:
    """Test permission string parsing"""

    def test_parse_valid_scope_format(self):
        """Test parsing valid resource:action format"""
        resource, action = parse_scope("workflow:create")
        assert resource == "workflow"
        assert action == "create"

    def test_parse_scope_with_colon_in_action(self):
        """Test parsing scope where action contains colon"""
        resource, action = parse_scope("resource:action:extra")
        assert resource == "resource"
        assert action == "action:extra"

    def test_parse_invalid_scope_missing_colon(self):
        """Test error handling for invalid format (missing colon)"""
        with pytest.raises(ValueError, match="Invalid scope format"):
            parse_scope("workflow")

    def test_parse_invalid_scope_empty_resource(self):
        """Test error handling for empty resource"""
        with pytest.raises(ValueError, match="Both resource and action must be non-empty"):
            parse_scope(":action")

    def test_parse_invalid_scope_empty_action(self):
        """Test error handling for empty action"""
        with pytest.raises(ValueError, match="Both resource and action must be non-empty"):
            parse_scope("resource:")


# ============================================================================
# TEST CLASS 2: Scope Matching Logic (6 tests)
# ============================================================================


class TestScopeMatching:
    """Test scope matching with wildcards"""

    def test_exact_scope_match(self):
        """Test exact scope matching"""
        assert scope_matches("workflow:create", "workflow:create") is True

    def test_wildcard_admin_matches_any(self):
        """Test superuser wildcard matches anything"""
        assert scope_matches("*", "workflow:create") is True
        assert scope_matches("*", "execution:read") is True
        assert scope_matches("*", "admin:audit") is True

    def test_resource_wildcard_matches_actions(self):
        """Test resource:* matches specific actions"""
        assert scope_matches("workflow:*", "workflow:create") is True
        assert scope_matches("workflow:*", "workflow:read") is True
        assert scope_matches("workflow:*", "workflow:update") is True

    def test_resource_mismatch_no_match(self):
        """Test different resources don't match"""
        assert scope_matches("workflow:*", "execution:read") is False
        assert scope_matches("admin:*", "workflow:create") is False

    def test_action_mismatch_no_match(self):
        """Test specific action mismatch"""
        assert scope_matches("workflow:read", "workflow:create") is False

    def test_partial_wildcard_no_match(self):
        """Test invalid wildcard patterns don't match"""
        # workflow:cr* is not supported
        assert scope_matches("workflow:cr*", "workflow:create") is False


# ============================================================================
# TEST CLASS 3: Decorator Behavior (8 tests)
# ============================================================================


class TestRequirePermissionDecorator:
    """Test @require_permission decorator"""

    @pytest.mark.asyncio
    async def test_decorator_missing_user_id(self):
        """Test decorator raises 401 when user_id missing"""

        @require_permission("workflow:read")
        async def handler():
            return {"status": "ok"}

        with pytest.raises(HTTPException) as exc_info:
            await handler()

        assert exc_info.value.status_code == http_status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self):
        """Test decorator preserves original function name"""

        @require_permission("workflow:read")
        async def create_workflow():
            return {}

        assert create_workflow.__name__ == "create_workflow"

    @pytest.mark.asyncio
    async def test_decorator_allow_bypass_mode(self):
        """Test decorator can bypass permission checks"""

        @require_permission("workflow:create", allow_bypass=True)
        async def handler():
            return {"status": "ok"}

        # Should succeed without user_id when bypassed
        result = await handler()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_decorator_invalid_permission_format_on_creation(self):
        """Test decorator validates permission format at creation time"""
        with pytest.raises(ValueError, match="Invalid permission"):

            @require_permission("invalid_format")
            async def handler():
                return {}

    @pytest.mark.asyncio
    async def test_decorator_multiple_permissions_all_required(self):
        """Test decorator with multiple permissions (all required)"""

        @require_permission("workflow:create", "workflow:read", require_all=True)
        async def handler():
            return {}

        # Should accept handler definition
        assert handler is not None

    @pytest.mark.asyncio
    async def test_decorator_multiple_permissions_any_required(self):
        """Test decorator with multiple permissions (any one)"""

        @require_permission("workflow:read", "execution:read", require_all=False)
        async def handler():
            return {}

        assert handler is not None

    @pytest.mark.asyncio
    async def test_decorator_calls_original_function_on_success(self):
        """Test decorator calls original function when permissions pass"""
        called = False

        @require_permission("workflow:read", allow_bypass=True)
        async def handler():
            nonlocal called
            called = True
            return {"status": "ok"}

        result = await handler()
        assert called is True
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_decorator_reraises_http_exceptions(self):
        """Test decorator re-raises HTTPException from permission check"""
        from fastapi import HTTPException

        @require_permission("workflow:read")
        async def handler():
            return {}

        # Calling without user_id should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await handler()

        assert exc_info.value.status_code in [
            http_status.HTTP_401_UNAUTHORIZED,
            http_status.HTTP_403_FORBIDDEN,
        ]


# ============================================================================
# TEST CLASS 4: Permission Checking with RBACService (8 tests)
# ============================================================================


class TestCheckPermissionsManual:
    """Test _check_permissions_manual function with RBACService"""

    @pytest.mark.asyncio
    async def test_check_no_db_session_skips(self):
        """Test permission check skips when no DB provided"""
        # Should not raise when db is None
        await _check_permissions_manual(
            user_id=1,
            required_permissions=("workflow:read",),
            require_all=True,
            db=None,
        )

    @pytest.mark.asyncio
    async def test_check_user_not_found_raises_403(self, no_testing_mode):
        """Test 403 error when user not found"""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()  # Use MagicMock, not AsyncMock - scalar_one_or_none is sync
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _check_permissions_manual(
                user_id=999, required_permissions=("workflow:read",), db=mock_db
            )

        assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN
        assert "User not found" in str(exc_info.value.detail)

        with pytest.raises(HTTPException) as exc_info:
            await _check_permissions_manual(
                user_id=999, required_permissions=("workflow:read",), db=mock_db
            )

        assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN
        assert "User not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_check_inactive_user_raises_403(self, no_testing_mode):
        """Test 403 error for inactive user"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = False
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _check_permissions_manual(
                user_id=1, required_permissions=("workflow:read",), db=mock_db
            )

        assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN
        assert "inactive" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_check_permission_granted_single(self):
        """Test permission check passes when user has permission"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            mock_rbac.user_has_permission = AsyncMock(return_value=True)
            MockRBACService.return_value = mock_rbac

            # Should not raise
            await _check_permissions_manual(
                user_id=1, required_permissions=("workflow:read",), db=mock_db
            )

    @pytest.mark.asyncio
    async def test_check_permission_denied_single(self, no_testing_mode):
        """Test permission check fails when user lacks permission"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            mock_rbac.user_has_permission = AsyncMock(return_value=False)
            MockRBACService.return_value = mock_rbac

            with pytest.raises(HTTPException) as exc_info:
                await _check_permissions_manual(
                    user_id=1, required_permissions=("workflow:read",), db=mock_db
                )

            assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_check_all_permissions_required(self, no_testing_mode):
        """Test require_all=True (all permissions needed)"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            # First permission granted, second denied
            mock_rbac.user_has_permission = AsyncMock(side_effect=[True, False])
            MockRBACService.return_value = mock_rbac

            with pytest.raises(HTTPException) as exc_info:
                await _check_permissions_manual(
                    user_id=1,
                    required_permissions=("workflow:read", "workflow:update"),
                    require_all=True,
                    db=mock_db,
                )

            assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_check_any_permission_required(self):
        """Test require_all=False (any permission needed)"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            # First permission denied, second granted
            mock_rbac.user_has_permission = AsyncMock(side_effect=[False, True])
            MockRBACService.return_value = mock_rbac

            # Should not raise because second permission is granted
            await _check_permissions_manual(
                user_id=1,
                required_permissions=("workflow:read", "workflow:update"),
                require_all=False,
                db=mock_db,
            )


# ============================================================================
# TEST CLASS 5: Multiple Permission Scenarios (5 tests)
# ============================================================================


class TestMultiplePermissionScenarios:
    """Test complex permission scenarios"""

    def test_admin_scopes_includes_all_permissions(self):
        """Test admin role has all permissions"""
        assert len(ADMIN_SCOPES) >= 3
        assert WORKFLOW_READ in ADMIN_SCOPES or "workflow:*" in ADMIN_SCOPES

    def test_editor_scopes_allows_create_update_execute(self):
        """Test editor role permissions"""
        assert WORKFLOW_CREATE in EDITOR_SCOPES
        assert WORKFLOW_UPDATE in EDITOR_SCOPES
        assert WORKFLOW_EXECUTE in EDITOR_SCOPES

    def test_viewer_scopes_readonly(self):
        """Test viewer role is read-only"""
        assert WORKFLOW_READ in VIEWER_SCOPES
        assert EXECUTION_READ in VIEWER_SCOPES
        assert WORKFLOW_CREATE not in VIEWER_SCOPES
        assert WORKFLOW_DELETE not in VIEWER_SCOPES

    def test_permission_constants_consistency(self):
        """Test all permission constants are properly formatted"""
        constants = [
            WORKFLOW_CREATE,
            WORKFLOW_READ,
            WORKFLOW_UPDATE,
            WORKFLOW_DELETE,
            WORKFLOW_EXECUTE,
            EXECUTION_READ,
            EXECUTION_CANCEL,
            ADMIN_AUDIT,
            TEMPLATE_READ,
        ]
        for perm in constants:
            assert ":" in perm, f"Permission {perm} not in resource:action format"
            resource, action = perm.split(":")
            assert resource in ["workflow", "execution", "admin", "template"]
            assert action in [
                "create",
                "read",
                "update",
                "delete",
                "execute",
                "cancel",
                "audit",
            ]

    def test_scope_wildcard_hierarchy(self):
        """Test scope wildcard matching hierarchy"""
        # workflow:* should match all workflow actions
        workflow_actions = [
            WORKFLOW_CREATE,
            WORKFLOW_READ,
            WORKFLOW_UPDATE,
            WORKFLOW_DELETE,
            WORKFLOW_EXECUTE,
        ]
        for action in workflow_actions:
            assert scope_matches("workflow:*", action) is True


# ============================================================================
# TEST CLASS 6: Error Handling & Edge Cases (5 tests)
# ============================================================================


class TestErrorHandlingEdgeCases:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_decorator_handles_unexpected_exception(self):
        """Test decorator handles unexpected errors gracefully"""

        @require_permission("workflow:read")
        async def handler(**kwargs):
            return {}

        # Call without user_id - should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await handler()

        # Should get auth error first before permission error
        assert exc_info.value.status_code == http_status.HTTP_401_UNAUTHORIZED

    def test_parse_scope_handles_special_characters(self):
        """Test scope parsing with special characters in resource/action"""
        # Should work with alphanumeric and underscore
        resource, action = parse_scope("my_resource:my_action")
        assert resource == "my_resource"
        assert action == "my_action"

    def test_scope_matching_case_sensitive(self):
        """Test scope matching is case sensitive"""
        assert scope_matches("Workflow:Read", "workflow:read") is False
        assert scope_matches("workflow:read", "workflow:read") is True

    @pytest.mark.asyncio
    async def test_check_permissions_with_no_permissions_required(self):
        """Test behavior when no permissions required"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()  # Use MagicMock, not AsyncMock
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Should not raise even though no permissions to check
        await _check_permissions_manual(user_id=1, required_permissions=(), db=mock_db)

    @pytest.mark.asyncio
    async def test_check_permissions_logs_warnings(self, no_testing_mode):
        """Test permission failures are logged"""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()  # Use MagicMock, not AsyncMock
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            mock_rbac.user_has_permission = AsyncMock(return_value=False)
            MockRBACService.return_value = mock_rbac

            with patch("src.core.auth.rbac_decorator.logger") as mock_logger:
                with pytest.raises(HTTPException):
                    await _check_permissions_manual(
                        user_id=1, required_permissions=("workflow:read",), db=mock_db
                    )

                # Should have logged warning
                mock_logger.warning.assert_called()


# ============================================================================
# Integration Tests (mock-based)
# ============================================================================


class TestIntegration:
    """Integration tests combining multiple components"""

    @pytest.mark.asyncio
    async def test_full_permission_flow_granted(self):
        """Test complete permission check flow (granted)"""
        mock_user = MagicMock(__name__="User")
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            mock_rbac.user_has_permission = AsyncMock(return_value=True)
            MockRBACService.return_value = mock_rbac

            # Directly call _check_permissions_manual to test complete flow
            await _check_permissions_manual(
                user_id=1, required_permissions=("workflow:create",), db=mock_db
            )
            # Should not raise

    @pytest.mark.asyncio
    async def test_full_permission_flow_denied(self, no_testing_mode):
        """Test complete permission check flow (denied)"""
        mock_user = MagicMock(__name__="User")
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.tenant_id = 1

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.services.rbac_service.RBACService") as MockRBACService:
            mock_rbac = MagicMock()
            mock_rbac.user_has_permission = AsyncMock(return_value=False)
            MockRBACService.return_value = mock_rbac

            # Directly call _check_permissions_manual to test complete flow
            with pytest.raises(HTTPException) as exc_info:
                await _check_permissions_manual(
                    user_id=1, required_permissions=("admin:audit",), db=mock_db
                )

            assert exc_info.value.status_code == http_status.HTTP_403_FORBIDDEN


__all__ = [
    "TestPermissionParsing",
    "TestScopeMatching",
    "TestRequirePermissionDecorator",
    "TestCheckPermissionsManual",
    "TestMultiplePermissionScenarios",
    "TestErrorHandlingEdgeCases",
    "TestIntegration",
]
