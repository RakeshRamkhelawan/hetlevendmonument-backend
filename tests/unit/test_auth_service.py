"""Tests for authentication service."""

import pytest
from unittest.mock import MagicMock

from src.core.auth.auth_service import get_primary_role_id
from src.core.models.rbac_models import User, Role


class TestGetPrimaryRoleId:
    """Test get_primary_role_id function with ORM attribute typing."""

    @pytest.mark.unit
    def test_get_primary_role_id_from_direct_role_id(self):
        """get_primary_role_id must return user.role_id when present."""
        user = MagicMock(spec=User)
        user.role_id = 42
        user.roles = None
        user.role = None

        result = get_primary_role_id(user)

        assert result == 42
        assert isinstance(result, int)

    @pytest.mark.unit
    def test_get_primary_role_id_from_roles_relationship(self):
        """get_primary_role_id must return first role.id from modern many-to-many."""
        role = MagicMock(spec=Role)
        role.id = 99

        user = MagicMock(spec=User)
        user.role_id = None
        user.roles = [role]
        user.role = None

        result = get_primary_role_id(user)

        assert result == 99
        assert isinstance(result, int)

    @pytest.mark.unit
    def test_get_primary_role_id_from_legacy_role_relationship(self):
        """get_primary_role_id must fallback to user.role for legacy compatibility."""
        role = MagicMock(spec=Role)
        role.id = 7

        user = MagicMock(spec=User)
        user.role_id = None
        user.roles = None
        user.role = role

        result = get_primary_role_id(user)

        assert result == 7
        assert isinstance(result, int)

    @pytest.mark.unit
    def test_get_primary_role_id_returns_none_when_no_role(self):
        """get_primary_role_id must return None when no role found."""
        user = MagicMock(spec=User)
        user.role_id = None
        user.roles = None
        user.role = None

        result = get_primary_role_id(user)

        assert result is None

    @pytest.mark.unit
    def test_get_primary_role_id_priority_order(self):
        """get_primary_role_id must follow priority: role_id > roles > role."""
        role1 = MagicMock(spec=Role)
        role1.id = 1

        role2 = MagicMock(spec=Role)
        role2.id = 2

        role3 = MagicMock(spec=Role)
        role3.id = 3

        user = MagicMock(spec=User)
        user.role_id = 1  # Highest priority
        user.roles = [role2]  # Medium priority
        user.role = role3  # Lowest priority

        result = get_primary_role_id(user)

        # Should return from role_id (priority 1), not from roles or role
        assert result == 1
