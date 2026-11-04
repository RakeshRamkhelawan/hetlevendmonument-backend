"""Meting: een wachtend globaal pakket is niet zichtbaar voor gewone gebruikers (ADR-039, 2026-10-10).

Gemeld door de review van `3ae028e0`: `GET /global/pending` zei "admin only" maar liet elke
ingelogde gebruiker de wachtende pakketten lezen, en `POST /global/search` en
`GET /global/{pack_id}` filterden niet op de status, dus goedkeuren had geen gevolg voor
zichtbaarheid. Besluit regie: `pending` alleen met `packs:manage`; zoeken en ophalen tonen een
gewone gebruiker alleen `approved` (een wachtend pakket geeft 404, geen 403, zodat het bestaan niet
wordt prijsgegeven); met `packs:manage` alles. `/submit` en `/contribute` blijven voor iedereen.

Ook de test die bij `3ae028e0` ontbrak: een beheerder van een ANDERE klant kan een pakket van deze
klant niet vrijgeven (404) en ziet het niet.

Opstelling: zoals `test_globaal_pakket_goedkeuren_alleen_beheerder.py` (echte app-stack, echte
Postgres, echte rolzaaier en rolcontrole).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_globaal_pakket_goedkeuren_alleen_beheerder import (  # noqa: F401 - fixtures
    goedkeurder,
    wachtend_pakket,
    zonder_recht,
)
from tests.integration.test_packs_execute_route import (  # noqa: F401 - fixtures
    TENANT,
    _client,
    alleen_lezen,
    beheerder,
    medewerker,
    redacteur,
    standaardrollen,
)

from src.core.governance.models import GlobalPack
from src.core.models.rbac_models import Role, Tenant, User, user_roles
from src.core.services.rbac_service import RBACService

PENDING = "/api/v1/pack-feedback/global/pending"
SEARCH = "/api/v1/pack-feedback/global/search"
GET = "/api/v1/pack-feedback/global/{pack_id}"
APPROVE = "/api/v1/pack-feedback/global/{pack_id}/approve"
ZOEK = {"query": "testpakket"}
ZONDER_RECHT = ["medewerker", "redacteur", "goedkeurder", "alleen_lezen"]


@pytest_asyncio.fixture
async def goedgekeurd_pakket(standaardrollen: AsyncSession) -> GlobalPack:  # noqa: F811
    pakket = GlobalPack(
        tenant_id=TENANT,
        contributor_user_id=None,
        name="Goedgekeurd testpakket",
        description="vrijgegeven",
        pack_data={"status": "approved", "department": "finance"},
    )
    standaardrollen.add(pakket)
    await standaardrollen.commit()
    return pakket


@pytest_asyncio.fixture
async def beheerder_van_een_andere_klant(
    integration_app: Any,
    standaardrollen: AsyncSession,  # noqa: F811
) -> AsyncGenerator[AsyncClient, None]:
    """Een beheerder (`*:*`) van klant B; klant A is `TENANT`."""
    klant_b = Tenant(
        name="Klant B pakketten",
        slug="klant-b-pakketten",
        is_active=True,
        max_users=10,
        max_agents=50,
        max_storage_gb=5,
    )
    standaardrollen.add(klant_b)
    await standaardrollen.commit()
    await RBACService(standaardrollen).ensure_default_roles(int(klant_b.id))
    rol_id = (
        await standaardrollen.execute(
            select(Role.id).where(Role.tenant_id == klant_b.id, Role.name == "admin")
        )
    ).scalar_one()
    gebruiker = User(
        email="beheerder-klant-b@integration.test",
        hashed_password="x",
        tenant_id=klant_b.id,
        is_active=True,
        is_superuser=False,
    )
    standaardrollen.add(gebruiker)
    await standaardrollen.flush()
    await standaardrollen.execute(
        user_roles.insert().values(user_id=gebruiker.id, role_id=rol_id, tenant_id=klant_b.id)
    )
    await standaardrollen.commit()
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=int(gebruiker.id),
        email="beheerder-klant-b@integration.test",
        rollen=["admin"],
        csrf=False,
        tenant=int(klant_b.id),
    ):
        yield client


def _ids(antwoord: Any) -> set[str]:
    return {p["id"] for p in antwoord.json()["data"]}


@pytest.mark.integration
@pytest.mark.asyncio
class TestPendingIsBeheer:
    @pytest.mark.parametrize("naam", ZONDER_RECHT)
    async def test_een_rol_zonder_packs_manage_krijgt_403(
        self, zonder_recht: dict[str, AsyncClient], wachtend_pakket: GlobalPack, naam: str
    ) -> None:
        antwoord = await zonder_recht[naam].get(PENDING)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing permission: packs:manage", antwoord.text

    async def test_de_beheerder_ziet_het_wachtende_pakket(
        self,
        beheerder: AsyncClient,
        wachtend_pakket: GlobalPack,  # noqa: F811
    ) -> None:
        antwoord = await beheerder.get(PENDING)

        assert antwoord.status_code == 200, antwoord.text
        assert str(wachtend_pakket.id) in _ids(antwoord)


@pytest.mark.integration
@pytest.mark.asyncio
class TestZoeken:
    @pytest.mark.parametrize("naam", ZONDER_RECHT)
    async def test_een_gewone_gebruiker_vindt_alleen_het_goedgekeurde_pakket(
        self,
        zonder_recht: dict[str, AsyncClient],
        wachtend_pakket: GlobalPack,
        goedgekeurd_pakket: GlobalPack,
        naam: str,
    ) -> None:
        antwoord = await zonder_recht[naam].post(SEARCH, json=ZOEK)

        assert _ids(antwoord) == {str(goedgekeurd_pakket.id)}

    async def test_de_beheerder_vindt_beide(
        self,
        beheerder: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        goedgekeurd_pakket: GlobalPack,
    ) -> None:
        antwoord = await beheerder.post(SEARCH, json=ZOEK)

        assert _ids(antwoord) == {str(wachtend_pakket.id), str(goedgekeurd_pakket.id)}

    async def test_het_totaal_telt_het_verborgen_pakket_niet_mee(
        self,
        medewerker: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        goedgekeurd_pakket: GlobalPack,
    ) -> None:
        """Anders verraadt `total` dat er een wachtend pakket is."""
        antwoord = await medewerker.post(SEARCH, json=ZOEK)

        assert antwoord.json()["total"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestOphalen:
    @pytest.mark.parametrize("naam", ZONDER_RECHT)
    async def test_een_wachtend_pakket_geeft_404_voor_een_gewone_gebruiker(
        self, zonder_recht: dict[str, AsyncClient], wachtend_pakket: GlobalPack, naam: str
    ) -> None:
        antwoord = await zonder_recht[naam].get(GET.format(pack_id=wachtend_pakket.id))

        assert antwoord.status_code == 404, antwoord.text

    async def test_een_geweigerd_ophalen_telt_geen_gebruik(
        self,
        medewerker: AsyncClient,  # noqa: F811
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        await medewerker.get(GET.format(pack_id=wachtend_pakket.id))
        await standaardrollen.refresh(wachtend_pakket)

        assert wachtend_pakket.pack_data.get("usage_count", 0) == 0

    async def test_een_goedgekeurd_pakket_blijft_voor_een_gewone_gebruiker_te_lezen(
        self,
        medewerker: AsyncClient,
        goedgekeurd_pakket: GlobalPack,  # noqa: F811
    ) -> None:
        antwoord = await medewerker.get(GET.format(pack_id=goedgekeurd_pakket.id))

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_beheerder_leest_ook_een_wachtend_pakket(
        self,
        beheerder: AsyncClient,
        wachtend_pakket: GlobalPack,  # noqa: F811
    ) -> None:
        antwoord = await beheerder.get(GET.format(pack_id=wachtend_pakket.id))

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenAndereKlant:
    async def test_een_beheerder_van_klant_b_kan_een_pakket_van_klant_a_niet_vrijgeven(
        self,
        beheerder_van_een_andere_klant: AsyncClient,
        wachtend_pakket: GlobalPack,
        standaardrollen: AsyncSession,  # noqa: F811
    ) -> None:
        antwoord = await beheerder_van_een_andere_klant.post(
            APPROVE.format(pack_id=wachtend_pakket.id)
        )
        await standaardrollen.refresh(wachtend_pakket)

        assert antwoord.status_code == 404, antwoord.text
        assert wachtend_pakket.pack_data.get("status") == "pending_review"

    async def test_een_beheerder_van_klant_b_ziet_het_pakket_van_klant_a_niet(
        self, beheerder_van_een_andere_klant: AsyncClient, wachtend_pakket: GlobalPack
    ) -> None:
        in_lijst = await beheerder_van_een_andere_klant.get(PENDING)
        direct = await beheerder_van_een_andere_klant.get(GET.format(pack_id=wachtend_pakket.id))

        assert str(wachtend_pakket.id) not in _ids(in_lijst)
        assert direct.status_code == 404, direct.text
