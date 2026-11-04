"""Meting: een globaal pakket goedkeuren mag alleen de beheerder (ADR-039, brief 2026-10-10).

`POST /api/v1/pack-feedback/global/{pack_id}/approve` gaf een pakket vrij voor de hele klant, met
alleen `get_current_user` als controle en `# TODO: Add admin check` in de code: elke ingelogde
gebruiker kon het. Rakesh, 2026-10-09: "een beheerder is iemand die het beheer van de applicatie
inricht, dus welke pakketten, en beheert het pakket."

Dit is BEHEER en geen procesgoedkeuring: het recht heet `packs:manage` en alleen de beheerder
(`*:*`) heeft het. Opstelling zoals `test_packs_execute_route.py`: echte app-stack, echte
Postgres, de echte rolzaaier `ensure_default_roles` en de echte rolcontrole. De rol
`goedkeurder` komt uit de zaaier (ADR-039, `receivables:approve`): wie een PROCES mag goedkeuren, mag
daarmee geen PAKKET vrijgeven.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_packs_execute_route import (  # noqa: F401 - fixtures
    TENANT,
    _client,
    _gebruiker_met_rol,
    alleen_lezen,
    beheerder,
    beheerder_met_echte_csrf,
    medewerker,
    redacteur,
    standaardrollen,
)

from src.core.governance.models import GlobalPack

URL = "/api/v1/pack-feedback/global/{pack_id}/approve"


@pytest_asyncio.fixture
async def goedkeurder(
    integration_app: Any,
    standaardrollen: AsyncSession,  # noqa: F811
) -> AsyncGenerator[AsyncClient, None]:
    """De GEZAAIDE rol `goedkeurder` (`receivables:approve`): een PROCES goedkeuren, geen pakketten beheren.

    Sinds 8022e99b (ADR-039) zaait `ensure_default_roles` die rol zelf. Hier stond een eigen `Role` met
    dezelfde naam, en dat gaf `UniqueViolation idx_role_tenant_name` in elke opbouw (gemeten 2026-10-26).
    De test gebruikt dus de echte rol; dat het geen `packs:manage` heeft toetst de 403-test hieronder.
    """
    email = "pakket-goedkeurder@integration.test"
    user_id = await _gebruiker_met_rol(standaardrollen, "goedkeurder", email)
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=user_id,
        email=email,
        rollen=["goedkeurder"],
        csrf=False,
    ):
        yield client


@pytest.fixture
def zonder_recht(
    medewerker: AsyncClient,  # noqa: F811
    redacteur: AsyncClient,  # noqa: F811
    goedkeurder: AsyncClient,
    alleen_lezen: AsyncClient,  # noqa: F811
) -> dict[str, AsyncClient]:
    """De vier rollen zonder `packs:manage`, per naam (async fixtures zijn niet op naam op te halen)."""
    return {
        "medewerker": medewerker,
        "redacteur": redacteur,
        "goedkeurder": goedkeurder,
        "alleen_lezen": alleen_lezen,
    }


@pytest_asyncio.fixture
async def wachtend_pakket(standaardrollen: AsyncSession) -> GlobalPack:  # noqa: F811
    pakket = GlobalPack(
        tenant_id=TENANT,
        contributor_user_id=None,
        name="Testpakket",
        description="wacht op vrijgave",
        pack_data={"status": "pending_review", "department": "finance"},
    )
    standaardrollen.add(pakket)
    await standaardrollen.commit()
    return pakket


async def _status(sessie: AsyncSession, pakket: GlobalPack) -> object:
    await sessie.refresh(pakket)
    return pakket.pack_data.get("status")


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagEenPakketVrijgeven:
    @pytest.mark.parametrize(
        "client_naam", ["medewerker", "redacteur", "goedkeurder", "alleen_lezen"]
    )
    async def test_een_rol_zonder_packs_manage_krijgt_403(
        self,
        zonder_recht: dict[str, AsyncClient],
        wachtend_pakket: GlobalPack,
        client_naam: str,
    ) -> None:
        client = zonder_recht[client_naam]

        antwoord = await client.post(URL.format(pack_id=wachtend_pakket.id))

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing permission: packs:manage", antwoord.text

    @pytest.mark.parametrize(
        "client_naam", ["medewerker", "redacteur", "goedkeurder", "alleen_lezen"]
    )
    async def test_een_geweigerde_aanvraag_laat_het_pakket_wachten(
        self,
        zonder_recht: dict[str, AsyncClient],
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
        client_naam: str,
    ) -> None:
        client = zonder_recht[client_naam]

        await client.post(URL.format(pack_id=wachtend_pakket.id))

        assert await _status(standaardrollen, wachtend_pakket) == "pending_review"

    async def test_de_beheerder_geeft_het_pakket_vrij(
        self,
        beheerder: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        antwoord = await beheerder.post(URL.format(pack_id=wachtend_pakket.id))

        assert antwoord.status_code == 200, antwoord.text
        assert await _status(standaardrollen, wachtend_pakket) == "approved"

    async def test_de_beheerder_krijgt_404_voor_een_onbekend_pakket(
        self,
        beheerder: AsyncClient,  # noqa: F811
    ) -> None:
        antwoord = await beheerder.post(URL.format(pack_id=UUID(int=0)))

        assert antwoord.status_code == 404, antwoord.text

    async def test_zonder_csrf_token_wordt_geweigerd(
        self,
        beheerder_met_echte_csrf: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        antwoord = await beheerder_met_echte_csrf.post(URL.format(pack_id=wachtend_pakket.id))

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing CSRF token", antwoord.text
        assert await _status(standaardrollen, wachtend_pakket) == "pending_review"


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuditregel:
    async def _aantal(self, sessie: AsyncSession) -> int:
        # Route en test delen een sessie zonder de commit van `get_db`: eerst wegschrijven.
        # BEPERKING: dit bewijst dat de regel in de sessie staat, niet dat `get_db` hem daarna
        # commit; dat staat in `database.py` (`session.commit()` na de `yield`), niet in deze test.
        await sessie.flush()
        rij = (
            await sessie.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'global_pack.approved'")
            )
        ).scalar_one()
        return int(rij)

    async def test_elke_vrijgave_laat_een_auditregel_achter(
        self,
        beheerder: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        voor = await self._aantal(standaardrollen)

        await beheerder.post(URL.format(pack_id=wachtend_pakket.id))

        assert await self._aantal(standaardrollen) - voor == 1

    async def test_de_auditregel_noemt_het_pakket_en_de_beheerder(
        self,
        beheerder: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        await beheerder.post(URL.format(pack_id=wachtend_pakket.id))
        await standaardrollen.flush()

        rij = (
            await standaardrollen.execute(
                text(
                    "SELECT resource, user_id FROM audit_logs "
                    "WHERE action = 'global_pack.approved' ORDER BY id DESC LIMIT 1"
                )
            )
        ).one()
        assert (rij[0], rij[1]) == (f"global_pack:{wachtend_pakket.id}", 1)

    async def test_een_geweigerde_aanvraag_laat_geen_auditregel_achter(
        self,
        medewerker: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        voor = await self._aantal(standaardrollen)

        await medewerker.post(URL.format(pack_id=wachtend_pakket.id))

        assert await self._aantal(standaardrollen) == voor
