"""AI-verordening voor de pilot: bij elk opleidingsvoorstel een uitleg, ook voor de medewerker zelf.

Brief `docs/agent-briefs/generated/2026-10-12-sprint-dag-ai-verordening-voor-de-pilot.md`,
onderzoek `docs/onderzoek-ai-verordening-hr-pakket-hoog-risico.md` (art. 13 en art. 86).

Echte app-stack en echte Postgres (zelfde opzet als `test_hr_pilot_dag2_opleidingsvoorstel.py`).

Wat dit vaststelt:

1. Elk voorstel in de HR-lijst draagt een uitleg: de vaardigheid, het vereiste niveau, het gemeten
   niveau, de beoordelingsdatum, dat het met vaste regels is gemaakt (geen taalmodel) en dat een mens
   besluit.
2. De medewerker leest via een EIGEN route de uitleg van ZIJN voorstellen; nooit die van een collega
   (404) en nooit die van een andere tenant.
3. Is de beoordeling na het voorstel gewijzigd, dan zegt de uitleg dat eerlijk: het gemeten niveau is
   dan het huidige, en de vlag `reassessed_since_proposal` staat aan.
4. De uitleg voor de medewerker bevat geen e-mailadres van een ander (ook niet van de goedkeurder).
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_hr_pilot_dag2_opleidingsvoorstel import (  # noqa: F401
    ANDERE_TENANT,
    HOOG,
    LAAG,
    PROPOSALS,
    SKILL,
    _client,
    _maak,
    _voorstel_id,
    goedkeurder,
    hr_medewerker,
    sessie,
    wereld,
)

MIJN = "/api/v1/hr/my-training-proposals"


@pytest_asyncio.fixture
async def laag(integration_app: Any, sessie: AsyncSession, wereld: dict[str, int]) -> Any:  # noqa: F811
    """De medewerker die onder de eis zit (niveau 2 van 3), ingelogd als zichzelf."""
    async for client in _client(integration_app, sessie, user_id=wereld["laag"], email=LAAG):
        yield client


@pytest_asyncio.fixture
async def hoog(integration_app: Any, sessie: AsyncSession, wereld: dict[str, int]) -> Any:  # noqa: F811
    """Een collega die NIET onder de eis zit en dus geen voorstel heeft."""
    async for client in _client(integration_app, sessie, user_id=wereld["hoog"], email=HOOG):
        yield client


async def _vreemd_voorstel(sessie: AsyncSession) -> int:
    """Een voorstel van tenant B, rechtstreeks in de database gezet."""
    gebruiker = (
        await sessie.execute(
            text(
                "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                "VALUES ('vreemd-aiv@integration.test', 'x', :t, true, false) RETURNING id"
            ),
            {"t": ANDERE_TENANT},
        )
    ).scalar_one()
    skill = (
        await sessie.execute(
            text("INSERT INTO skills (tenant_id, name) VALUES (:t, 'Vreemd-aiv') RETURNING id"),
            {"t": ANDERE_TENANT},
        )
    ).scalar_one()
    training = (
        await sessie.execute(
            text(
                "INSERT INTO trainings (tenant_id, name, skill_id) "
                "VALUES (:t, 'Vreemde-training-aiv', :s) RETURNING id"
            ),
            {"t": ANDERE_TENANT, "s": skill},
        )
    ).scalar_one()
    voorstel = (
        await sessie.execute(
            text(
                "INSERT INTO training_proposals "
                "(tenant_id, user_id, skill_id, training_id, reason, status) "
                "VALUES (:t, :u, :s, :tr, 'test', 'voorgesteld') RETURNING id"
            ),
            {"t": ANDERE_TENANT, "u": gebruiker, "s": skill, "tr": training},
        )
    ).scalar_one()
    await sessie.commit()
    return int(voorstel)


@pytest.mark.integration
@pytest.mark.asyncio
class TestUitlegVoorHr:
    async def _eerste(self, hr_medewerker: AsyncClient) -> dict[str, Any]:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        lijst = await hr_medewerker.get(PROPOSALS)
        assert lijst.status_code == 200, lijst.text
        return dict(lijst.json()["data"][0])

    async def test_elk_voorstel_in_de_lijst_heeft_een_uitleg(
        self, hr_medewerker: AsyncClient
    ) -> None:
        voorstel = await self._eerste(hr_medewerker)

        assert isinstance(voorstel.get("explanation"), dict)

    async def test_de_uitleg_noemt_vaardigheid_vereist_en_gemeten_niveau(
        self, hr_medewerker: AsyncClient
    ) -> None:
        uitleg = (await self._eerste(hr_medewerker))["explanation"]

        assert (uitleg["skill"], uitleg["required_level"], uitleg["measured_level"]) == (
            SKILL,
            3,
            2,
        )

    async def test_de_uitleg_noemt_de_beoordelingsdatum(self, hr_medewerker: AsyncClient) -> None:
        uitleg = (await self._eerste(hr_medewerker))["explanation"]

        assert isinstance(uitleg["assessed_at"], str) and len(uitleg["assessed_at"]) >= 10

    async def test_de_uitleg_zegt_dat_het_met_vaste_regels_is_gemaakt_en_een_mens_besluit(
        self, hr_medewerker: AsyncClient
    ) -> None:
        uitleg = (await self._eerste(hr_medewerker))["explanation"]

        assert (uitleg["rule_based"], uitleg["human_decides"]) == (True, True)

    async def test_de_uitleg_is_leesbare_tekst_met_de_niveaus_erin(
        self, hr_medewerker: AsyncClient
    ) -> None:
        tekst = (await self._eerste(hr_medewerker))["explanation"]["text"]

        assert "2" in tekst and "3" in tekst and SKILL in tekst

    async def test_de_tekst_zegt_in_gewone_taal_dat_een_mens_besluit(
        self, hr_medewerker: AsyncClient
    ) -> None:
        tekst = (await self._eerste(hr_medewerker))["explanation"]["text"].lower()

        assert "een mens" in tekst and "besluit" in tekst

    async def test_de_tekst_zegt_wie_de_opleiding_koos(self, hr_medewerker: AsyncClient) -> None:
        """Art. 86: 'waarom deze opleiding'. Personeelszaken kiest hem, het systeem kiest niet."""
        tekst = (await self._eerste(hr_medewerker))["explanation"]["text"].lower()

        assert "gekozen door een medewerker van personeelszaken" in tekst

    async def test_een_enkele_uitleg_is_ook_op_te_vragen(self, hr_medewerker: AsyncClient) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)

        antwoord = await hr_medewerker.get(f"{PROPOSALS}/{voorstel_id}/explanation")

        assert antwoord.status_code == 200 and antwoord.json()["data"]["skill"] == SKILL

    async def test_een_voorstel_van_een_andere_tenant_heeft_voor_hr_geen_uitleg(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        vreemd = await _vreemd_voorstel(sessie)

        antwoord = await hr_medewerker.get(f"{PROPOSALS}/{vreemd}/explanation")

        assert antwoord.status_code == 404

    async def test_na_een_nieuwe_beoordeling_zegt_de_uitleg_dat_eerlijk(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        await sessie.execute(
            text(
                "UPDATE employee_skills SET level = 3, assessed_at = now() + interval '1 hour' "
                "WHERE user_id = :u"
            ),
            {"u": wereld["laag"]},
        )
        await sessie.commit()

        uitleg = (await hr_medewerker.get(PROPOSALS)).json()["data"][0]["explanation"]

        assert (uitleg["measured_level"], uitleg["reassessed_since_proposal"]) == (3, True)

    async def test_de_tekst_zegt_niet_dat_het_niveau_onder_de_eis_ligt_als_het_de_eis_nu_haalt(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession, wereld: dict[str, int]
    ) -> None:
        """Gate 2 (2026-10-14): na een nieuwe beoordeling tot de eis zei de uitleg nog 'onder de eis'."""
        await hr_medewerker.post(PROPOSALS, json=_maak())
        await sessie.execute(
            text(
                "UPDATE employee_skills SET level = 3, assessed_at = now() + interval '1 hour' "
                "WHERE user_id = :u"
            ),
            {"u": wereld["laag"]},
        )
        await sessie.commit()

        tekst = (await hr_medewerker.get(PROPOSALS)).json()["data"][0]["explanation"]["text"]

        assert "onder het gevraagde niveau" not in tekst and "haalt de eis" in tekst

    async def test_de_tekst_beweert_niet_dat_het_niveau_lager_was_als_alleen_de_eis_is_verlaagd(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        """Herreview 2026-10-14: zonder nieuwe beoordeling is 'het niveau was lager' niet bewezen."""
        await hr_medewerker.post(PROPOSALS, json=_maak())
        await sessie.execute(
            text(
                "UPDATE role_required_skills SET required_level = 2 "
                "WHERE role_id IN (SELECT id FROM roles WHERE name = 'Planner-d2')"
            )
        )
        await sessie.commit()

        uitleg = (await hr_medewerker.get(PROPOSALS)).json()["data"][0]["explanation"]

        assert uitleg["reassessed_since_proposal"] is False
        assert "haalt de eis" in uitleg["text"]
        assert "toen het niveau lager was" not in uitleg["text"]

    async def test_de_tekst_zegt_wel_onder_de_eis_zolang_het_niveau_er_nog_onder_ligt(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())

        tekst = (await hr_medewerker.get(PROPOSALS)).json()["data"][0]["explanation"]["text"]

        assert "onder het gevraagde niveau 3" in tekst


@pytest.mark.integration
@pytest.mark.asyncio
class TestUitlegVoorDeMedewerker:
    async def test_de_medewerker_ziet_zijn_eigen_voorstel_met_uitleg(
        self, hr_medewerker: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())

        antwoord = await laag.get(MIJN)

        assert antwoord.status_code == 200, antwoord.text
        assert [v["explanation"]["skill"] for v in antwoord.json()["data"]] == [SKILL]

    async def test_de_eigen_lijst_bevat_geen_emailadres_van_een_ander(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel_id}/approve")

        antwoord = await laag.get(MIJN)

        assert antwoord.status_code == 200
        assert "@" not in antwoord.text

    async def test_een_collega_zonder_voorstel_ziet_een_lege_lijst(
        self, hr_medewerker: AsyncClient, hoog: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())

        antwoord = await hoog.get(MIJN)

        assert antwoord.status_code == 200 and antwoord.json()["data"] == []

    async def test_de_medewerker_leest_de_uitleg_van_zijn_eigen_voorstel(
        self, hr_medewerker: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = (await laag.get(MIJN)).json()["data"][0]["id"]

        antwoord = await laag.get(f"{MIJN}/{voorstel_id}/explanation")

        assert antwoord.status_code == 200 and antwoord.json()["data"]["required_level"] == 3

    async def test_de_uitleg_van_een_collega_is_niet_op_te_vragen(
        self, hr_medewerker: AsyncClient, hoog: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)

        antwoord = await hoog.get(f"{MIJN}/{voorstel_id}/explanation")

        assert antwoord.status_code == 404

    async def test_ook_hr_krijgt_via_de_eigen_route_alleen_eigen_voorstellen(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)

        antwoord = await hr_medewerker.get(f"{MIJN}/{voorstel_id}/explanation")

        assert antwoord.status_code == 404

    async def test_een_voorstel_van_een_andere_tenant_is_niet_op_te_vragen(
        self, laag: AsyncClient, sessie: AsyncSession
    ) -> None:
        vreemd = await _vreemd_voorstel(sessie)

        antwoord = await laag.get(f"{MIJN}/{vreemd}/explanation")

        assert antwoord.status_code == 404

    async def test_de_eigen_lijst_toont_geen_voorstel_van_een_andere_tenant(
        self, laag: AsyncClient, sessie: AsyncSession
    ) -> None:
        await _vreemd_voorstel(sessie)

        antwoord = await laag.get(MIJN)

        assert antwoord.json()["data"] == []

    async def test_een_tenant_in_de_query_wordt_genegeerd(
        self, laag: AsyncClient, sessie: AsyncSession
    ) -> None:
        vreemd = await _vreemd_voorstel(sessie)

        antwoord = await laag.get(
            f"{MIJN}/{vreemd}/explanation", params={"tenant_id": ANDERE_TENANT}
        )

        assert antwoord.status_code == 404

    async def test_de_uitleg_voor_de_medewerker_bevat_geen_emailadres_van_de_goedkeurder(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel_id}/approve")

        antwoord = await laag.get(f"{MIJN}/{voorstel_id}/explanation")

        assert antwoord.status_code == 200
        assert "@" not in antwoord.text

    async def test_na_het_besluit_zegt_de_tekst_is_voorgesteld_en_niet_wordt_voorgesteld(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel_id}/approve")

        tekst = (await laag.get(f"{MIJN}/{voorstel_id}/explanation")).json()["data"]["text"]

        assert "is voorgesteld" in tekst and "wordt voorgesteld" not in tekst

    async def test_na_het_besluit_staat_de_status_in_de_uitleg(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, laag: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel_id = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel_id}/approve")

        uitleg = (await laag.get(f"{MIJN}/{voorstel_id}/explanation")).json()["data"]

        assert (uitleg["status"], uitleg["decided_at"] is not None) == ("goedgekeurd", True)
