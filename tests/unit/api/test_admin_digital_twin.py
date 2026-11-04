"""Unit tests for admin_digital_twin.py (B-1 JWT tenant isolation fix).

Covers:
  - Happy: regular admin reads own JWT tenant (override_tenant_id ignored)
  - Happy: system_admin with override_tenant_id queries that tenant
  - Happy: system_admin without override uses own JWT tenant
  - Unhappy: user with tenant_id=None raises ValueError
  - Behavioral: RLS SET LOCAL called before get_twin_stats
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers.limiet_request import echte_request


def _make_user(tenant_id: int, roles: list[str] | None = None) -> MagicMock:
    user = MagicMock()
    user.tenant_id = tenant_id
    user.roles = roles or ["admin"]
    return user


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


# ─── Happy path ───────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestAdminDigitalTwinHappy:
    @patch("src.core.api.admin_digital_twin.get_twin_stats")
    async def test_regular_admin_reads_own_tenant(self, mock_stats: MagicMock) -> None:
        """Regular admin always sees their own JWT tenant regardless of override param."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        mock_stats.return_value = {"observation_total": 5}
        db = _make_db()
        user = _make_user(tenant_id=42, roles=["admin"])

        result = await get_digital_twin_stats(request=echte_request(), 
            override_tenant_id=99,  # should be ignored for non-system_admin
            db=db,
            current_user=user,
        )

        mock_stats.assert_called_once_with(db=db, tenant_id=42)
        assert result["success"] is True

    @patch("src.core.api.admin_digital_twin.get_twin_stats")
    async def test_system_admin_can_use_override(self, mock_stats: MagicMock) -> None:
        """system_admin with override_tenant_id queries the override tenant."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        mock_stats.return_value = {"observation_total": 0}
        db = _make_db()
        user = _make_user(tenant_id=1, roles=["system_admin"])

        result = await get_digital_twin_stats(request=echte_request(), 
            override_tenant_id=7,
            db=db,
            current_user=user,
        )

        mock_stats.assert_called_once_with(db=db, tenant_id=7)
        assert result["success"] is True

    @patch("src.core.api.admin_digital_twin.get_twin_stats")
    async def test_system_admin_without_override_uses_own_tenant(
        self, mock_stats: MagicMock
    ) -> None:
        """system_admin without override uses their own JWT tenant."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        mock_stats.return_value = {}
        db = _make_db()
        user = _make_user(tenant_id=3, roles=["system_admin"])

        await get_digital_twin_stats(request=echte_request(), override_tenant_id=None, db=db, current_user=user)

        mock_stats.assert_called_once_with(db=db, tenant_id=3)


# ─── Unhappy path ────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestAdminDigitalTwinUnhappy:
    async def test_user_without_tenant_id_raises(self) -> None:
        """User with tenant_id=None must raise ValueError before any DB access."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        db = _make_db()
        user = MagicMock()
        user.tenant_id = None
        user.roles = ["admin"]

        with pytest.raises(ValueError, match="no tenant_id"):
            await get_digital_twin_stats(request=echte_request(), override_tenant_id=None, db=db, current_user=user)

        db.execute.assert_not_called()


# ─── Behavioral: RLS ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestAdminDigitalTwinRLS:
    @patch("src.core.api.admin_digital_twin.get_twin_stats")
    async def test_rls_set_local_called_before_stats(self, mock_stats: MagicMock) -> None:
        """db.execute(SET LOCAL app.current_tenant) must precede get_twin_stats."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        call_order: list[str] = []

        async def _track_execute(*args: object) -> None:
            call_order.append("rls")

        async def _track_stats(**kwargs: object) -> dict:
            call_order.append("stats")
            return {}

        db = _make_db()
        db.execute.side_effect = _track_execute
        mock_stats.side_effect = _track_stats

        user = _make_user(tenant_id=5, roles=["admin"])
        await get_digital_twin_stats(request=echte_request(), override_tenant_id=None, db=db, current_user=user)

        assert call_order == ["rls", "stats"], "SET LOCAL must be called before get_twin_stats"

    @patch("src.core.api.admin_digital_twin.get_twin_stats")
    async def test_rls_uses_bind_param(self, mock_stats: MagicMock) -> None:
        """SET LOCAL statement must use bind-param :tid, not f-string interpolation."""
        from src.core.api.admin_digital_twin import get_digital_twin_stats

        mock_stats.return_value = {}
        db = _make_db()
        user = _make_user(tenant_id=12, roles=["admin"])

        await get_digital_twin_stats(request=echte_request(), override_tenant_id=None, db=db, current_user=user)

        rls_call = db.execute.call_args_list[0]
        stmt_str = str(rls_call.args[0])
        assert "app.current_tenant" in stmt_str
        assert ":tid" in stmt_str, "Bind-param :tid verwacht, geen f-string interpolatie"
        params = rls_call.args[1] if len(rls_call.args) > 1 else {}
        assert params.get("tid") == "12", "tenant_id moet als bind-param worden doorgegeven"
