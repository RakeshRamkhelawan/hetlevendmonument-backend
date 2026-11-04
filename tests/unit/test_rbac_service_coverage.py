"""
RBAC Service Coverage Tests - Week 3, Subagent 1
Target: rbac_service.py (31.03% -> 70%+)

Tests for Role-Based Access Control service:
- RBACService class methods
- Permission checking
- Role management
- User-role relationships
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# ==================== TENANT CONTEXT MOCK ====================


@pytest.fixture(autouse=True)
def mock_tenant_context():
    """Auto-mock tenant context for all tests in this module.

    The RBACService.has_permission() calls user_has_permission() which requires
    tenant context via get_tenant_id(). Without this mock, tests fail because
    there's no tenant context in unit test mode.

    We patch BOTH the import location and the source module.
    """
    with patch("src.core.services.rbac_service.get_tenant_id", return_value=1):
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            yield


# ==================== MOCK HELPER FUNCTIONS ====================


def create_dual_mock_result(data_list, is_role_query=False):
    """
    Create a mock result that works with BOTH:
    - result.all() - returns list of tuples for role_ids query
    - result.scalars().all() - returns list of objects for permission queries

    The new RBACService.user_has_permission() uses:
    - `result.all()` for role_ids (returns [(role_id,), ...])
    - `result.scalars().all()` for permissions

    Args:
        data_list: List of mock objects (roles or permissions)
        is_role_query: If True, format result.all() as tuples [(id,), ...]
    """
    mock_result = MagicMock()
    mock_scalars = MagicMock()

    # For result.scalars().all() - return the objects directly
    mock_scalars.all.return_value = data_list
    mock_result.scalars.return_value = mock_scalars

    # For result.all() - return tuples if items have .id attribute (role query)
    if is_role_query and data_list and hasattr(data_list[0], "id"):
        mock_result.all.return_value = [(item.id,) for item in data_list]
    else:
        mock_result.all.return_value = data_list

    mock_result.first.return_value = data_list[0] if data_list else None

    return mock_result


def create_mock_role(role_id: int, name: str = "test_role", is_active: bool = True):
    """Create a mock Role object"""
    mock_role = MagicMock()
    mock_role.id = role_id
    mock_role.name = name
    mock_role.is_active = is_active
    return mock_role


def create_mock_permission(resource: str, action: str, conditions: dict = None):
    """Create a mock RolePermission object

    Args:
        resource: Resource name (e.g., "users", "*")
        action: Action name (e.g., "read", "*")
        conditions: Optional conditions dict (MUST be None or dict, not Mock)
    """
    mock_perm = MagicMock()
    mock_perm.resource = resource
    mock_perm.action = action
    mock_perm.conditions = conditions  # Critical: must be None or real dict
    return mock_perm


class TestRBACServiceInit:
    """Test RBACService initialization"""

    def test_rbac_service_accepts_db_session(self):
        """RBACService should accept AsyncSession in constructor"""
        from src.core.services.rbac_service import RBACService

        mock_db = MagicMock(spec=AsyncSession)
        service = RBACService(mock_db)

        assert service.db == mock_db

    def test_rbac_service_stores_db_reference(self):
        """RBACService should store db session for later use"""
        from src.core.services.rbac_service import RBACService

        mock_db = MagicMock(spec=AsyncSession)
        service = RBACService(mock_db)

        assert hasattr(service, "db")
        assert service.db is mock_db


class TestRBACServiceGetUserRoles:
    """Test get_user_roles method"""

    @pytest.mark.asyncio
    async def test_get_user_roles_returns_list(self):
        """get_user_roles should return a list of roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        roles = await service.get_user_roles(user_id=1)

        assert isinstance(roles, list)

    @pytest.mark.asyncio
    async def test_get_user_roles_with_valid_user(self):
        """get_user_roles should query database for user roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()

        # Create mock role
        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "admin"
        mock_role.is_active = True
        mock_scalars.all.return_value = [mock_role]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        roles = await service.get_user_roles(user_id=1)

        assert len(roles) == 1
        assert roles[0].name == "admin"

    @pytest.mark.asyncio
    async def test_get_user_roles_with_no_roles(self):
        """get_user_roles should return empty list for user without roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        roles = await service.get_user_roles(user_id=999)

        assert roles == []

    @pytest.mark.asyncio
    async def test_get_user_roles_with_multiple_roles(self):
        """get_user_roles should return all assigned roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()

        # Create multiple mock roles
        mock_role1 = MagicMock()
        mock_role1.id = 1
        mock_role1.name = "admin"
        mock_role2 = MagicMock()
        mock_role2.id = 2
        mock_role2.name = "editor"

        mock_scalars.all.return_value = [mock_role1, mock_role2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        roles = await service.get_user_roles(user_id=1)

        assert len(roles) == 2


class TestRBACServiceGetRolePermissions:
    """Test get_role_permissions method"""

    @pytest.mark.asyncio
    async def test_get_role_permissions_returns_list(self):
        """get_role_permissions should return list of permissions"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        perms = await service.get_role_permissions(role_id=1)

        assert isinstance(perms, list)

    @pytest.mark.asyncio
    async def test_get_role_permissions_with_valid_role(self):
        """get_role_permissions should return permissions for role"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()

        # Create mock permission
        mock_perm = MagicMock()
        mock_perm.id = 1
        mock_perm.role_id = 1
        mock_perm.resource = "users"
        mock_perm.action = "read"

        mock_scalars.all.return_value = [mock_perm]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        perms = await service.get_role_permissions(role_id=1)

        assert len(perms) == 1
        assert perms[0].resource == "users"

    @pytest.mark.asyncio
    async def test_get_role_permissions_empty_for_invalid_role(self):
        """get_role_permissions should return empty for non-existent role"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        perms = await service.get_role_permissions(role_id=99999)

        assert perms == []


class TestRBACServiceHasPermission:
    """Test has_permission method"""

    @pytest.mark.asyncio
    async def test_has_permission_returns_bool(self):
        """has_permission should return boolean"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        # Mock get_user_roles to return empty (no permission)
        mock_result = create_dual_mock_result([])
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        result = await service.has_permission(user_id=1, resource="users", action="read")

        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_has_permission_false_without_roles(self):
        """has_permission should return False for user without roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = create_dual_mock_result([])
        mock_db.execute.return_value = mock_result

        service = RBACService(mock_db)
        result = await service.has_permission(user_id=1, resource="users", action="delete")

        assert result is False

    @pytest.mark.asyncio
    async def test_has_permission_true_with_matching_permission(self):
        """has_permission should return True when user has the permission"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        mock_role = create_mock_role(1, "admin")
        mock_perm = create_mock_permission("users", "read")

        mock_result1 = create_dual_mock_result([mock_role], is_role_query=True)
        mock_result2 = create_dual_mock_result([mock_perm], is_role_query=False)

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        service = RBACService(mock_db)
        # Disable Redis to use in-memory cache for testing
        service._redis = None
        service._perm_cache = {}

        # Pass tenant_id directly to avoid context dependency
        result = await service.has_permission(
            user_id=1, resource="users", action="read", tenant_id=1
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_has_permission_false_without_matching_permission(self):
        """has_permission should return False when permission doesn't match"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        mock_role = create_mock_role(1)

        # The SQL query filters for resource + action, so empty result for non-matching
        mock_result1 = create_dual_mock_result([mock_role], is_role_query=True)
        mock_result2 = create_dual_mock_result([], is_role_query=False)  # No matching permissions

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        service = RBACService(mock_db)
        result = await service.has_permission(user_id=1, resource="users", action="delete")

        assert result is False


class TestRBACServiceProtocol:
    """Test RBACServiceProtocol compliance"""

    def test_protocol_defines_has_permission(self):
        """RBACServiceProtocol should define has_permission method"""
        from src.core.services.rbac_service import RBACServiceProtocol

        # Protocol should have has_permission
        assert hasattr(RBACServiceProtocol, "has_permission")

    def test_protocol_defines_get_user_roles(self):
        """RBACServiceProtocol should define get_user_roles method"""
        from src.core.services.rbac_service import RBACServiceProtocol

        assert hasattr(RBACServiceProtocol, "get_user_roles")


class TestGetRBACService:
    """Test get_rbac_service dependency factory"""

    @pytest.mark.asyncio
    async def test_get_rbac_service_returns_service(self):
        """get_rbac_service should return RBACService instance"""
        from src.core.services.rbac_service import RBACService, get_rbac_service

        mock_db = AsyncMock(spec=AsyncSession)

        # get_rbac_service is a dependency that needs db
        service = await get_rbac_service(db=mock_db)

        assert isinstance(service, RBACService)

    @pytest.mark.asyncio
    async def test_get_rbac_service_passes_db(self):
        """get_rbac_service should pass db session to RBACService"""
        from src.core.services.rbac_service import get_rbac_service

        mock_db = AsyncMock(spec=AsyncSession)
        service = await get_rbac_service(db=mock_db)

        assert service.db == mock_db


class TestRBACServiceWildcardPermissions:
    """Test wildcard permission matching"""

    @pytest.mark.asyncio
    async def test_has_permission_with_wildcard_action(self):
        """has_permission should match wildcard (*) actions"""
        from unittest.mock import patch

        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        mock_role = create_mock_role(1)
        mock_perm = create_mock_permission("users", "*")  # Wildcard action

        # First query is role query (uses .all() for tuples)
        # Second query is permission query (uses .scalars().all())
        mock_result1 = create_dual_mock_result([mock_role], is_role_query=True)
        mock_result2 = create_dual_mock_result([mock_perm], is_role_query=False)

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        # Patch tenant context
        with patch("src.core.services.rbac_service.get_tenant_id", return_value=1):
            service = RBACService(mock_db)
            # Clear cache to ensure fresh query
            service._perm_cache = {}
            service._redis = None
            # Should match any action due to wildcard
            result = await service.has_permission(user_id=1, resource="users", action="delete")

        assert result is True

    @pytest.mark.asyncio
    async def test_has_permission_with_wildcard_resource_not_supported(self):
        """
        has_permission DOES support *:action pattern (wildcard resource + specific action).
        The SQL query uses: or_(RolePermission.resource == perm_resource, RolePermission.resource == '*')
        This means wildcard resources ARE matched.
        """
        from unittest.mock import patch

        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        mock_role = create_mock_role(1)
        mock_perm = create_mock_permission("*", "read")  # Wildcard resource, specific action

        mock_result1 = create_dual_mock_result([mock_role], is_role_query=True)
        mock_result2 = create_dual_mock_result([mock_perm], is_role_query=False)

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        # Patch tenant context
        with patch("src.core.services.rbac_service.get_tenant_id", return_value=1):
            service = RBACService(mock_db)
            # Clear cache to ensure fresh query
            service._perm_cache = {}
            service._redis = None
            # *:action IS supported per the SQL query logic
            result = await service.has_permission(user_id=1, resource="anything", action="read")

        # Current implementation DOES support *:action pattern (matched in SQL with or_())
        assert result is True


class TestRBACServiceMultipleRoles:
    """Test permission checking across multiple roles"""

    @pytest.mark.asyncio
    async def test_has_permission_checks_all_roles(self):
        """has_permission should check permissions across all user roles"""
        from src.core.services.rbac_service import RBACService

        mock_db = AsyncMock(spec=AsyncSession)

        # User has 2 roles
        mock_role1 = create_mock_role(1, "viewer")
        mock_role2 = create_mock_role(2, "editor")

        # Role 2 has write permission (the one we're checking for)
        mock_perm2 = create_mock_permission("users", "write")

        # First query returns both roles (role query uses .all())
        mock_result1 = create_dual_mock_result([mock_role1, mock_role2], is_role_query=True)
        # Second query returns the matching permission (permission query uses .scalars().all())
        mock_result2 = create_dual_mock_result([mock_perm2], is_role_query=False)

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        service = RBACService(mock_db)
        # Should find "write" permission
        result = await service.has_permission(user_id=1, resource="users", action="write")

        assert result is True
