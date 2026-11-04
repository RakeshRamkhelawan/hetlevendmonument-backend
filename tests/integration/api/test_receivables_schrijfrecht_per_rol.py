"""Meting: welke rol mag op /api/v1/receivables schrijven (Keten B nazorg, punt 2).

Echte app-stack (`register_all_routers`), echte Postgres op netwerkpoort 5455, de echte
`require_permission` op het JWT. De gebruiker wordt gemaakt met het echte seedscript
`scripts/seed_tweede_gebruiker.py`: PRECIES de rol `user` met `*:read`. Alleen CSRF is vervangen
(Redis-gebonden token; de controle zelf heeft eigen tests) en `get_current_user` wijst naar deze
gebruiker.

Wat gemeten wordt: lezen mag (200), elke schrijfroute weigert met 403
de Nederlandse melding "U mag debiteuren niet invoeren of wijzigen ...".

Rolmodel debiteuren, optie A (plan-van-aanpak-nazorg deel II punt 1): de rol `debiteuren`
(`receivables:read` + `receivables:write`, gezaaid met `--rol debiteuren` van hetzelfde script)
komt op elke schrijfroute voorbij de rolcontrole, maar kan een HITL-ticket NIET goedkeuren:
`POST /api/v1/tools/hitl/approve` geeft 403 via `_require_approver`.
Tegenproef: de gezaaide beheerder (rol `admin`, `*:*`) komt bij dezelfde routes WEL voorbij de
rolcontrole (geen 403) -- anders is "alles weigeren" een geldige uitkomst. Goedkeuren is sinds
2026-10-09 een procesbevoegdheid (ADR-039): de beheerder krijgt daar 403, de rol `goedkeurder` 404.

Wat NIET gemeten wordt: zelfgoedkeuring en vier ogen bij het goedkeuren -- die hebben eigen tests.
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

URL = "/api/v1/receivables"
SCRIPT_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed_tweede_gebruiker.py"

_FACTUUR: dict[str, Any] = {
    "customer_name": "Bakkerij De Korst",
    "customer_email": "administratie@dekorst.example",
    "invoice_number": "F-ROL-001",
    "amount": "100.00",
    "currency": "EUR",
    "due_date": "2026-09-01",
}

SCHRIJFROUTES: list[tuple[str, str, dict[str, Any]]] = [
    ("POST", URL, _FACTUUR),
    ("PATCH", f"{URL}/1", {"status": "betaald"}),
]
# `/reminder-proposals` vraagt sinds wfb-dag1 stap 7 `receivables:propose`, niet `write`:
# per rol getoetst in test_receivables_voorstelrecht_per_rol.py.


def _seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_seed_tweede_gebruiker_rol", SCRIPT_PAD)
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


@pytest_asyncio.fixture
async def medewerker(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    email = "medewerker@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        postgres_session, tenant_id=1, email=email, password="medewerker-wachtwoord"
    )
    async for client in _client(
        integration_app, postgres_session, user_id=user_id, email=email, rollen=["user"]
    ):
        yield client


@pytest_asyncio.fixture
async def debiteuren(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    email = "debiteuren@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        postgres_session,
        tenant_id=1,
        email=email,
        password="debiteuren-wachtwoord",
        rol_naam="debiteuren",
    )
    async for client in _client(
        integration_app, postgres_session, user_id=user_id, email=email, rollen=["debiteuren"]
    ):
        yield client


@pytest_asyncio.fixture
async def goedkeurder(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    email = "goedkeurder@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        postgres_session,
        tenant_id=1,
        email=email,
        password="goedkeurder-wachtwoord",
        rol_naam="goedkeurder",
    )
    async for client in _client(
        integration_app, postgres_session, user_id=user_id, email=email, rollen=["goedkeurder"]
    ):
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
class TestRolUser:
    async def test_lezen_mag(self, medewerker: AsyncClient) -> None:
        antwoord = await medewerker.get(URL)
        assert antwoord.status_code == 200, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_schrijven_wordt_geweigerd(
        self, medewerker: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await medewerker.request(methode, pad, json=body)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == (
            "U mag debiteuren niet invoeren of wijzigen. Vraag de beheerder om u de rol "
            "'debiteuren' te geven."
        ), antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestRolDebiteuren:
    async def test_lezen_mag(self, debiteuren: AsyncClient) -> None:
        antwoord = await debiteuren.get(URL)
        assert antwoord.status_code == 200, antwoord.text

    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_komt_voorbij_de_rolcontrole(
        self, debiteuren: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await debiteuren.request(methode, pad, json=body)

        assert antwoord.status_code != 403, antwoord.text

    async def test_toevoegen_slaagt(self, debiteuren: AsyncClient) -> None:
        antwoord = await debiteuren.post(URL, json={**_FACTUUR, "invoice_number": "F-ROL-DEB"})

        assert antwoord.status_code == 201, antwoord.text

    async def test_kan_geen_ticket_goedkeuren(self, debiteuren: AsyncClient) -> None:
        antwoord = await debiteuren.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-ONBEKEND"}
        )

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestTegenproefBeheerder:
    @pytest.mark.parametrize(("methode", "pad", "body"), SCHRIJFROUTES)
    async def test_beheerder_komt_voorbij_de_rolcontrole(
        self, beheerder: AsyncClient, methode: str, pad: str, body: dict[str, Any]
    ) -> None:
        antwoord = await beheerder.request(methode, pad, json=body)

        assert antwoord.status_code != 403, antwoord.text

    async def test_beheerder_zonder_goedkeurrecht_wordt_geweigerd(
        self, beheerder: AsyncClient
    ) -> None:
        """Goedkeuren is een procesbevoegdheid (ADR-039): `*:*` geeft het niet."""
        antwoord = await beheerder.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-ONBEKEND"}
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_goedkeurder_komt_voorbij_de_goedkeurcontrole(
        self, goedkeurder: AsyncClient
    ) -> None:
        """Tegenproef: zelfde verzoek geeft bij de goedkeurder 404 (onbekend ticket), dus de 403
        hierboven komt van de rechtencontrole en niet van iets anders."""
        antwoord = await goedkeurder.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-ONBEKEND"}
        )

        assert antwoord.status_code == 404, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthMeGeeftDeRechten:
    """`/auth/me` levert de rechtenlijst waar de frontend de debiteurenknoppen op zet."""

    async def test_debiteuren_krijgt_receivables_write(self, debiteuren: AsyncClient) -> None:
        antwoord = await debiteuren.get("/api/v1/auth/me")

        assert antwoord.status_code == 200, antwoord.text
        assert "receivables:write" in antwoord.json()["permissions"], antwoord.text

    async def test_user_krijgt_geen_schrijfrecht(self, medewerker: AsyncClient) -> None:
        antwoord = await medewerker.get("/api/v1/auth/me")

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["permissions"] == ["*:read"], antwoord.text
