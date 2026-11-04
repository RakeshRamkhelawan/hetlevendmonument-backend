"""
RBAC module tests (src/core/auth/rbac.py)

Tests for:
- Permission enum (values, serialization, comparison)
- RBACService: nog maar de tool-gatekeeper `user_has_scope_for`; de vaste rolmatrix en de
  methodes die haar lazen zijn weg (ADR-036 OP-143) -- dat wordt hier bewaakt
- TOOL_RECHTEN (geldige toolrechten, resource:actie)
- RequirePermission decorator (metadata storage)

De beslissing welke rol welk toolrecht heeft staat in de database; die wordt gemeten in
tests/integration/test_tools_lezen_hun_rechten_uit_de_database.py en in
tests/architecture/test_role_permissions_cover_every_seeded_role.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# ==================== PERMISSION ENUM TESTS ====================


class TestPermissionEnum:
    """Test Permission enum definition and values"""

    def test_permission_enum_exists(self):
        """Permission enum should be defined"""
        from src.core.auth.rbac import Permission

        assert Permission is not None

    def test_permission_read_value(self):
        """Permission.READ should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.READ.value == "read"

    def test_permission_write_value(self):
        """Permission.WRITE should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.WRITE.value == "write"

    def test_permission_admin_value(self):
        """Permission.ADMIN should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.ADMIN.value == "admin"

    def test_permission_system_monitor_value(self):
        """Permission.SYSTEM_MONITOR should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.SYSTEM_MONITOR.value == "system_monitor"

    def test_permission_system_admin_value(self):
        """Permission.SYSTEM_ADMIN should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.SYSTEM_ADMIN.value == "system_admin"

    def test_permission_log_analyzer_value(self):
        """Permission.LOG_ANALYZER should have correct value"""
        from src.core.auth.rbac import Permission

        assert Permission.LOG_ANALYZER.value == "log_analyzer"

    def test_permission_enum_count(self):
        """Permission enum should have exactly 6 members"""
        from src.core.auth.rbac import Permission

        assert len(Permission) == 7  # + RECEIVABLES_PROPOSE (acceptant ronde 3, N1)

    def test_permission_serialization(self):
        """Permission enum should serialize to string value"""
        from src.core.auth.rbac import Permission

        assert Permission.READ.value == "read"
        assert str(Permission.READ.value) == "read"

    def test_permission_comparison(self):
        """Permission enum members should be comparable"""
        from src.core.auth.rbac import Permission

        assert Permission.READ == Permission.READ
        assert Permission.READ != Permission.WRITE

    def test_permission_membership(self):
        """Permission enum members should support 'in' checks"""
        from src.core.auth.rbac import Permission

        permissions = {Permission.READ, Permission.WRITE}
        assert Permission.READ in permissions
        assert Permission.ADMIN not in permissions


# ==================== RBACSERVICE CLASS TESTS ====================


class TestRBACServiceClass:
    """Test RBACService class instantiation and structure"""

    def test_rbac_service_class_exists(self):
        """RBACService class should be defined"""
        from src.core.auth.rbac import RBACService

        assert RBACService is not None

    def test_rbac_service_has_user_has_scope_for_method(self):
        """RBACService is nog maar een ding: de tool-gatekeeper van de SecurityOfficer"""
        from src.core.auth.rbac import RBACService

        assert callable(getattr(RBACService, "user_has_scope_for"))

    @pytest.mark.parametrize("naam", ["get_user_permissions", "user_has_permission"])
    def test_the_dead_role_matrix_methods_are_gone(self, naam):
        """OP-143: de methodes die `ROLE_PERMISSIONS` lazen hadden nul aanroepers en zijn weg"""
        from src.core.auth.rbac import RBACService

        assert not hasattr(RBACService, naam)

    def test_the_role_matrix_is_gone(self):
        """OP-143: rechten komen uit `role_permissions`, niet uit een woordenboek in de code"""
        from src.core.auth import rbac

        assert not hasattr(rbac, "ROLE_PERMISSIONS")


# ==================== REQUIRE_PERMISSION DECORATOR TESTS ====================


class TestRequirePermissionDecorator:
    """Test RequirePermission decorator function"""

    def test_require_permission_exists(self):
        """RequirePermission function should be defined"""
        from src.core.auth.rbac import RequirePermission

        assert RequirePermission is not None
        assert callable(RequirePermission)

    def test_require_permission_returns_decorator(self):
        """RequirePermission should return a decorator function"""
        from src.core.auth.rbac import Permission, RequirePermission

        decorator = RequirePermission(Permission.ADMIN)

        assert callable(decorator)

    def test_require_permission_stores_metadata(self):
        """RequirePermission should store permission metadata on function"""
        from src.core.auth.rbac import Permission, RequirePermission

        @RequirePermission(Permission.ADMIN)
        def test_endpoint():
            pass

        assert hasattr(test_endpoint, "__required_permission__")
        assert test_endpoint.__required_permission__ == Permission.ADMIN

    def test_require_permission_preserves_function(self):
        """RequirePermission should preserve the original function"""
        from src.core.auth.rbac import Permission, RequirePermission

        def test_endpoint():
            return "success"

        decorated = RequirePermission(Permission.READ)(test_endpoint)

        assert decorated() == "success"

    def test_require_permission_with_different_permissions(self):
        """RequirePermission should work with all permission types"""
        from src.core.auth.rbac import Permission, RequirePermission

        @RequirePermission(Permission.WRITE)
        def write_endpoint():
            pass

        @RequirePermission(Permission.SYSTEM_ADMIN)
        def admin_endpoint():
            pass

        assert write_endpoint.__required_permission__ == Permission.WRITE
        assert admin_endpoint.__required_permission__ == Permission.SYSTEM_ADMIN


# ==================== GLOBAL INSTANCE TESTS ====================


class TestGlobalRBACServiceInstance:
    """Test global rbac_service instance"""

    def test_rbac_service_global_instance_exists(self):
        """Global rbac_service instance should be defined"""
        from src.core.auth.rbac import rbac_service

        assert rbac_service is not None

    def test_rbac_service_global_instance_type(self):
        """Global rbac_service should be RBACService instance"""
        from src.core.auth.rbac import RBACService, rbac_service

        assert isinstance(rbac_service, RBACService)


# ==================== MODULE EXPORTS TESTS ====================


class TestModuleExports:
    """Test __all__ exports"""

    def test_all_exports_defined(self):
        """__all__ should be defined with expected exports"""
        from src.core.auth import rbac

        assert hasattr(rbac, "__all__")
        assert isinstance(rbac.__all__, list)

    def test_permission_exported(self):
        """Permission should be in __all__"""
        from src.core.auth import rbac

        assert "Permission" in rbac.__all__

    def test_tool_rechten_exported_and_role_permissions_not(self):
        """TOOL_RECHTEN staat in __all__; ROLE_PERMISSIONS (OP-143) niet meer"""
        from src.core.auth import rbac

        assert ("TOOL_RECHTEN" in rbac.__all__, "ROLE_PERMISSIONS" in rbac.__all__) == (True, False)

    def test_rbac_service_class_exported(self):
        """RBACService should be in __all__"""
        from src.core.auth import rbac

        assert "RBACService" in rbac.__all__

    def test_rbac_service_instance_exported(self):
        """rbac_service should be in __all__"""
        from src.core.auth import rbac

        assert "rbac_service" in rbac.__all__

    def test_require_permission_exported(self):
        """RequirePermission should be in __all__"""
        from src.core.auth import rbac

        assert "RequirePermission" in rbac.__all__


# ==================== INTEGRATION TESTS ====================


class TestRBACIntegration:
    """Integration tests for complete RBAC workflows"""

    def test_permission_enum_in_set_operations(self):
        """Test Permission enum works correctly in set operations"""
        from src.core.auth.rbac import Permission

        user_perms = {Permission.READ}
        admin_perms = {Permission.READ, Permission.WRITE, Permission.ADMIN}

        # Set difference
        admin_only = admin_perms - user_perms
        assert Permission.WRITE in admin_only
        assert Permission.ADMIN in admin_only
        assert Permission.READ not in admin_only

        # Set union
        combined = user_perms | {Permission.WRITE}
        assert Permission.READ in combined
        assert Permission.WRITE in combined
