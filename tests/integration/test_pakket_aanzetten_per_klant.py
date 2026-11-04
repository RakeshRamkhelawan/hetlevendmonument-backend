"""Pakket aanzetten per klant, dag 1: de beheerder zet aan, de uitvoerroute luistert (ADR-039, ADR-005).

Echte app-stack, echte Postgres, de echte rolzaaier en rolcontrole (zelfde opzet als
`test_packs_execute_route.py`). Besluit Rakesh 2026-10-09: "een beheerder zet het pakket aan, een
medewerker voert het uit". Na deze wijziging staat elk pakket voor elke klant UIT tot een beheerder het
aanzet: `POST /api/v1/agentic/packs/execute` geeft 403 `PACK_NOT_ENABLED` voor een pakket dat uit staat.

Wat gemeten wordt (alle via de echte routes):

(a) uitvoeren: uit = 403 (en geen enkele stap gestart), onbekend pakket blijft 404, aan = uitvoeren,
    weer uit = weer 403, klant A aanzetten laat klant B uit;
(b) aanzetten: `PUT /api/v1/packs/activations/{pack_id}` vraagt `packs:manage` en CSRF, onbekend pakket
    404, de klant komt uit de JWT (nooit uit de body), idempotent, een auditregel per wijziging;
(c) lijst: `GET /api/v1/packs/activations` (recht `packs:execute`) toont de hele catalogus met de stand
    van de EIGEN klant.

Wat NIET gemeten is: een draaiende applicatie met scherm (dag 2); een echte LLM-uitvoering (de stap is,
net als in de bestaande test, op de grens vervangen).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.rbac_service import RBACService
from tests.integration.test_packs_execute_route import (  # noqa: F401
    PACK,
    TENANT,
    URL,
    Opname,
    _body,
    _client,
    _gebruiker_met_rol,
    alleen_lezen,
    beheerder,
    beheerder_met_echte_csrf,
    medewerker,
    redacteur,
    standaardrollen,
    stappen,
)

ANDER_TENANT = 2
PILOTPAKKETTEN = ("mkb.zero_admin", "hr.reskilling_engine")
ACTIVATIES = "/api/v1/packs/activations"
EVENT = "pack_activation_changed"


def _put(pack_id: str = PACK) -> str:
    return f"{ACTIVATIES}/{pack_id}"


async def _zet_aan_in_database(
    sessie: AsyncSession, tenant_id: int, pack_id: str, *, aan: bool = True
) -> None:
    """Direct in de tabel, zodat de uitvoertests niet van de beheerroute afhangen."""
    await sessie.execute(
        text(
            "INSERT INTO tenant_pack_activations (tenant_id, pack_id, is_enabled) "
            "VALUES (:t, :p, :a) "
            "ON CONFLICT (tenant_id, pack_id) DO UPDATE SET is_enabled = :a"
        ),
        {"t": tenant_id, "p": pack_id, "a": aan},
    )
    await sessie.commit()


async def _aantal_rijen(sessie: AsyncSession, tenant_id: int, pack_id: str = PACK) -> int:
    return int(
        (
            await sessie.execute(
                text(
                    "SELECT count(*) FROM tenant_pack_activations "
                    "WHERE tenant_id = :t AND pack_id = :p"
                ),
                {"t": tenant_id, "p": pack_id},
            )
        ).scalar_one()
    )


async def _aantal_auditregels(sessie: AsyncSession) -> int:
    return int(
        (
            await sessie.execute(
                text("SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND event_type = :e"),
                {"t": TENANT, "e": EVENT},
            )
        ).scalar_one()
    )


@pytest_asyncio.fixture
async def medewerker_van_klant_b(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Een medewerker van de TWEEDE klant, met de standaardrol `user` van die klant."""
    await RBACService(standaardrollen).ensure_default_roles(ANDER_TENANT)
    email = "pack-medewerker-b@integration.test"
    rol_id = (
        await standaardrollen.execute(
            text("SELECT id FROM roles WHERE name = 'user' AND tenant_id = :t"),
            {"t": ANDER_TENANT},
        )
    ).scalar_one()
    gebruiker_id = (
        await standaardrollen.execute(
            text(
                "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                "VALUES (:e, 'x', :t, true, false) RETURNING id"
            ),
            {"e": email, "t": ANDER_TENANT},
        )
    ).scalar_one()
    await standaardrollen.execute(
        text("INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": gebruiker_id, "r": rol_id, "t": ANDER_TENANT},
    )
    await standaardrollen.commit()
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=int(gebruiker_id),
        email=email,
        rollen=["user"],
        csrf=False,
        tenant=ANDER_TENANT,
    ):
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
class TestUitvoerenMoetAanStaan:
    async def test_een_uitgezet_pakket_geeft_403_pack_not_enabled(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(URL, json=_body())

        assert antwoord.status_code == 403, antwoord.text
        detail = antwoord.json()["detail"]
        assert detail["code"] == "PACK_NOT_ENABLED"
        assert detail["message"] == (
            "Dit pakket staat niet aan voor uw bedrijf. Vraag uw beheerder om het aan te zetten."
        )

    async def test_een_uitgezet_pakket_start_geen_enkele_stap(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json=_body())

        assert stappen.aanroepen == []

    async def test_een_onbekend_pakket_blijft_404_ook_als_niets_aan_staat(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(URL, json=_body("bestaat.niet"))

        assert antwoord.status_code == 404, antwoord.text
        assert antwoord.json()["detail"]["code"] == "PACK_NOT_FOUND"

    async def test_een_aangezet_pakket_wordt_uitgevoerd(
        self, medewerker: AsyncClient, stappen: Opname, standaardrollen: AsyncSession
    ) -> None:
        await _zet_aan_in_database(standaardrollen, TENANT, PACK)

        antwoord = await medewerker.post(URL, json=_body())

        assert antwoord.status_code == 200, antwoord.text
        assert [a["agent_id"] for a in stappen.aanroepen] == [
            "receiptscanner",
            "vatcompliance",
            "dunning",
        ]

    async def test_een_weer_uitgezet_pakket_geeft_weer_403(
        self, medewerker: AsyncClient, stappen: Opname, standaardrollen: AsyncSession
    ) -> None:
        await _zet_aan_in_database(standaardrollen, TENANT, PACK, aan=False)

        antwoord = await medewerker.post(URL, json=_body())

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json()["detail"]["code"] == "PACK_NOT_ENABLED"

    async def test_aanzetten_voor_klant_a_laat_klant_b_uit(
        self,
        medewerker_van_klant_b: AsyncClient,
        stappen: Opname,
        standaardrollen: AsyncSession,
    ) -> None:
        await _zet_aan_in_database(standaardrollen, TENANT, PACK)

        antwoord = await medewerker_van_klant_b.post(URL, json=_body())

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json()["detail"]["code"] == "PACK_NOT_ENABLED"
        assert stappen.aanroepen == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanzetten:
    async def test_een_beheerder_zet_het_pakket_aan_en_een_medewerker_voert_uit(
        self, beheerder: AsyncClient, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        aanzetten = await beheerder.put(_put(), json={"is_enabled": True})
        uitvoeren = await medewerker.post(URL, json=_body())

        assert aanzetten.status_code == 200, aanzetten.text
        data = aanzetten.json()["data"]
        assert (data["pack_id"], data["is_enabled"]) == (PACK, True)
        assert uitvoeren.status_code == 200, uitvoeren.text

    async def test_een_beheerder_zet_het_pakket_weer_uit(
        self, beheerder: AsyncClient, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await beheerder.put(_put(), json={"is_enabled": True})
        uitzetten = await beheerder.put(_put(), json={"is_enabled": False})
        uitvoeren = await medewerker.post(URL, json=_body())

        assert uitzetten.status_code == 200, uitzetten.text
        assert uitzetten.json()["data"]["is_enabled"] is False
        assert uitvoeren.status_code == 403, uitvoeren.text

    async def test_een_medewerker_mag_niet_aanzetten(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await medewerker.put(_put(), json={"is_enabled": True})

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing permission: packs:manage", antwoord.text
        assert await _aantal_rijen(standaardrollen, TENANT) == 0

    async def test_een_redacteur_mag_niet_aanzetten(
        self, redacteur: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await redacteur.put(_put(), json={"is_enabled": True})

        assert antwoord.status_code == 403, antwoord.text
        assert await _aantal_rijen(standaardrollen, TENANT) == 0

    async def test_een_onbekend_pack_id_geeft_404(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await beheerder.put(_put("bestaat.niet"), json={"is_enabled": True})

        assert antwoord.status_code == 404, antwoord.text
        assert antwoord.json()["detail"]["code"] == "PACK_NOT_FOUND"
        assert await _aantal_rijen(standaardrollen, TENANT, "bestaat.niet") == 0

    async def test_aanzetten_vraagt_een_csrf_token(
        self, beheerder_met_echte_csrf: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await beheerder_met_echte_csrf.put(_put(), json={"is_enabled": True})

        assert antwoord.status_code == 403, antwoord.text
        assert "csrf" in antwoord.text.lower(), antwoord.text
        assert await _aantal_rijen(standaardrollen, TENANT) == 0

    async def test_de_klant_in_de_body_wordt_geweigerd_en_niet_gebruikt(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await beheerder.put(_put(), json={"is_enabled": True, "tenant_id": ANDER_TENANT})

        assert antwoord.status_code == 422, antwoord.text
        assert await _aantal_rijen(standaardrollen, ANDER_TENANT) == 0
        assert await _aantal_rijen(standaardrollen, TENANT) == 0

    async def test_twee_keer_aanzetten_geeft_een_rij(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        eerste = await beheerder.put(_put(), json={"is_enabled": True})
        tweede = await beheerder.put(_put(), json={"is_enabled": True})

        assert (eerste.status_code, tweede.status_code) == (200, 200)
        assert await _aantal_rijen(standaardrollen, TENANT) == 1

    async def test_de_rij_legt_vast_wie_en_wanneer(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        await beheerder.put(_put(), json={"is_enabled": True})

        rij = (
            await standaardrollen.execute(
                text(
                    "SELECT enabled_by_user_id, enabled_at, is_enabled "
                    "FROM tenant_pack_activations WHERE tenant_id = :t AND pack_id = :p"
                ),
                {"t": TENANT, "p": PACK},
            )
        ).one()
        assert rij.enabled_by_user_id == 1
        assert rij.enabled_at is not None and rij.enabled_at.tzinfo is not None
        assert rij.is_enabled is True

    async def test_er_komt_een_auditregel_per_wijziging(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        voor = await _aantal_auditregels(standaardrollen)

        await beheerder.put(_put(), json={"is_enabled": True})
        await beheerder.put(_put(), json={"is_enabled": False})

        assert await _aantal_auditregels(standaardrollen) - voor == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestLijst:
    async def test_de_lijst_toont_de_pilotpakketten_standaard_uit(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await medewerker.get(ACTIVATIES)

        assert antwoord.status_code == 200, antwoord.text
        per_pakket = {p["pack_id"]: p for p in antwoord.json()["data"]}
        for pack_id in PILOTPAKKETTEN:
            assert per_pakket[pack_id]["is_enabled"] is False, pack_id
        assert per_pakket[PACK]["name"] == "Zero-Admin Bookkeeping"

    async def test_de_lijst_toont_de_hele_catalogus(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        from src.core.als.enterprise.packs import DomainPackOrchestrator

        antwoord = await medewerker.get(ACTIVATIES)

        verwacht = set(DomainPackOrchestrator().catalog.packs)
        assert {p["pack_id"] for p in antwoord.json()["data"]} == verwacht

    async def test_de_lijst_toont_de_stand_na_aanzetten(
        self, beheerder: AsyncClient, medewerker: AsyncClient
    ) -> None:
        await beheerder.put(_put("mkb.zero_admin"), json={"is_enabled": True})

        antwoord = await medewerker.get(ACTIVATIES)

        per_pakket = {p["pack_id"]: p["is_enabled"] for p in antwoord.json()["data"]}
        assert per_pakket["mkb.zero_admin"] is True
        assert per_pakket["hr.reskilling_engine"] is False

    async def test_de_lijst_toont_niet_de_stand_van_een_andere_klant(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        await _zet_aan_in_database(standaardrollen, ANDER_TENANT, PACK)

        antwoord = await medewerker.get(ACTIVATIES)

        per_pakket = {p["pack_id"]: p["is_enabled"] for p in antwoord.json()["data"]}
        assert per_pakket[PACK] is False

    async def test_een_rol_zonder_het_recht_krijgt_403_op_de_lijst(
        self, alleen_lezen: AsyncClient
    ) -> None:
        antwoord = await alleen_lezen.get(ACTIVATIES)

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing permission: packs:execute", antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestRepositoryIsolatie:
    """De repository filtert op de klant: klant A ziet de stand van klant B nooit (ADR-005)."""

    async def test_klant_a_ziet_de_stand_van_klant_b_niet(
        self, standaardrollen: AsyncSession
    ) -> None:
        from src.core.repositories.tenant_pack_activations_repository import (
            TenantPackActivationsRepository,
        )

        await _zet_aan_in_database(standaardrollen, ANDER_TENANT, PACK)
        repo = TenantPackActivationsRepository(standaardrollen)

        assert await repo.is_enabled(TENANT, PACK) is False
        assert await repo.is_enabled(ANDER_TENANT, PACK) is True
        assert await repo.enabled_pack_ids(TENANT) == set()

    async def test_zetten_voor_klant_a_raakt_klant_b_niet(
        self, standaardrollen: AsyncSession
    ) -> None:
        from src.core.repositories.tenant_pack_activations_repository import (
            TenantPackActivationsRepository,
        )

        repo = TenantPackActivationsRepository(standaardrollen)
        await repo.set_enabled(TENANT, PACK, True, user_id=1)
        await standaardrollen.commit()

        assert await repo.is_enabled(TENANT, PACK) is True
        assert await repo.is_enabled(ANDER_TENANT, PACK) is False
