"""De uitleg over vier ogen bij het inrichten (ADR-039, "Bestaande ondernemingen", Rakesh 2026-10-05).

Een onderneming met de markering `four_eyes_explanation_pending` (gezet door de migratie
`20261007_vier_ogen_bestaande_tenants`, of bij het aanmaken van een nieuwe) laat een beheerder
eerst de uitleg zien. `GET /four-eyes` meldt de markering; `POST /four-eyes/explanation-confirmed`
haalt hem weg: alleen een beheerder, met CSRF, met een auditregel, alleen in de EIGEN tenant.

Echte SQLite-sessie: de markering wordt echt in `tenants.settings` gelezen en geschreven.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.auth.auth_service import UserResponse

PAD = "/api/v1/tools/hitl/four-eyes"
BEVESTIG = "/api/v1/tools/hitl/four-eyes/explanation-confirmed"
MERK = {"revision": "20261007_vier_ogen_bestaande_tenants", "settings_was_null": False}


def _gebruiker(tenant_id: int, roles: list[str]) -> UserResponse:
    return UserResponse(id=5, email="b@klant.nl", tenant_id=tenant_id, roles=roles)


async def _tenants(db: AsyncSession) -> None:
    from src.core.models.rbac_models import Tenant

    gemarkeerd = {
        "four_eyes_actions": ["make_payment"],
        "four_eyes_explanation_pending": True,
        "four_eyes_set_by_migration": MERK,
    }
    db.add(Tenant(id=1, name="Een", slug="een", settings=dict(gemarkeerd)))
    db.add(Tenant(id=2, name="Twee", slug="twee", settings=dict(gemarkeerd)))
    db.add(Tenant(id=3, name="Drie", slug="drie", settings={"four_eyes_actions": []}))
    await db.commit()


def _client(
    db: AsyncSession, gebruiker: UserResponse, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, AsyncMock]:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.admin.dependencies import get_current_user
    from src.core.api.v1.tool_broker import four_eyes_router as module
    from src.core.api.v1.tool_broker.dependencies import get_db

    audit = AsyncMock(return_value=None)
    monkeypatch.setattr(module.AuditService, "log_event", audit)
    app = FastAPI()
    app.include_router(module.router)

    async def _db() -> Any:
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app), audit


async def _settings(db: AsyncSession, tenant_id: int) -> dict[str, Any]:
    from src.core.models.rbac_models import Tenant

    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    await db.refresh(tenant)
    return dict(tenant.settings)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeMarkeringLezen:
    async def test_a_marked_tenant_reports_the_explanation_as_pending(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["user"]), monkeypatch)

        assert client.get(PAD).json()["data"]["explanation_pending"] is True

    async def test_an_unmarked_tenant_reports_nothing_pending(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(3, ["admin"]), monkeypatch)

        assert client.get(PAD).json()["data"]["explanation_pending"] is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestBevestigen:
    async def test_an_administrator_clears_the_marker(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.post(BEVESTIG)

        assert client.get(PAD).json()["data"]["explanation_pending"] is False

    async def test_confirming_keeps_the_four_eyes_setting(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.post(BEVESTIG)

        assert (await _settings(db_session, 1))["four_eyes_actions"] == ["make_payment"]

    async def test_a_user_without_the_right_gets_403(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["user"]), monkeypatch)

        assert client.post(BEVESTIG).status_code == 403

    async def test_a_refused_user_leaves_the_marker(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["user"]), monkeypatch)

        client.post(BEVESTIG)

        assert (await _settings(db_session, 1))["four_eyes_explanation_pending"] is True

    async def test_another_tenant_keeps_its_marker(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.post(BEVESTIG)

        assert (await _settings(db_session, 2))["four_eyes_explanation_pending"] is True

    async def test_confirming_is_written_to_the_audit_log(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, audit = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.post(BEVESTIG)

        assert audit.await_args is not None
        assert audit.await_args.kwargs["event_type"] == "four_eyes_explanation_confirmed"

    async def test_the_route_requires_a_csrf_token(self) -> None:
        from src.core.api.auth.dependencies import validate_csrf_token
        from src.core.api.v1.tool_broker import four_eyes_router as module

        route = next(r for r in module.router.routes if getattr(r, "path", "") == BEVESTIG)
        afhankelijk = [d.call for d in route.dependant.dependencies]  # type: ignore[attr-defined]

        assert validate_csrf_token in afhankelijk


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenEigenKeuze:
    async def test_changing_the_setting_drops_the_migration_mark(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wie zelf kiest, maakt het tot zijn keuze: een downgrade mag die niet terugdraaien."""
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.put(PAD, json={"actions": ["make_payment"]})

        assert "four_eyes_set_by_migration" not in await _settings(db_session, 1)


@pytest.mark.unit
class TestEenNieuweOnderneming:
    def test_a_new_tenant_is_marked_to_see_the_explanation(self) -> None:
        from src.core.models.rbac_models import with_four_eyes_defaults

        assert with_four_eyes_defaults(None)["four_eyes_explanation_pending"] is True
