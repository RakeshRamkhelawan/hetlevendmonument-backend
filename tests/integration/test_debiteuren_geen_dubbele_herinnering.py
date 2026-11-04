"""Debiteuren: geen tweede herinnering of aanmaning van dezelfde soort voor dezelfde factuur, en een aanmaning pas na een
herinnering (brief 2026-10-24).

Door de regie in de code gelezen en NIET getest; deze module is het bewijs, eerst rood. Echte stack: de agent met een
scriptdubbel als taalmodel, de echte registry, de echte HITL-routes en echte Postgres (netwerkpoort 5455). Er wordt echt
gecommit en na elke test opgeruimd, zoals in `scenarios/test_scenario_5_betalingsherinnering.py` (daar staan de helpers).

Wat telt als "al klaargezet of verstuurd": een bericht van DEZE tenant voor dezelfde factuur en soort met status `klaar` of
`verzonden`. Een `mislukt` bericht blokkeert niet (dan mag het opnieuw). Een aanmaning vraagt een VERZONDEN herinnering.

**Mutatiebewijs (2026-10-24), een regel per element, kopie als terugweg; alle negen betrapt:**
- voorbereiden controleert niets -> 6 rood; versturen controleert niet opnieuw -> 1 rood (twee goedgekeurde tickets);
- geen volgorde-eis voor een aanmaning -> 3 rood; berichten van elke tenant tellen -> 2 rood;
- een mislukt bericht blokkeert ook -> 1 rood; een klaargezette herinnering telt voor de aanmaning -> 1 rood;
- tickets van elke tenant tellen -> 1 rood; ook besloten tickets blokkeren -> 1 rood; wachtende tickets tellen niet -> 1 rood.
Vooraf (zonder de fix) waren 7 van de 11 toenmalige tests rood en de vier tegenproeven groen.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401
from tests.integration.scenarios.test_scenario_5_betalingsherinnering import (
    AANVRAGER,
    TENANT,
    _berichten,
    _beslis,
    _sql,
    _ticket_payload,
    debiteur,  # noqa: F401
)

_ANDERE_TENANT_SLUG = "dubbel-andere-tenant"


async def _agent_run(receivable_id: int, kind: str) -> str:
    """Een run van de debiteurenagent die de brief wil laten klaarzetten. Geeft de foutregels als een tekst terug."""
    from src.core.als.agents.skills.dunning import DunningSkill

    agent = DunningSkill(tenant_id=TENANT)
    model = AsyncMock()
    model.generate = AsyncMock(
        return_value=(
            f'TOOL_CALL: send_payment_reminder {{"receivable_id": {receivable_id}, "kind": "{kind}"}}'
        )
    )

    async def _model() -> Any:
        return model

    agent._get_llm_service = _model  # type: ignore[method-assign]
    resultaat = await agent.execute_with_manifest_prompt(
        {"task": f"Stuur een {kind}"}, initiated_by_user_id=AANVRAGER
    )
    return " ".join(str(f.get("error")) for f in resultaat.result_data.get("errors", []))


async def _tickets(receivable_id: int, kind: str) -> int:
    rij = (
        await _sql(
            "SELECT count(*) FROM hitl_tickets WHERE tenant_id = :t AND tool_name = 'send_payment_reminder' "
            "AND payload->>'receivable_id' = :r AND payload->>'kind' = :k",
            t=TENANT,
            r=str(receivable_id),
            k=kind,
        )
    ).scalar_one()
    return int(rij)


async def _zet_bericht(receivable_id: int, kind: str, status: str, tenant_id: int = TENANT) -> None:
    await _sql(
        "INSERT INTO outgoing_messages (tenant_id, receivable_id, channel, kind, recipient, subject, body, "
        "status, pogingen) VALUES (:t, :r, 'email', :k, 'a@example.com', 's', 'b', :s, 0)",
        t=tenant_id,
        r=receivable_id,
        k=kind,
        s=status,
    )


@pytest_asyncio.fixture
async def debiteur_van_een_andere_tenant() -> AsyncGenerator[tuple[int, int], None]:
    from src.core.database.database import db_manager
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    tenant_id = (
        await _sql(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Dubbel B', :s, true, 1, 1, 1) RETURNING id",
            s=_ANDERE_TENANT_SLUG,
        )
    ).scalar_one()
    async with db_manager.get_session() as session:
        rij = await ReceivableRepository(session).add(
            tenant_id,
            NewReceivable(
                customer_name="Andere Klant",
                customer_email="andere@klant.example",
                invoice_number="B-1",
                amount=Decimal("10.00"),
                currency="EUR",
                due_date=date(2026, 9, 1),
            ),
        )
        await session.commit()
        rid = rij.id
    yield tenant_id, rid
    await _sql(
        "DELETE FROM outgoing_messages WHERE tenant_id = :t OR receivable_id = :r",
        t=tenant_id,
        r=rid,
    )
    await _sql("DELETE FROM receivables WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM tenants WHERE id = :t", t=tenant_id)


async def _voorbeeld(tenant_id: int, receivable_id: int, kind: str) -> dict[str, object]:
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    return await ReceivablesToolRegistry().preview_payment_reminder(tenant_id, receivable_id, kind)


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeenTweedeVoorstelVoorDezelfdeSoort:
    async def test_een_tweede_run_voor_dezelfde_factuur_en_soort_maakt_geen_tweede_ticket(
        self, debiteur: int
    ) -> None:
        await _agent_run(debiteur, "herinnering")

        melding = await _agent_run(debiteur, "herinnering")

        assert await _tickets(debiteur, "herinnering") == 1
        assert "al een herinnering" in melding

    async def test_een_herinnering_en_een_aanmaning_zijn_verschillende_soorten(
        self, debiteur: int
    ) -> None:
        """Tegenproef: 'weiger alles na een eerste voorstel' is een geldige oplossing zonder deze test."""
        await _zet_bericht(debiteur, "herinnering", "verzonden")

        await _agent_run(debiteur, "aanmaning")

        assert await _tickets(debiteur, "aanmaning") == 1

    async def test_een_klaargezet_bericht_blokkeert_een_nieuw_voorstel_van_dezelfde_soort(
        self, debiteur: int
    ) -> None:
        await _zet_bericht(debiteur, "herinnering", "klaar")

        melding = await _agent_run(debiteur, "herinnering")

        assert await _tickets(debiteur, "herinnering") == 0
        assert "al een herinnering" in melding

    async def test_een_verzonden_bericht_blokkeert_een_nieuw_voorstel_van_dezelfde_soort(
        self, debiteur: int
    ) -> None:
        await _zet_bericht(debiteur, "herinnering", "verzonden")

        melding = await _agent_run(debiteur, "herinnering")

        assert await _tickets(debiteur, "herinnering") == 0
        assert "al een herinnering" in melding

    async def test_een_mislukt_bericht_blokkeert_niet(self, debiteur: int) -> None:
        await _zet_bericht(debiteur, "herinnering", "mislukt")

        await _agent_run(debiteur, "herinnering")

        assert await _tickets(debiteur, "herinnering") == 1


async def _zet_ticket(ref: str, tenant_id: int, status: str, receivable_id: int, kind: str) -> None:
    await _sql(
        "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, risk_level, expires_at) "
        "VALUES (:r, :t, CAST(:s AS VARCHAR), 'send_payment_reminder', CAST(:p AS JSONB), 'HIGH', "
        "clock_timestamp() + interval '1 day')",
        r=ref,
        t=tenant_id,
        s=status,
        p=json.dumps({"receivable_id": receivable_id, "kind": kind}),
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestWatEenVoorstelNietBlokkeert:
    async def test_een_besloten_voorstel_van_dezelfde_soort_blokkeert_niet(
        self, debiteur: int
    ) -> None:
        await _zet_ticket("hitl_besloten_test", TENANT, "rejected", debiteur, "herinnering")

        await _agent_run(debiteur, "herinnering")

        assert await _tickets(debiteur, "herinnering") == 2  # het besloten voorstel en het nieuwe

    async def test_een_wachtend_voorstel_van_een_andere_tenant_blokkeert_niet(
        self, debiteur: int, debiteur_van_een_andere_tenant: tuple[int, int]
    ) -> None:
        tenant_b, _ = debiteur_van_een_andere_tenant
        await _zet_ticket("hitl_andere_tenant_test", tenant_b, "pending", debiteur, "herinnering")
        try:
            await _agent_run(debiteur, "herinnering")

            assert await _tickets(debiteur, "herinnering") == 1  # alleen dat van tenant A
        finally:
            await _sql("DELETE FROM hitl_tickets WHERE ticket_ref = 'hitl_andere_tenant_test'")


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenAanmaningKomtNaEenHerinnering:
    async def test_een_aanmaning_zonder_eerdere_herinnering_wordt_geweigerd_met_reden(
        self, debiteur: int
    ) -> None:
        melding = await _agent_run(debiteur, "aanmaning")

        assert await _tickets(debiteur, "aanmaning") == 0
        assert "pas na een verstuurde herinnering" in melding

    async def test_een_klaargezette_maar_nog_niet_verstuurde_herinnering_telt_niet(
        self, debiteur: int
    ) -> None:
        await _zet_bericht(debiteur, "herinnering", "klaar")

        melding = await _agent_run(debiteur, "aanmaning")

        assert await _tickets(debiteur, "aanmaning") == 0
        assert "pas na een verstuurde herinnering" in melding

    @pytest.mark.parametrize("status", ["herinnerd", "geescaleerd"])
    async def test_een_dossier_dat_al_herinnerd_of_geescaleerd_is_mag_een_aanmaning(
        self, debiteur: int, status: str
    ) -> None:
        """De verzendlus zet die status pas na een verstuurde brief: dat telt als bewijs van een herinnering."""
        await _sql("UPDATE receivables SET status = :s WHERE id = :r", s=status, r=debiteur)

        await _agent_run(debiteur, "aanmaning")

        assert await _tickets(debiteur, "aanmaning") == 1

    async def test_na_een_verstuurde_herinnering_mag_de_aanmaning(self, debiteur: int) -> None:
        await _zet_bericht(debiteur, "herinnering", "verzonden")

        await _agent_run(debiteur, "aanmaning")

        assert await _tickets(debiteur, "aanmaning") == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestTweeGoedkeuringenGevenEenBrief:
    async def test_twee_goedgekeurde_tickets_voor_dezelfde_factuur_en_soort_geven_een_brief(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _agent_run(debiteur, "herinnering")
        ref1 = (
            await _sql(
                "SELECT ticket_ref FROM hitl_tickets WHERE tenant_id = :t "
                "AND tool_name = 'send_payment_reminder'",
                t=TENANT,
            )
        ).scalar_one()
        # Een tweede ticket dat de voorbereidingscontrole al is gepasseerd (twee tegelijk geopend): het
        # versturen moet het dan tegenhouden.
        payload = await _ticket_payload(ref1)
        await _sql(
            "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, risk_level, expires_at) "
            "VALUES ('hitl_tweede_test', :t, 'pending', 'send_payment_reminder', CAST(:p AS JSONB), 'HIGH', "
            "clock_timestamp() + interval '1 day')",
            t=TENANT,
            p=json.dumps(payload),
        )

        eerste_besluit = await _beslis(integration_app, AANVRAGER, "approve", {"ticket_ref": ref1})
        tweede_besluit = await _beslis(
            integration_app, AANVRAGER, "approve", {"ticket_ref": "hitl_tweede_test"}
        )

        assert eerste_besluit.status_code == 200, eerste_besluit.text
        assert len(await _berichten()) == 1
        assert tweede_besluit.json().get("executed") is not True, tweede_besluit.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeControleTeltAlleenDeEigenTenant:
    async def test_een_bericht_van_tenant_a_blokkeert_niets_bij_tenant_b(
        self, debiteur: int, debiteur_van_een_andere_tenant: tuple[int, int]
    ) -> None:
        tenant_b, factuur_b = debiteur_van_een_andere_tenant
        await _zet_bericht(debiteur, "herinnering", "verzonden")
        # Een bericht van tenant A dat toevallig naar het id van B's factuur wijst telt niet voor B.
        await _zet_bericht(factuur_b, "herinnering", "verzonden", tenant_id=TENANT)

        antwoord = await _voorbeeld(tenant_b, factuur_b, "herinnering")

        assert antwoord["success"] is True, antwoord

    async def test_een_verstuurde_herinnering_van_tenant_a_maakt_een_aanmaning_bij_b_niet_mogelijk(
        self, debiteur: int, debiteur_van_een_andere_tenant: tuple[int, int]
    ) -> None:
        tenant_b, factuur_b = debiteur_van_een_andere_tenant
        await _zet_bericht(factuur_b, "herinnering", "verzonden", tenant_id=TENANT)

        antwoord = await _voorbeeld(tenant_b, factuur_b, "aanmaning")

        assert antwoord["success"] is False
        assert "pas na een verstuurde herinnering" in str(antwoord["error"])
