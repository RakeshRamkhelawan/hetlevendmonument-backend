"""Unit tests for TenantService (AUDIT-DB-01)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.tenants.schemas import TenantCreate, TenantUpdate
from src.core.container import TenantContext
from src.core.services.tenant_service import TenantService


def _make_mock_tenant(tenant_id: int = 1, name: str = "Tenant") -> MagicMock:
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.name = name
    tenant.slug = "slug"
    tenant.domain = None
    tenant.settings = {}
    tenant.is_active = True
    tenant.max_users = 10
    tenant.max_agents = 50
    tenant.max_storage_gb = 5
    tenant.subscription_tier = "free"
    tenant.subscription_status = "active"
    tenant.data_residency = "global"
    tenant.twin_hard_delete_max_hours = None
    tenant.created_at = datetime.now(timezone.utc)
    tenant.updated_at = None
    return tenant


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def superuser_context() -> TenantContext:
    return TenantContext(tenant_id=1, bypass_filter=True)


@pytest.fixture
def regular_user_context() -> TenantContext:
    return TenantContext(tenant_id=2, bypass_filter=False)


@pytest.fixture
def tenant_service(mock_db: AsyncMock, regular_user_context: TenantContext) -> TenantService:
    return TenantService(db=mock_db, tenant_context=regular_user_context)


def _make_scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    return result


def _make_scalars_result(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.unit
class TestTenantServiceCreate:
    async def test_create_tenant_success(
        self, tenant_service: TenantService, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
        mock_tenant = _make_mock_tenant(tenant_id=42, name="Acme")

        def _refresh_side_effect(obj: object) -> None:
            obj.id = 42
            obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh = AsyncMock(side_effect=_refresh_side_effect)

        # ADR-021: create_tenant() ook echt PranaService.provision_tenant() aanroept (best_effort).
        # Dat heeft zijn eigen, echte dekking in tests/integration/governance/
        # test_prana_service_integration.py -- hier alleen uitschakelen zodat deze test op
        # tenant-aanmaak-semantiek blijft toetsen, niet op een mock-db die geen echte
        # SQLAlchemy-sessie is.
        mock_provision = AsyncMock()
        monkeypatch.setattr(
            "src.core.governance.prana_service.PranaService.provision_tenant", mock_provision
        )

        data = TenantCreate(name="Acme", slug="acme")
        result = await tenant_service.create_tenant(data)

        assert result.id == 42
        # Was `mock_db.add.assert_called_once()` tot 2026-09-11. Sinds ADR-036 OP-185 maakt
        # create_user geen rollen meer aan, dus zaait create_tenant de standaardrollen voor
        # de nieuwe tenant -- anders kan die tenant niemand meer aanmaken. Dat zijn extra
        # `add`-aanroepen (3 rollen plus hun permissierijen), en dat HOORT zo. De toets
        # controleert nu wat hij bedoelde: de tenant zelf wordt precies een keer toegevoegd,
        # en alles wat er verder bij komt is rolbeheer en niets anders.
        toegevoegd = [c.args[0] for c in mock_db.add.call_args_list]
        tenants = [o for o in toegevoegd if type(o).__name__ == "Tenant"]
        assert len(tenants) == 1, toegevoegd
        overig = {type(o).__name__ for o in toegevoegd} - {"Tenant"}
        assert overig <= {"Role", "RolePermission"}, overig
        # Commits: de tenant zelf, het zaaien van de rollen, en de aparte transactie van de
        # prana-provisioning (best_effort) -- alle drie echt, geen dubbele call op dezelfde
        # handeling.
        assert mock_db.commit.await_count == 3, mock_db.commit.await_count
        mock_db.refresh.assert_awaited_once()
        mock_provision.assert_awaited_once_with(42)

    async def test_create_tenant_duplicate_slug(self, tenant_service: TenantService) -> None:
        duplicate_result = _make_scalar_result(MagicMock())
        tenant_service.db.execute = AsyncMock(return_value=duplicate_result)

        data = TenantCreate(name="Acme", slug="acme")
        with pytest.raises(Exception) as exc_info:
            await tenant_service.create_tenant(data)

        assert "already exists" in str(exc_info.value)

    async def test_create_tenant_duplicate_name(self, tenant_service: TenantService) -> None:
        tenant_service.db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),  # slug check
                _make_scalar_result(MagicMock()),  # name duplicate
            ]
        )

        data = TenantCreate(name="Acme", slug="acme")
        with pytest.raises(Exception) as exc_info:
            await tenant_service.create_tenant(data)

        assert "already exists" in str(exc_info.value)


@pytest.mark.unit
class TestTenantServiceList:
    async def test_list_tenants_superuser_sees_all(
        self, mock_db: AsyncMock, superuser_context: TenantContext
    ) -> None:
        service = TenantService(db=mock_db, tenant_context=superuser_context)
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(5),
                _make_scalars_result([_make_mock_tenant(1), _make_mock_tenant(2)]),
            ]
        )

        result = await service.list_tenants(skip=0, limit=10, is_active=None)

        assert result.total == 5
        assert len(result.data) == 2

    async def test_list_tenants_regular_user_filter_own_tenant(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(1),
                _make_scalars_result([_make_mock_tenant(2)]),
            ]
        )

        result = await tenant_service.list_tenants(skip=0, limit=10, is_active=None)

        assert result.total == 1
        assert len(result.data) == 1


@pytest.mark.unit
class TestTenantServiceGet:
    async def test_get_tenant_success(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_tenant = _make_mock_tenant(tenant_id=2)
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(mock_tenant))

        result = await tenant_service.get_tenant(2)

        assert result is not None

    async def test_get_tenant_not_found(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

        result = await tenant_service.get_tenant(2)

        assert result is None


@pytest.mark.unit
class TestTenantServiceUpdate:
    async def test_update_tenant_success(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_tenant = _make_mock_tenant(tenant_id=2)
        mock_tenant.domain = "old.example.com"
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(mock_tenant),
                _make_scalar_result(None),  # duplicate domain check
            ]
        )

        result = await tenant_service.update_tenant(2, TenantUpdate(name="New Name"))

        assert result is not None
        mock_db.commit.assert_awaited_once()

    async def test_update_tenant_duplicate_domain(self, tenant_service: TenantService) -> None:
        mock_tenant = _make_mock_tenant(tenant_id=2)
        mock_tenant.domain = "old.example.com"
        tenant_service.db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(mock_tenant),
                _make_scalar_result(MagicMock()),  # duplicate domain
            ]
        )

        with pytest.raises(Exception) as exc_info:
            await tenant_service.update_tenant(2, TenantUpdate(domain="taken.example.com"))

        assert "already in use" in str(exc_info.value)

    async def test_update_tenant_settings_none_coerced_to_empty_dict(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_tenant = _make_mock_tenant(tenant_id=2)
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(mock_tenant),
                _make_scalar_result(None),  # duplicate domain check
            ]
        )

        result = await tenant_service.update_tenant(2, TenantUpdate(settings=None))

        assert result is not None
        assert mock_tenant.settings == {}


@pytest.mark.unit
class TestTenantServiceDelete:
    async def test_delete_tenant_success(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_tenant = _make_mock_tenant(tenant_id=2)
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(mock_tenant))

        result = await tenant_service.delete_tenant(2)

        assert result is True
        assert mock_tenant.is_active is False
        mock_db.commit.assert_awaited_once()


@pytest.mark.unit
class TestTenantServiceStats:
    async def test_get_tenant_stats_makes_multiple_db_queries(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(2),  # tenant exists
                _make_scalar_result(1),
                _make_scalar_result(2),
                _make_scalar_result(None),
                _make_scalar_result(0),
            ]
        )

        await tenant_service.get_tenant_stats(2)

        assert mock_db.execute.await_count >= 3

    async def test_get_tenant_stats_returns_db_values(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(2),  # tenant exists
                _make_scalar_result(5),  # users
                _make_scalar_result(3),  # agents
                _make_scalar_result(None),  # last activity
                _make_scalar_result(1073741824),  # bytes -> 1 GB
            ]
        )

        stats = await tenant_service.get_tenant_stats(2)

        assert stats is not None
        assert stats.user_count == 5
        assert stats.agent_count == 3
        assert stats.storage_used_gb == 1.0

    async def test_get_tenant_stats_defense_in_depth_tenant_scope(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(0))

        with pytest.raises(Exception) as exc_info:
            await tenant_service.get_tenant_stats(999)

        assert "Cross-tenant" in str(exc_info.value)

    async def test_get_tenant_stats_returns_none_for_missing_tenant(
        self, tenant_service: TenantService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

        result = await tenant_service.get_tenant_stats(2)

        assert result is None


@pytest.mark.unit
class TestTenantServiceSchemaDefense:
    def test_tenant_response_tolerates_settings_none(self) -> None:
        """coerce_null_settings validator converts NULL DB value to empty dict."""
        from datetime import datetime, timezone

        from src.core.schemas.tenant_schemas import TenantResponse

        raw = {
            "id": 1,
            "name": "Test",
            "slug": "test",
            "domain": None,
            "settings": None,
            "is_active": True,
            "max_users": 10,
            "max_agents": 50,
            "max_storage_gb": 5,
            "subscription_tier": "free",
            "subscription_status": "active",
            "data_residency": "global",
            "twin_hard_delete_max_hours": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        }
        response = TenantResponse.model_validate(raw)
        assert response.settings == {}
