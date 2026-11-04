"""Meting: welke rol mag op /api/v1/payables lezen en schrijven (crediteuren dag 1, rollen en rechten).

Echte app-stack (`register_all_routers`), echte Postgres op netwerkpoort 5455, de echte `require_resource_permission` op het JWT. De
gebruikers worden gemaakt met het echte seedscript `scripts/seed_tweede_gebruiker.py` (`--rol <naam>`); alleen CSRF is vervangen en
`get_current_user` wijst naar de gemaakte gebruiker. Zelfde opzet als `test_receivables_schrijfrecht_per_rol.py`.

Wat gemeten wordt (brief: "een eigen smal recht `payables:read` en `payables:write`, een rol `crediteuren`; beheer los van goedkeuren"):
- de rol `crediteuren` mag lezen en schrijven, en kan GEEN goedkeuring van een ticket geven;
- de rol `goedkeurder` mag lezen (`payables:read`, commit 51b9cc50) maar niet schrijven;
- een rol zonder crediteurenrecht (`debiteuren`, `goedkeurder_hr`) komt er niet in: 403 met de Nederlandse melding.
  Dat is de scheiding tussen de processen: een debiteurenadministrateur ziet geen inkoopfacturen;
- tegenproef: de beheerder (`*:*`) komt wel voorbij de rolcontrole, anders is "alles weigeren" een geldige uitkomst.

Bewust NIET getoetst met de rol `user` van het seedscript: die krijgt daar `*:read` en ziet dus alles. In de gezaaide standaardrollen van
`ensure_default_roles` heeft `user` geen `payables`-recht; dat legt `tests/architecture/test_role_permissions_cover_every_seeded_role.py` vast.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncGenerator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/v1/payables"
SCRIPT_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed_tweede_gebruiker.py"

LEESMELDING = (
    "U mag de inkoopfacturen niet bekijken. Vraag de beheerder om u de rol 'crediteuren' te geven."
)
SCHRIJFMELDING = "U mag inkoopfacturen en leveranciers niet invoeren of wijzigen. Vraag de beheerder om u de rol 'crediteuren' te geven."

_FACTUUR: dict[str, Any] = {
    "supplier_id": 1,
    "invoice_number": "INK-ROL-001",
    "amount_cents": 10000,
    "currency": "EUR",
    "invoice_date": "2026-10-01",
    "due_date": "2026-10-31",
}

LEESROUTES: list[tuple[str, str]] = [("GET", URL), ("GET", f"{URL}/suppliers")]
SCHRIJFROUTES: list[tuple[str, str, dict[str, Any]]] = [
    ("POST", URL, _FACTUUR),
    ("POST", f"{URL}/suppliers", {"name": "Rol BV"}),
    ("PATCH", f"{URL}/1", {"status": "gecontroleerd"}),
]


def _seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_seed_tweede_gebruiker_payables", SCRIPT_PAD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _client(
    app: Any, session: AsyncSession, *, user_id: int, email: str, rollen: list[str]
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=1, roles=rollen)
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        validate_csrf_token: _geen_csrf,
        get_current_user: lambda: gebruiker,
    }
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=1)
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


async def _rol_client(
    app: Any, session: AsyncSession, rol: str
) -> AsyncGenerator[AsyncClient, None]:
    email = f"{rol}@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        session, tenant_id=1, email=email, password=f"{rol}-wachtwoord", rol_naam=rol
    )
    async for client in _client(app, session, user_id=user_id, email=email, rollen=[rol]):
        yield client


@pytest_asyncio.fixture
async def crediteuren(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _rol_client(integration_app, postgres_session, "crediteuren"):
        yield client


@pytest_asyncio.fixture
async def debiteuren(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _rol_client(integration_app, postgres_session, "debiteuren"):
        yield client


@pytest_asyncio.fixture
async def goedkeurder(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _rol_client(integration_app, postgres_session, "goedkeurder"):
        yield client


@pytest_asyncio.fixture(params=["debiteuren", "goedkeurder_hr"])
async def zonder_recht(
    request: pytest.FixtureRequest, integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Een rol zonder crediteurenrecht; een geparametriseerde fixture, want `getfixturevalue` kan een async fixture niet aan."""
    async for client in _rol_client(integration_app, postgres_session, request.param):
        yield client


async def _eigen_rol_client(
    app: Any, session: AsyncSession, rol: str, rechten: tuple[tuple[str, str], ...]
) -> AsyncGenerator[AsyncClient, None]:
    """Een gebruiker met PRECIES deze rechten, voor een rol die het seedscript niet kent."""
    seed = _seed()
    seed.ROLLEN[rol] = (rol, rechten)
    email = f"{rol}@integration.test"
    user_id = await seed.maak_tweede_gebruiker(
        session, tenant_id=1, email=email, password=f"{rol}-wachtwoord", rol_naam=rol
    )
    async for client in _client(app, session, user_id=user_id, email=email, rollen=[rol]):
        yield client


@pytest_asyncio.fixture
async def medewerker(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Alleen `payables:read`: wel mogen lezen, niet mogen schrijven."""
    async for client in _eigen_rol_client(
        integration_app, postgres_session, "crediteuren_lezer", (("payables", "read"),)
    ):
        yield client


@pytest_asyncio.fixture(params=[("user", (("*", "read"),)), ("schrijf_joker", (("*", "write"),))], ids=["joker-lezen", "joker-schrijven"])
async def jokerrecht(
    request: pytest.FixtureRequest, integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Een jokerrecht (`*:read`, `*:write`), zoals een bestaande tenant het voor de rol `user` heeft."""
    rol, rechten = request.param
    async for client in _eigen_rol_client(integration_app, postgres_session, rol, rechten):
        yield client


@pytest_asyncio.fixture
async def beheerder(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client(
        integration_app,
        postgres_session,
        user_id=1,
        email="admin@integration.test",
        rollen=["admin"],
    ):
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
class TestRolCrediteuren:
    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_lezen_mag(self, crediteuren: AsyncClient, methode: str, pad: str) -> None:
        antwoord = await crediteuren.request(methode, pad)

        assert antwoord.status_code == 200, antwoord.text

    async def test_leverancier_en_factuur_vastleggen_slaagt(self, crediteuren: AsyncClient) -> None:
        leverancier = await crediteuren.post(f"{URL}/suppliers", json={"name": "Rol BV"})
        assert leverancier.status_code == 201, leverancier.text

        factuur = await crediteuren.post(
            URL, json={**_FACTUUR, "supplier_id": leverancier.json()["data"]["id"]}
        )

        assert factuur.status_code == 201, factuur.text

    async def test_een_factuur_controleren_slaagt(self, crediteuren: AsyncClient) -> None:
        leverancier = (await crediteuren.post(f"{URL}/suppliers", json={"name": "Rol BV"})).json()[
            "data"
        ]["id"]
        factuur = (
            await crediteuren.post(URL, json={**_FACTUUR, "supplier_id": leverancier})
        ).json()["data"]

        antwoord = await crediteuren.patch(
            f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"}
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_kan_geen_ticket_goedkeuren(self, crediteuren: AsyncClient) -> None:
        """Beheer los van goedkeuren (ADR-039): de rol crediteuren heeft geen goedkeurrecht."""
        antwoord = await crediteuren.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-ONBEKEND"}
        )

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestAndereRollenKomenErNietIn:
    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_lezen_wordt_geweigerd(self, zonder_recht: AsyncClient, methode: str, pad: str) -> None:
        antwoord = await zonder_recht.request(methode, pad)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == LEESMELDING, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_schrijven_wordt_geweigerd(
        self, zonder_recht: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await zonder_recht.request(methode, pad, json=body)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == SCHRIJFMELDING, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeGoedkeurderMagLezenEnNietSchrijven:
    """De rol `goedkeurder` kreeg in commit 51b9cc50 BEWUST `payables:read` en `payables:approve`
    (`src/core/services/rbac_service.py`, reden daar: leesrecht om de factuur te zien die hij goedkeurt). Voorheen stond
    hij in `TestAndereRollenKomenErNietIn` bij "geen recht"; die uitkomst is met dat besluit verouderd (CI-run
    40674951559). Wat blijft: hij mag niets schrijven (`payables:write` is een eigen recht)."""

    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_lezen_mag(self, goedkeurder: AsyncClient, methode: str, pad: str) -> None:
        antwoord = await goedkeurder.request(methode, pad)

        assert antwoord.status_code == 200, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_schrijven_wordt_geweigerd(
        self, goedkeurder: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await goedkeurder.request(methode, pad, json=body)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == SCHRIJFMELDING, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestAlleenLezen:
    """Wie mag lezen mag daarom nog niet schrijven: `payables:write` is een eigen recht (zonder deze klasse blijft het wegnemen
    van de schrijfcontrole op een route onopgemerkt, want de andere rollen komen er al niet in)."""

    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_lezen_mag(self, medewerker: AsyncClient, methode: str, pad: str) -> None:
        antwoord = await medewerker.request(methode, pad)

        assert antwoord.status_code == 200, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_schrijven_wordt_geweigerd(
        self, medewerker: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await medewerker.request(methode, pad, json=body)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == SCHRIJFMELDING, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenJokerrechtGeeftGeenCrediteurenrecht:
    """Gate 2 (HIGH): `*:read` gaf elke medewerker met de rol `user` (zo staat hij in bestaande omgevingen) de leveranciers met
    IBAN en alle inkoopfacturen. `payables` is daarom een eigen resource zoals `hr`: alleen een recht op de resource zelf, of `*:*`."""

    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_lezen_wordt_geweigerd(self, jokerrecht: AsyncClient, methode: str, pad: str) -> None:
        antwoord = await jokerrecht.request(methode, pad)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == LEESMELDING, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_schrijven_wordt_geweigerd(
        self, jokerrecht: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await jokerrecht.request(methode, pad, json=body)

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestTegenproefBeheerder:
    @pytest.mark.parametrize(("methode", "pad"), LEESROUTES)
    async def test_beheerder_mag_lezen(
        self, beheerder: AsyncClient, methode: str, pad: str
    ) -> None:
        antwoord = await beheerder.request(methode, pad)

        assert antwoord.status_code == 200, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_beheerder_komt_voorbij_de_rolcontrole(
        self, beheerder: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await beheerder.request(methode, pad, json=body)

        assert antwoord.status_code != 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthMeGeeftDeRechten:
    """`/auth/me` levert de rechtenlijst waar de frontend het menu en de knoppen op zet."""

    async def test_crediteuren_krijgt_lees_en_schrijfrecht(self, crediteuren: AsyncClient) -> None:
        antwoord = await crediteuren.get("/api/v1/auth/me")

        assert antwoord.status_code == 200, antwoord.text
        rechten = antwoord.json()["permissions"]
        assert "payables:read" in rechten and "payables:write" in rechten, antwoord.text

    async def test_crediteuren_krijgt_precies_deze_twee_rechten(self, crediteuren: AsyncClient) -> None:
        """Smal: geen goedkeurrecht, geen leesrecht op andere processen, geen jokerrecht."""
        antwoord = await crediteuren.get("/api/v1/auth/me")

        assert sorted(antwoord.json()["permissions"]) == ["payables:read", "payables:write"], antwoord.text

    async def test_debiteuren_krijgt_geen_crediteurenrecht(self, debiteuren: AsyncClient) -> None:
        antwoord = await debiteuren.get("/api/v1/auth/me")

        assert antwoord.status_code == 200, antwoord.text
        assert not [r for r in antwoord.json()["permissions"] if r.startswith("payables")], (
            antwoord.text
        )
