"""Een MEEGELEVERDE tool aan- of uitzetten mag alleen de platformrol; een klantbeheerder mag alleen zijn eigen tool.

Regie 2026-10-27. De meegeleverde tools (`serena`, `code_analyzer`, ...) staan in het toolregister onder
`(None, naam)` en zijn voor ELKE klant zichtbaar. `POST /api/v1/tools/{naam}/enable|disable` eist alleen
`admin:*`, en dat krijgt de klantbeheerder (rol `admin`, `*:*`) via de databasefallback van `require_scopes`:
dus kon een beheerder van klant A een meegeleverde tool voor ALLE klanten uitzetten. Het register is proces-breed.

Opstelling zoals `test_packs_execute_route.py`: echte app-stack, echte Postgres, de echte rolzaaier en de echte
`admin:*`-controle (geen scope in het token). Klantbeheerder = rol `admin`, GEEN superuser en GEEN platformrol;
platformbeheerder = rol `admin` plus de platformrol `system_admin`.

Per klant aan- en uitzetten van een meegeleverde tool komt later via het inrichtscherm van de koppelingen.

MUTATIEBEWIJS (2026-10-27, productiecode gemuteerd, kopie als terugweg; basis 7 groen):
    controle weg (klantbeheerder mag alles)                  -> ROOD (3)
    niemand mag een meegeleverde tool schakelen              -> ROOD (2: platformbeheerder geweigerd)
    ook de EIGEN tool vraagt de platformrol                  -> ROOD (2: klantbeheerder geweigerd)
    tellers op het gedeelde object (unit)                    -> ROOD (2)
    alles terug                                              -> GROEN (7 integratie, 15 unit)
GEMETEN voor de fix: een klantbeheerder zette `serena` met 200 uit en aan.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_packs_execute_route import (  # noqa: F401 - fixtures
    TENANT,
    _client,
    _gebruiker_met_rol,
    standaardrollen,
)

from src.core.api.v1.tool_broker_shared import available_tools

PLATFORMROL = "system_admin"
MEEGELEVERD = "serena"
EIGEN_TOOL = "eigen_scanner_van_klant_a"


@pytest.fixture(autouse=True)
def _register_terugzetten() -> Iterator[None]:
    voor = {sleutel: dict(waarde) for sleutel, waarde in available_tools.items()}
    yield
    available_tools.clear()
    available_tools.update(voor)


async def _maak_client(
    app: Any, sessie: AsyncSession, *, email: str, platformrol: bool
) -> AsyncGenerator[AsyncClient, None]:
    gebruiker_id = await _gebruiker_met_rol(sessie, "admin", email)
    if platformrol:
        await sessie.execute(
            text(
                "INSERT INTO roles (name, tenant_id, is_active) "
                "SELECT CAST(:n AS varchar), CAST(:t AS integer), true WHERE NOT EXISTS "
                "(SELECT 1 FROM roles WHERE name = :n AND tenant_id = :t)"
            ),
            {"n": PLATFORMROL, "t": TENANT},
        )
        await sessie.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) "
                "SELECT :u, r.id, :t FROM roles r WHERE r.name = :n AND r.tenant_id = :t"
            ),
            {"u": gebruiker_id, "n": PLATFORMROL, "t": TENANT},
        )
        await sessie.commit()
    rollen = ["admin", PLATFORMROL] if platformrol else ["admin"]
    async for client in _client(
        app, sessie, user_id=gebruiker_id, email=email, rollen=rollen, csrf=False
    ):
        yield client


@pytest_asyncio.fixture
async def klantbeheerder(
    integration_app: Any,
    standaardrollen: AsyncSession,  # noqa: F811
    account_actief_zonder_database: None,
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _maak_client(
        integration_app,
        standaardrollen,
        email="klantbeheerder@toolregister.test",
        platformrol=False,
    ):
        yield client


@pytest_asyncio.fixture
async def platformbeheerder(
    integration_app: Any,
    standaardrollen: AsyncSession,  # noqa: F811
    account_actief_zonder_database: None,
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _maak_client(
        integration_app,
        standaardrollen,
        email="platformbeheerder@toolregister.test",
        platformrol=True,
    ):
        yield client


def _eigen_tool_van_klant_a() -> None:
    """De tool van de klant, zoals `register_tool` hem onder `(tenant_id, naam)` zet. Rechtstreeks in het register:
    `POST /api/v1/tools/` wordt in de volledige app door een andere router afgehandeld (die eist `tool_type`), en
    deze test meet het SCHAKELEN, niet het registreren."""
    available_tools[(TENANT, EIGEN_TOOL)] = {
        "id": "tool-eigen-1",
        "name": EIGEN_TOOL,
        "tenant_id": TENANT,
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "finance",
        "capabilities": ["lezen"],
        "parameters_schema": {},
        "description": "van klant A",
    }


def _schakel(client: AsyncClient, naam: str, actie: str) -> Any:
    return client.post(f"/api/v1/tools/{naam}/{actie}")


@pytest.mark.integration
@pytest.mark.asyncio
class TestMeegeleverdeToolSchakelen:
    async def test_een_klantbeheerder_kan_een_meegeleverde_tool_niet_uitzetten(
        self, klantbeheerder: AsyncClient
    ) -> None:
        antwoord = await _schakel(klantbeheerder, MEEGELEVERD, "disable")

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_klantbeheerder_kan_een_meegeleverde_tool_niet_aanzetten(
        self, klantbeheerder: AsyncClient
    ) -> None:
        available_tools[(None, MEEGELEVERD)]["available"] = False

        antwoord = await _schakel(klantbeheerder, MEEGELEVERD, "enable")

        assert antwoord.status_code == 403, antwoord.text

    async def test_na_een_geweigerde_poging_staat_de_meegeleverde_tool_nog_zoals_hij_stond(
        self, klantbeheerder: AsyncClient
    ) -> None:
        await _schakel(klantbeheerder, MEEGELEVERD, "disable")

        assert available_tools[(None, MEEGELEVERD)]["available"] is True

    async def test_een_platformbeheerder_mag_een_meegeleverde_tool_wel_uitzetten(
        self, platformbeheerder: AsyncClient
    ) -> None:
        antwoord = await _schakel(platformbeheerder, MEEGELEVERD, "disable")

        assert (antwoord.status_code, available_tools[(None, MEEGELEVERD)]["available"]) == (
            200,
            False,
        )

    async def test_een_platformbeheerder_mag_een_meegeleverde_tool_wel_aanzetten(
        self, platformbeheerder: AsyncClient
    ) -> None:
        available_tools[(None, MEEGELEVERD)]["available"] = False

        antwoord = await _schakel(platformbeheerder, MEEGELEVERD, "enable")

        assert (antwoord.status_code, available_tools[(None, MEEGELEVERD)]["available"]) == (
            200,
            True,
        )

    async def test_een_klantbeheerder_kan_zijn_eigen_tool_wel_uitzetten(
        self, klantbeheerder: AsyncClient
    ) -> None:
        _eigen_tool_van_klant_a()

        antwoord = await _schakel(klantbeheerder, EIGEN_TOOL, "disable")

        assert (antwoord.status_code, available_tools[(TENANT, EIGEN_TOOL)]["available"]) == (
            200,
            False,
        )

    async def test_een_klantbeheerder_kan_zijn_eigen_tool_wel_aanzetten(
        self, klantbeheerder: AsyncClient
    ) -> None:
        _eigen_tool_van_klant_a()
        available_tools[(TENANT, EIGEN_TOOL)]["available"] = False

        antwoord = await _schakel(klantbeheerder, EIGEN_TOOL, "enable")

        assert (antwoord.status_code, available_tools[(TENANT, EIGEN_TOOL)]["available"]) == (
            200,
            True,
        )
