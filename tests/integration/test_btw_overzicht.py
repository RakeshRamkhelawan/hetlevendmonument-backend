"""Btw-overzicht per kwartaal uit bevestigde bonnen, met echte rechten en de echte catalogus (2026-10-19).

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole; vervangen zijn
alleen `get_current_user`, de databasesessie, de uploadmap (een tijdelijke map met bevestigde bonnen) en de klok. De
pakketstap loopt door de ECHTE agentcatalogus en de echte `vatcompliance`-skill.

Wat dit vaststelt:

1. Drie bevestigde bonnen in Q3 en een in Q4: het Q3-overzicht telt precies die drie, per tarief, op de cent.
2. Een niet-bevestigde bon telt niet mee.
3. Tenant B ziet het overzicht van tenant A niet.
4. Wie `receipts:read` heeft mag het overzicht en de CSV zien (rol `user`, jokerleesrecht); wie dat recht niet heeft
   krijgt 403.
5. Pakket mkb.zero_admin: stap 1 (receiptscanner) en stap 2 (vatcompliance) slagen, stap 2 toont het kwartaal en de
   bedragen; een kwartaal zonder bonnen geeft 0 en geen fout.

Wat NIET gemeten is: een draaiende worker, Redis, de echte JWT-controle en de pakketroute zelf (die staat in
`test_packs_execute_route.py`; hier loopt de stap door de echte catalogus).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.btw_overzicht import BtwOverzicht
from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator, WorkflowStep
from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
ANDERE_TENANT = 2
URL = "/api/v1/bonnen/btw-overzicht"
NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _bevestig(root: Path, tenant: int, teken: str, datum: str, btw: dict[str, str]) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden = {
        "leverancier": "Bakkerij De Korenaar B.V.",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw,
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    (map_ / f"{teken * 32}.pdf.bevestigd.json").write_text(
        json.dumps({"velden": velden, "door": 1, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )


async def _gebruiker(session: AsyncSession, email: str, tenant_id: int, rollen: list[str]) -> int:
    gebruiker = User(
        email=email, hashed_password="x", tenant_id=tenant_id, is_active=True, is_superuser=False
    )
    session.add(gebruiker)
    await session.flush()
    for naam in rollen:
        rol = (
            await session.execute(
                select(Role).where(Role.name == naam, Role.tenant_id == tenant_id)
            )
        ).scalar_one()
        await session.execute(
            user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id, tenant_id=tenant_id)
        )
    await session.commit()
    return int(gebruiker.id)


async def _client(
    app: Any, session: AsyncSession, root: Path, *, user_id: int, email: str, tenant_id: int
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.dependencies import get_db as api_get_db
    from src.core.api.v1.bonnen.dependencies import get_btw_overzicht, get_nu
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=tenant_id, roles=["user"])
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        get_btw_overzicht: lambda: BtwOverzicht(root),
        get_nu: lambda: NU,
    }
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=tenant_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


@pytest_asyncio.fixture
async def sessie(postgres_session: AsyncSession) -> AsyncSession:
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    await RBACService(postgres_session).ensure_default_roles(ANDERE_TENANT)
    return postgres_session


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # De pakketstap leest dezelfde map als de routes.
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    return tmp_path


@pytest_asyncio.fixture
async def medewerker(
    integration_app: Any, sessie: AsyncSession, root: Path
) -> AsyncGenerator[AsyncClient, None]:
    email = "usr-btw@integration.test"
    user_id = await _gebruiker(sessie, email, TENANT, ["user"])
    async for client in _client(
        integration_app, sessie, root, user_id=user_id, email=email, tenant_id=TENANT
    ):
        yield client


async def _met_recht(
    app: Any, sessie: AsyncSession, root: Path, rolnaam: str, resource: str, actie: str
) -> AsyncGenerator[AsyncClient, None]:
    rol = Role(tenant_id=TENANT, name=rolnaam, description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource=resource, action=actie))
    await sessie.commit()
    email = f"{rolnaam}@integration.test"
    user_id = await _gebruiker(sessie, email, TENANT, [rolnaam])
    async for client in _client(app, sessie, root, user_id=user_id, email=email, tenant_id=TENANT):
        yield client


@pytest_asyncio.fixture
async def alles_lezen(
    integration_app: Any, sessie: AsyncSession, root: Path
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _met_recht(integration_app, sessie, root, "alles-lezen-btw", "*", "read"):
        yield client


@pytest_asyncio.fixture
async def zonder_recht(
    integration_app: Any, sessie: AsyncSession, root: Path
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _met_recht(integration_app, sessie, root, "zonder-btw", "agents", "read"):
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetOverzichtMetEchteRechten:
    async def test_three_bonnen_in_q3_and_one_in_q4_give_the_q3_overview(
        self, medewerker: AsyncClient, root: Path
    ) -> None:
        _bevestig(root, TENANT, "a", "2026-07-15", {"9": "0.50", "21": "1.60"})
        _bevestig(root, TENANT, "b", "2026-08-20", {"21": "2.10"})
        _bevestig(root, TENANT, "c", "2026-09-30", {"9": "1.25"})
        _bevestig(root, TENANT, "d", "2026-10-01", {"9": "99.00", "21": "99.00"})

        antwoord = await medewerker.get(URL, params={"kwartaal": "2026-Q3"})

        data = antwoord.json()["data"]
        assert (antwoord.status_code, data["aantal"], data["voorbelasting"], data["totaal"]) == (
            200,
            3,
            {"9": "1.75", "21": "3.70", "overig": "0.00"},
            "5.45",
        )

    async def test_a_bon_that_is_not_confirmed_does_not_count(
        self, medewerker: AsyncClient, root: Path
    ) -> None:
        map_ = root / str(TENANT)
        map_.mkdir(parents=True)
        (map_ / f"{'a' * 32}.pdf.resultaat.json").write_text(
            json.dumps(
                {"status": "gelezen", "velden": {"datum": "2026-08-15", "btw": {"21": "5.00"}}}
            ),
            encoding="utf-8",
        )

        antwoord = await medewerker.get(URL, params={"kwartaal": "2026-Q3"})

        assert antwoord.json()["data"]["aantal"] == 0

    async def test_tenant_b_does_not_see_the_overview_of_tenant_a(
        self,
        integration_app: Any,
        sessie: AsyncSession,
        root: Path,
        medewerker: AsyncClient,
    ) -> None:
        _bevestig(root, TENANT, "a", "2026-08-15", {"21": "5.00"})
        email = "andere-tenant-btw@integration.test"
        user_id = await _gebruiker(sessie, email, ANDERE_TENANT, ["user"])

        aantallen: list[int] = []
        async for client in _client(
            integration_app, sessie, root, user_id=user_id, email=email, tenant_id=ANDERE_TENANT
        ):
            antwoord = await client.get(URL, params={"kwartaal": "2026-Q3"})
            aantallen.append(antwoord.json()["data"]["aantal"])

        assert aantallen == [0]

    async def test_a_quarter_without_bonnen_gives_zero_and_no_error(
        self, medewerker: AsyncClient
    ) -> None:
        antwoord = await medewerker.get(URL, params={"kwartaal": "2026-Q1"})

        assert (antwoord.status_code, antwoord.json()["data"]["totaal"]) == (200, "0.00")

    async def test_the_csv_is_available_for_the_same_user(
        self, medewerker: AsyncClient, root: Path
    ) -> None:
        _bevestig(root, TENANT, "a", "2026-07-15", {"9": "0.50"})

        antwoord = await medewerker.get(f"{URL}.csv", params={"kwartaal": "2026-Q3"})

        assert antwoord.status_code == 200 and "2026-07-15" in antwoord.text

    async def test_a_user_without_the_right_gets_403(self, zonder_recht: AsyncClient) -> None:
        antwoord = await zonder_recht.get(URL, params={"kwartaal": "2026-Q3"})

        assert antwoord.status_code == 403, antwoord.text

    async def test_a_user_without_the_right_gets_403_for_the_csv(
        self, zonder_recht: AsyncClient
    ) -> None:
        antwoord = await zonder_recht.get(f"{URL}.csv", params={"kwartaal": "2026-Q3"})

        assert antwoord.status_code == 403, antwoord.text

    async def test_a_wildcard_read_right_may_see_the_overview(
        self, alles_lezen: AsyncClient
    ) -> None:
        antwoord = await alles_lezen.get(URL, params={"kwartaal": "2026-Q3"})

        assert antwoord.status_code == 200, antwoord.text


def _pakket() -> DomainPack:
    """De stappen van mkb.zero_admin (config/domain_packs.yaml): bonnen lezen, dan de btw voorbereiden."""
    return DomainPack(
        pack_id="mkb.zero_admin",
        name="Zero-Admin Bookkeeping",
        steps=[
            WorkflowStep(agent_id="receiptscanner", mode="sequential", sla_seconds=30),
            WorkflowStep(agent_id="vatcompliance", mode="sequential", sla_seconds=30),
        ],
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestStapTweeVanHetPakket:
    async def _draai(self, tenant: int = TENANT) -> list[Any]:
        with (
            patch("src.core.database.database.db_manager"),
            patch("src.core.als.agents.skills.vatcompliance._nu", lambda: NU),
            patch("src.core.als.agents.skills.receiptscanner._nu", lambda: NU),
        ):
            return await DomainPackOrchestrator().run_pack(
                _pakket(), tenant_id=tenant, initiated_by_user_id=42
            )

    async def test_step_two_succeeds_and_shows_the_quarter_and_the_amounts(
        self, root: Path
    ) -> None:
        # Zonder gekozen kwartaal is het het VORIGE afgesloten kwartaal (zero-admin afwerken, 2026-10-19): Q3.
        _bevestig(root, TENANT, "a", "2026-08-05", {"9": "0.50", "21": "1.60"})
        _bevestig(root, TENANT, "b", "2026-09-09", {"21": "2.10"})
        _bevestig(root, TENANT, "c", "2026-10-09", {"21": "9.99"})

        resultaten = await self._draai()

        data = resultaten[1].result_data or {}
        assert (resultaten[1].success, data["kwartaal"], data["aantal"], data["voorbelasting"]) == (
            True,
            "2026-Q3",
            2,
            {"9": "0.50", "21": "3.70", "overig": "0.00"},
        )

    async def test_step_one_and_step_two_both_succeed(self, root: Path) -> None:
        _bevestig(root, TENANT, "a", "2026-10-05", {"21": "1.60"})

        resultaten = await self._draai()

        assert [r.success for r in resultaten] == [True, True]

    async def test_the_steps_keep_their_agent_ids_for_the_screen(self, root: Path) -> None:
        resultaten = await self._draai()

        assert [r.agent_id for r in resultaten] == ["receiptscanner", "vatcompliance"]

    async def test_a_quarter_without_bonnen_gives_zero_and_no_error(self, root: Path) -> None:
        resultaten = await self._draai()

        data = resultaten[1].result_data or {}
        assert (resultaten[1].success, data["aantal"], data["totaal"]) == (True, 0, "0.00")

    async def test_the_overview_of_another_tenant_is_not_used(self, root: Path) -> None:
        _bevestig(root, ANDERE_TENANT, "a", "2026-10-05", {"21": "50.00"})

        resultaten = await self._draai()

        assert (resultaten[1].result_data or {})["aantal"] == 0

    async def test_the_answer_for_the_screen_carries_the_overview(self, root: Path) -> None:
        from src.core.api.v1.agentic.agentic_domain_router import _naar_antwoord

        _bevestig(root, TENANT, "a", "2026-08-05", {"21": "1.60"})

        antwoord = _naar_antwoord("mkb.zero_admin", await self._draai(), sla_breached=False)

        samenvatting = antwoord.steps[1].samenvatting
        assert samenvatting is not None and samenvatting["kwartaal"] == "2026-Q3"
