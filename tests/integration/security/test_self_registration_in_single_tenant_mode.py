"""Zelfregistratie in `single_tenant`: de EERSTE aanmelder wordt beheerder, daarna is de deur dicht.

Besluit Rakesh 2026-10-04 (brief, "Het besluit" punt 2): in modus `single_tenant` mag de
publieke registratie alleen de eerste gebruiker aanmaken (beheerder van de ene tenant);
daarna voegen beheerders gebruikers toe. De brief noemt dit een AANNAME van de regie.

**Aanname van de testspecialist over "de eerste".** De beginstand hier is een LEGE
installatie: nul tenants en nul gebruikers (de module leegt de tabellen zelf, zie
`lege_installatie`). Een installatie waar al een tenant staat maar nog geen gebruiker, of waar
`seed.py` al een beheerder zaait, is NIET vastgepind; de brief zegt daar niets over en de
bouwer beslist. Meld dat als de meting iets anders laat zien.

**Wegwerpdatabase.** De test-PostgreSQL is de gedeelde testdatabase (poort 5455), geen
wegwerpdatabase; `reset_db_per_module` leegt en zaait hem bij elke module opnieuw, en deze
module leegt hem nog verder (`TRUNCATE ... CASCADE` op `tenants`). Geen `DROP`.

De database verbindt als `postgres` en omzeilt RLS; zie `_voordeur_hulp.py`.

**Mutatiebewijs** (tegen een wegwerp-referentie-implementatie in een KOPIE, zie het rapport):
- single_tenant-controle weghalen -> `test_the_second_public_registration_is_refused` ROOD
- de controle ook in `saas` laten gelden -> `test_in_saas_mode_the_second_registration_works` ROOD
- eerste aanmelder niet admin -> `test_the_first_registration_becomes_admin_of_the_only_tenant` ROOD
- een tweede tenant aanmaken in single_tenant -> `..._the_only_tenant` ROOD
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from tests.integration.security._voordeur_hulp import (  # noqa: F401  (fixtures)
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    log_in,
    registreer,
    rolnamen_van_gebruiker,
    tenant_ids,
    tenant_van_gebruiker,
    unieke_email,
    voer_uit,
    zet_deploymentmodus,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def lege_installatie() -> Iterator[None]:
    """Nul tenants en nul gebruikers: de toestand van een verse single_tenant-installatie."""
    voer_uit("TRUNCATE TABLE tenants RESTART IDENTITY CASCADE")
    yield


def _aantal(tabel: str) -> int:
    return int(een_waarde(f"SELECT count(*) FROM {tabel}"))  # noqa: S608 - vaste tabelnaam


async def test_the_first_registration_becomes_admin_of_the_only_tenant(
    client: AsyncClient, lege_installatie: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    zet_deploymentmodus(monkeypatch, "single_tenant")
    email = unieke_email("eerste")

    r = await registreer(client, email)

    assert r.status_code == 201, f"{r.status_code}: {r.text}"
    assert len(tenant_ids()) == 1 and rolnamen_van_gebruiker(email) == {"admin"}
    assert tenant_van_gebruiker(email) == [r.json()["tenant_id"]]


async def test_the_first_admin_in_single_tenant_mode_is_not_refused_on_agents(
    client: AsyncClient, lege_installatie: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    zet_deploymentmodus(monkeypatch, "single_tenant")
    email = unieke_email("eerste")
    aangemeld = await registreer(client, email)
    assert aangemeld.status_code == 201, f"{aangemeld.status_code}: {aangemeld.text}"
    token = await log_in(client, email)

    r = await client.get("/api/v1/agents/", headers=bearer(token))

    assert r.status_code == 200, f"{r.status_code}: {r.text}"


async def test_the_second_public_registration_is_refused(
    client: AsyncClient, lege_installatie: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    zet_deploymentmodus(monkeypatch, "single_tenant")
    eerste = await registreer(client, unieke_email("eerste"))
    assert eerste.status_code == 201, f"de eerste moet slagen: {eerste.status_code}: {eerste.text}"

    tweede = await registreer(client, unieke_email("tweede"))

    assert tweede.status_code in (400, 403, 409), f"{tweede.status_code}: {tweede.text}"


async def test_the_refused_second_registration_leaves_nothing_behind(
    client: AsyncClient, lege_installatie: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Geweigerd betekent: geen tweede tenant en geen tweede gebruiker, ook geen halve."""
    zet_deploymentmodus(monkeypatch, "single_tenant")
    await registreer(client, unieke_email("eerste"))
    tweede = unieke_email("tweede")

    await registreer(client, tweede)

    assert (_aantal("tenants"), _aantal("users")) == (1, 1) and tenant_van_gebruiker(tweede) == []


async def test_in_saas_mode_the_second_registration_works(
    client: AsyncClient, lege_installatie: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GROEN-helft in zijn betekenis, ROOD vandaag omdat registreren zelf nog niet werkt.

    De dichtgaande deur hoort ALLEEN bij `single_tenant`. Zonder deze test is 'altijd na
    de eerste weigeren' een geldige oplossing en kan in `saas` niemand zich meer melden.
    """
    zet_deploymentmodus(monkeypatch, "saas")
    eerste = await registreer(client, unieke_email("a"))
    assert eerste.status_code == 201, f"{eerste.status_code}: {eerste.text}"

    tweede = await registreer(client, unieke_email("b"))

    assert tweede.status_code == 201 and len(tenant_ids()) == 2, f"{tweede.status_code}"
