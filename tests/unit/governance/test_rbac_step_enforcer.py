"""
Unit tests for RBAC Step Enforcer - Slice 5

Tests fine-grained access control per workflow step.
Sprint 4 - S4.5: RBAC per procedure step
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


@pytest.fixture
def mock_policy_engine():
    """Mock PolicyEngine for testing."""
    engine = Mock()
    engine.check_permission = Mock()
    return engine


class TestRBACStepEnforcer:
    """Test suite for RBAC step enforcement."""

    def test_user_with_role_allowed(self, mock_policy_engine):
        """User with 'Finance Manager' role should be allowed to 'Approve'."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock user with Finance Manager role
        user = Mock()
        user.id = 1
        user.roles = ["Finance Manager"]
        user.tenant_id = 1

        # Mock step requiring Finance Manager role
        step = {
            "step_name": "approve_invoice",
            "required_roles": ["Finance Manager", "CFO"],
        }

        # Mock policy engine allows access
        mock_policy_engine.check_permission.return_value = True

        # Check permission
        result = enforcer.check_step_permission(user, step, tenant_id=1)

        assert result is True
        mock_policy_engine.check_permission.assert_called_once()

    def test_user_without_role_denied(self, mock_policy_engine):
        """User without required role should get RoleViolationError."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer, RoleViolationError

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock user without Finance Manager role
        user = Mock()
        user.id = 2
        user.roles = ["Employee"]
        user.tenant_id = 1

        # Mock step requiring Finance Manager role
        step = {
            "step_name": "approve_invoice",
            "required_roles": ["Finance Manager", "CFO"],
        }

        # Mock policy engine denies access
        mock_policy_engine.check_permission.return_value = False

        # Check permission - should raise error
        with pytest.raises(RoleViolationError) as exc_info:
            enforcer.check_step_permission(user, step, tenant_id=1)

        assert "User 2 lacks required roles" in str(exc_info.value)
        assert "approve_invoice" in str(exc_info.value)

    def test_cross_tenant_denial(self, mock_policy_engine):
        """User from Tenant A should not execute step from Tenant B."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer, TenantViolationError

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock user from Tenant 1
        user = Mock()
        user.id = 1
        user.tenant_id = 1
        user.roles = ["Finance Manager"]

        # Mock step from Tenant 2
        step = {"step_name": "approve_invoice", "required_roles": ["Finance Manager"]}

        # Check permission for Tenant 2 - should raise error
        with pytest.raises(TenantViolationError) as exc_info:
            enforcer.check_step_permission(user, step, tenant_id=2)

        assert "User from tenant 1 cannot access resources in tenant 2" in str(exc_info.value)

    def test_superadmin_bypass(self, mock_policy_engine):
        """SuperAdmin should bypass all role checks."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock superadmin user
        user = Mock()
        user.id = 1
        user.roles = ["SuperAdmin"]
        user.tenant_id = 1

        # Mock step with restrictive roles
        step = {"step_name": "delete_all_data", "required_roles": ["Owner"]}

        # SuperAdmin should be allowed
        result = enforcer.check_step_permission(user, step, tenant_id=1)

        assert result is True

    def test_multiple_roles_any_match(self, mock_policy_engine):
        """User with ANY of required roles should be allowed."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock user with one of required roles
        user = Mock()
        user.id = 1
        user.roles = ["CFO"]  # Not Finance Manager, but CFO is also allowed
        user.tenant_id = 1

        # Mock step requiring either Finance Manager or CFO
        step = {
            "step_name": "approve_invoice",
            "required_roles": ["Finance Manager", "CFO"],
        }

        # Mock policy engine allows access
        mock_policy_engine.check_permission.return_value = True

        result = enforcer.check_step_permission(user, step, tenant_id=1)

        assert result is True

    def test_no_required_roles_allows_all(self, mock_policy_engine):
        """Step with no required roles should allow all users."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock any user
        user = Mock()
        user.id = 1
        user.roles = ["Employee"]
        user.tenant_id = 1

        # Mock step with no role requirements
        step = {"step_name": "view_dashboard", "required_roles": []}

        result = enforcer.check_step_permission(user, step, tenant_id=1)

        assert result is True

    def test_audit_logging_on_denial(self, mock_policy_engine):
        """Access denials should be logged for audit."""
        from src.core.governance.rbac_step_enforcer import RBACStepEnforcer, RoleViolationError

        enforcer = RBACStepEnforcer(policy_engine=mock_policy_engine)

        # Mock user without required role
        user = Mock()
        user.id = 5
        user.roles = ["Employee"]
        user.tenant_id = 1

        # Mock step requiring admin
        step = {"step_name": "delete_user", "required_roles": ["Admin"]}

        # Mock policy engine denies
        mock_policy_engine.check_permission.return_value = False

        # Capture audit log
        with pytest.raises(RoleViolationError):
            enforcer.check_step_permission(user, step, tenant_id=1)

        # Verify audit was logged (enforcer should have logged this)
        assert enforcer.last_denial is not None
        assert enforcer.last_denial["user_id"] == 5
        assert enforcer.last_denial["step_name"] == "delete_user"
