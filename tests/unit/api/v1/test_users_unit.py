"""Unit tests for User CRUD endpoints (TC-008 reactivation).

Rewrites the quarantined test_users.py with mocked DB (no async_client / admin_token).
Tests verify create_user and list_users behavior in isolation.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.v1.users.schemas import UserCreate, UserResponse

_VALID_PWD = "Testpass1!"  # satisfies: upper + lower + digit + 8 chars


def _make_user(
    id: int = 1,
    email: str = "user@tenant1.com",
    tenant_id: int = 1,
    is_active: bool = True,
    is_superuser: bool = False,
) -> MagicMock:
    user = MagicMock()
    user.id = id
    user.email = email
    user.tenant_id = tenant_id
    user.is_active = is_active
    user.is_superuser = is_superuser
    user.roles = []
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = None
    user.last_login = None
    return user


def _make_user_response(
    id: int = 1,
    email: str = "user@tenant1.com",
    tenant_id: int = 1,
) -> UserResponse:
    return UserResponse(
        id=id,
        email=email,
        tenant_id=tenant_id,
        is_active=True,
        roles=[],
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        last_login=None,
    )


@pytest.fixture()
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture()
def admin_user() -> MagicMock:
    user = _make_user(id=10, email="admin@tenant1.com", tenant_id=1)
    role = MagicMock()
    role.name = "admin"
    user.roles = [role]
    return user


@pytest.fixture()
def regular_user() -> MagicMock:
    return _make_user(id=5, email="regular@tenant1.com", tenant_id=1)


class TestCreateUser:
    """Happy and unhappy path tests for POST /users/."""

    @pytest.mark.asyncio
    async def test_create_user_happy_path(self, mock_db: AsyncMock, admin_user: MagicMock) -> None:
        """Happy path: admin creates a new user; UserResponse is returned."""
        from src.core.api.v1.users.users_list_router import create_user

        new_user = _make_user(id=20, email="newuser@tenant1.com", tenant_id=1)
        expected_response = _make_user_response(id=20, email="newuser@tenant1.com", tenant_id=1)

        no_user_result = MagicMock()
        no_user_result.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = new_user
        mock_db.execute = AsyncMock(side_effect=[no_user_result, user_result])

        mock_auth_svc = AsyncMock()
        mock_auth_svc.create_user = AsyncMock(return_value=new_user)

        data = UserCreate(email="newuser@tenant1.com", password=_VALID_PWD, role_ids=[])

        with (
            patch("src.core.api.v1.users.users_list_router.can_manage_users", return_value=True),
            patch(
                "src.core.api.v1.users.users_list_router.AuthService",
                return_value=mock_auth_svc,
            ),
            patch(
                "src.core.api.v1.users.users_list_router.UserResponse.model_validate",
                return_value=expected_response,
            ),
        ):
            result = await create_user(
                data=data,
                target_tenant_id=1,
                db=mock_db,
                current_user=admin_user,
            )

        assert result.email == "newuser@tenant1.com"
        assert result.tenant_id == 1

    @pytest.mark.asyncio
    async def test_create_user_forbidden_without_permission(
        self, mock_db: AsyncMock, regular_user: MagicMock
    ) -> None:
        """Unhappy path: 403 when caller lacks manage-users permission."""
        from fastapi import HTTPException

        from src.core.api.v1.users.users_list_router import create_user

        data = UserCreate(email="victim@tenant1.com", password=_VALID_PWD, role_ids=[])

        with (
            patch("src.core.api.v1.users.users_list_router.can_manage_users", return_value=False),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_user(
                data=data,
                target_tenant_id=1,
                db=mock_db,
                current_user=regular_user,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_raises_400(
        self, mock_db: AsyncMock, admin_user: MagicMock
    ) -> None:
        """Unhappy path: 400 when email already exists in DB."""
        from fastapi import HTTPException

        from src.core.api.v1.users.users_list_router import create_user

        existing = _make_user(id=3, email="dup@tenant1.com", tenant_id=1)
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=dup_result)

        data = UserCreate(email="dup@tenant1.com", password=_VALID_PWD, role_ids=[])

        with (
            patch("src.core.api.v1.users.users_list_router.can_manage_users", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_user(
                data=data,
                target_tenant_id=1,
                db=mock_db,
                current_user=admin_user,
            )

        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail


class TestListUsers:
    """Happy path tests for GET /users/."""

    @pytest.mark.asyncio
    async def test_list_users_regular_user_sees_only_self(
        self, mock_db: AsyncMock, regular_user: MagicMock
    ) -> None:
        """Regular user (non-admin) receives list containing only themselves."""
        from src.core.api.v1.users.users_list_router import list_users

        self_response = _make_user_response(id=5, email="regular@tenant1.com", tenant_id=1)

        with patch(
            "src.core.api.v1.users.users_list_router.UserResponse.model_validate",
            return_value=self_response,
        ):
            result = await list_users(
                tenant_id=None,
                is_active=None,
                skip=0,
                limit=100,
                db=mock_db,
                current_user=regular_user,
            )

        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].email == "regular@tenant1.com"

    @pytest.mark.asyncio
    async def test_list_users_admin_queries_db_for_tenant(
        self, mock_db: AsyncMock, admin_user: MagicMock
    ) -> None:
        """Admin user triggers DB query (not the self-only shortcut)."""
        from src.core.api.v1.users.users_list_router import list_users

        u1 = _make_user(id=1, email="a@t.com", tenant_id=1)
        u2 = _make_user(id=2, email="b@t.com", tenant_id=1)

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [u1, u2]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        with patch(
            "src.core.api.v1.users.users_list_router.has_role",
            return_value=True,
        ):
            result = await list_users(
                tenant_id=None,
                is_active=None,
                skip=0,
                limit=100,
                db=mock_db,
                current_user=admin_user,
            )

        assert result.total == 2
