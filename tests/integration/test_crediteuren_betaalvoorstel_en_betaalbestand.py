"""Crediteuren dag 3: de agent stelt de betaling voor, een mens keurt goed, er komt een SEPA-betaalbestand (Keten F).

Brief `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag3-betaalvoorstel-en-betaalbestand.md` (op develop, commit
facba464). De zes rode tests uit de brief:

1. de agent maakt een betaalvoorstel-ticket met de juiste facturen en het waarom;
2. een factuur boven de drempel vraagt een tweede, andere goedkeurder; dezelfde persoon wordt geweigerd;
3. na goedkeuring ontstaat een pain.001-bestand met de juiste bedragen en IBAN's (de toets tegen het XSD staat in
   `test_pain001_valideert_tegen_xsd.py` en wacht op het schemabestand);
4. een factuur kan niet in een tweede betaalbestand komen;
5. afwijzen zonder reden wordt geweigerd; met reden blijft de factuur onbetaald;
6. tenant B ziet het voorstel en het bestand van tenant A niet.

Echt zijn Postgres op netwerkpoort 5455 (eigen database `crd_agent`), de Council, de HITL-vloer, het ticket in `hitl_tickets`, de HITL-routes,
de broker met zijn verzilvering, de registry en de auditketen. Vervangen zijn `get_current_user` en de CSRF-controle.

Wat NIET gemeten wordt: een bank die het bestand inleest en een draaiend scherm.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio

from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401
from tests.integration.test_crediteurenagent_verwerkt_factuur import _hitl, _post, _sql

TENANT = 1
ANDERE_TENANT = 2
STARTER = 1
ANDERE_GOEDKEURDER = 101
EIGEN_IBAN = "NL91ABNA0417164300"
IBAN_A = "NL02ABNA0123456789"
IBAN_B = "DE89370400440532013000"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"}


def _vandaag() -> date:
    return datetime.now(timezone.utc).date()


@pytest_asyncio.fixture(autouse=True)
async def _opruimen(goedkeurder_gebruikers: None) -> AsyncGenerator[None, None]:
    yield
    await _sql("DELETE FROM payables WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM suppliers WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM hitl_tickets WHERE tenant_id = :t", t=TENANT)


def _json(waarde: object) -> str:
    import json

    return json.dumps(waarde if waarde is not None else {})


@pytest_asyncio.fixture
async def drempel_origineel() -> AsyncGenerator[None, None]:
    """Zet de instelling van tenant 1 na afloop terug zoals hij was."""
    rij = (await _sql("SELECT settings FROM tenants WHERE id = :t", t=TENANT)).one()
    yield
    await _sql(
        "UPDATE tenants SET settings = CAST(:s AS json) WHERE id = :t", t=TENANT, s=_json(rij[0])
    )


async def _zet_drempel(cents: int) -> None:
    rij = (await _sql("SELECT settings FROM tenants WHERE id = :t", t=TENANT)).one()
    instellingen = dict(rij[0] or {})
    instellingen["crediteur_betaal_drempel_cents"] = cents
    await _sql(
        "UPDATE tenants SET settings = CAST(:s AS json) WHERE id = :t",
        t=TENANT,
        s=_json(instellingen),
    )


async def _leverancier(naam: str, iban: str | None, tenant: int = TENANT) -> int:
    from src.core.database.database import db_manager
    from src.core.repositories.payable_repository import NewSupplier, SupplierRepository

    async with db_manager.get_session() as session:
        rij = await SupplierRepository(session).add(tenant, NewSupplier(name=naam, iban=iban))
        await session.commit()
        return int(rij.id)


async def _factuur(
    leverancier: int,
    nummer: str,
    cents: int = 100000,
    over_dagen: int = 3,
    status: str = "ontvangen",
    tenant: int = TENANT,
) -> int:
    from src.core.database.database import db_manager
    from src.core.repositories.payable_repository import NewPayable, PayableRepository

    vervalt = _vandaag() + timedelta(days=over_dagen)
    async with db_manager.get_session() as session:
        rij = await PayableRepository(session).add(
            tenant,
            NewPayable(
                supplier_id=leverancier,
                invoice_number=nummer,
                amount_cents=cents,
                invoice_date=vervalt - timedelta(days=30),
                due_date=vervalt,
            ),
            created_by=None,
        )
        await session.commit()
        payable_id = int(rij.id)
    if status != "ontvangen":
        await _sql("UPDATE payables SET status = :s WHERE id = :i", s=status, i=payable_id)
    return payable_id


async def _stel_voor(door: int | None = STARTER, tenant: int = TENANT) -> dict[str, Any]:
    from src.core.als.agents.loader import EnterpriseCatalogLoader

    agent = EnterpriseCatalogLoader().load_all().get_agent_instance("crediteuren", tenant)
    return dict(await agent.stel_betaling_voor(initiated_by_user_id=door))


async def _statussen() -> dict[str, str]:
    rijen = await _sql(
        "SELECT invoice_number, status FROM payables WHERE tenant_id = :t ORDER BY id", t=TENANT
    )
    return {r[0]: r[1] for r in rijen.all()}


async def _ticket_payload(ref: str) -> dict[str, Any]:
    return dict(
        (await _sql("SELECT payload FROM hitl_tickets WHERE ticket_ref = :r", r=ref)).one()[0]
    )


async def _tickets() -> list[str]:
    rijen = await _sql(
        "SELECT ticket_ref FROM hitl_tickets WHERE tenant_id = :t ORDER BY id", t=TENANT
    )
    return [r[0] for r in rijen.all()]


async def _goedkeuren(app: Any, ref: str, door: int) -> Any:
    return await _post(app, "/api/v1/tools/hitl/approve", {"ticket_ref": ref}, user_id=door)


def _bestand_body(**over: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "debiteur_naam": "Mijn Bedrijf BV",
        "debiteur_iban": EIGEN_IBAN,
        "uitvoerdatum": (_vandaag() + timedelta(days=1)).isoformat(),
    }
    body.update(over)
    return body


async def _haal_bestand(app: Any, door: int = STARTER, **over: object) -> Any:
    return await _post(app, "/api/v1/payables/betaalbestand", _bestand_body(**over), user_id=door)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeAgentStelltVoor:
    async def test_the_agent_makes_one_ticket_with_the_right_invoices_and_the_reason(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)
        await _factuur(a, "INK-1", cents=120000, over_dagen=3)
        await _factuur(b, "INK-2", cents=45050, over_dagen=-2)

        uitkomst = await _stel_voor()

        assert uitkomst["uitkomst"] == "ticket", uitkomst
        assert (uitkomst["aantal"], uitkomst["totaal_cents"]) == (2, 165050)
        payload = await _ticket_payload(uitkomst["ticket_ref"])
        assert [(r["invoice_number"], r["amount_cents"]) for r in payload["regels"]] == [
            ("INK-2", 45050),
            ("INK-1", 120000),
        ]
        assert [r["waarom"] for r in payload["regels"]] == [
            "2 dagen te laat",
            "vervalt over 3 dagen",
        ]
        assert "stelt voor 2 facturen te betalen" in payload["waarom"]

    async def test_the_ticket_shows_masked_ibans_never_the_full_number(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")

        payload = await _ticket_payload((await _stel_voor())["ticket_ref"])

        assert payload["regels"][0]["iban"] == "NL02ABNA******6789"
        assert IBAN_A not in str(payload)

    async def test_an_invoice_that_is_far_in_the_future_is_not_proposed(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-LATER", over_dagen=30)

        uitkomst = await _stel_voor()

        assert (uitkomst["uitkomst"], await _tickets()) == ("niets_te_betalen", [])

    async def test_an_invoice_of_a_supplier_without_iban_is_skipped_with_a_reason(self) -> None:
        zonder = await _leverancier("Zonder IBAN BV", None)
        await _factuur(zonder, "INK-X")

        uitkomst = await _stel_voor()

        assert uitkomst["uitkomst"] == "niets_te_betalen"
        assert uitkomst["overgeslagen"] == [
            {"invoice_number": "INK-X", "reden": "de leverancier heeft geen geldig SEPA-IBAN"}
        ]

    @pytest.mark.parametrize("status", ["goedgekeurd", "in_betaalbestand", "betaald", "afgewezen"])
    async def test_an_invoice_that_is_further_along_is_never_proposed_again(
        self, status: str
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", status=status)

        assert (await _stel_voor())["uitkomst"] == "niets_te_betalen"

    async def test_a_checked_invoice_is_proposed_too(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", status="gecontroleerd")

        assert (await _stel_voor())["uitkomst"] == "ticket"

    async def test_an_invoice_in_an_open_proposal_is_not_proposed_a_second_time(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        await _stel_voor()

        tweede = await _stel_voor()

        assert (tweede["uitkomst"], len(await _tickets())) == ("niets_te_betalen", 1)

    async def test_without_a_responsible_person_nothing_happens(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")

        uitkomst = await _stel_voor(door=None)

        assert (uitkomst["uitkomst"], await _tickets()) == ("geweigerd", [])

    async def test_proposing_pays_and_approves_nothing(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")

        await _stel_voor()

        assert await _statussen() == {"INK-1": "ontvangen"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestVierOgenBovenDeDrempel:
    async def test_the_default_threshold_is_2500_euro_per_invoice(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=250001)

        payload = await _ticket_payload((await _stel_voor())["ticket_ref"])

        assert (payload["drempel_cents"], payload["vier_ogen_vereist"]) == (250000, True)

    async def test_an_amount_exactly_on_the_threshold_does_not_need_four_eyes(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=250000)

        payload = await _ticket_payload((await _stel_voor())["ticket_ref"])

        assert payload["vier_ogen_vereist"] is False

    async def test_a_total_above_the_threshold_needs_four_eyes_even_when_every_invoice_is_below_it(
        self,
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=200000)
        await _factuur(a, "INK-2", cents=200000)

        payload = await _ticket_payload((await _stel_voor())["ticket_ref"])

        assert (payload["totaal_cents"], payload["vier_ogen_vereist"]) == (400000, True)

    async def test_the_starter_cannot_approve_a_run_with_an_invoice_above_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-GROOT", cents=300000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.status_code == 403, antwoord.text
        assert await _statussen() == {"INK-GROOT": "ontvangen"}

    async def test_another_person_can_approve_a_run_above_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-GROOT", cents=300000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)

        assert antwoord.json()["executed"] is True, antwoord.json()
        assert await _statussen() == {"INK-GROOT": "goedgekeurd"}

    async def test_the_starter_may_approve_a_run_below_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-KLEIN", cents=100000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is True, antwoord.json()

    async def test_a_lower_threshold_set_by_the_tenant_applies(
        self, integration_app: Any, drempel_origineel: None
    ) -> None:
        await _zet_drempel(50000)
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=60000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.status_code == 403, antwoord.text

    async def test_an_unreadable_threshold_falls_back_to_the_strictest_rule(
        self, integration_app: Any, drempel_origineel: None
    ) -> None:
        await _zet_drempel(-5)
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=100)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGoedkeurenEnAfwijzen:
    async def test_approving_moves_every_invoice_of_the_run_to_approved(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)
        await _factuur(a, "INK-1")
        await _factuur(b, "INK-2")
        ref = (await _stel_voor())["ticket_ref"]

        await _goedkeuren(integration_app, ref, STARTER)

        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "goedgekeurd"}

    async def test_rejecting_without_a_reason_is_refused(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _hitl(integration_app, "reject", {"ticket_ref": ref, "reason": ""})

        assert antwoord.status_code == 422
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_rejecting_with_a_reason_leaves_the_invoices_unpaid(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _hitl(
            integration_app,
            "reject",
            {"ticket_ref": ref, "reason": "nog geen akkoord van de eigenaar"},
        )

        assert antwoord.status_code == 200, antwoord.text
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_after_a_rejection_the_invoices_can_be_proposed_again(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _hitl(
            integration_app,
            "reject",
            {"ticket_ref": ref, "reason": "nog geen akkoord van de eigenaar"},
        )

        assert (await _stel_voor())["uitkomst"] == "ticket"

    async def test_an_invoice_that_changed_after_the_proposal_blocks_the_whole_run(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        eerste = await _factuur(a, "INK-1")
        await _factuur(a, "INK-2")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql("UPDATE payables SET amount_cents = amount_cents + 1 WHERE id = :i", i=eerste)

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is False, antwoord.json()
        assert await _statussen() == {"INK-1": "ontvangen", "INK-2": "ontvangen"}

    async def test_a_supplier_iban_that_changed_after_the_proposal_blocks_the_run(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql("UPDATE suppliers SET iban = :n WHERE id = :i", n=IBAN_B, i=a)

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is False, antwoord.json()
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_an_invoice_approved_through_another_run_blocks_this_run(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        factuur = await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql("UPDATE payables SET status = 'goedgekeurd' WHERE id = :i", i=factuur)

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is False, antwoord.json()

    async def test_the_approval_leaves_a_log_line_without_iban(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]

        await _goedkeuren(integration_app, ref, STARTER)

        regels = (
            await _sql(
                "SELECT description, event_metadata FROM audit_logs WHERE event_type = 'payment_run_approved' "
                "AND tenant_id = :t",
                t=TENANT,
            )
        ).all()
        assert regels and ref in regels[-1][0] and IBAN_A not in str(regels[-1])


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetBetaalbestand:
    async def _goedgekeurd(self, integration_app: Any, *facturen: tuple[str, int, int]) -> None:
        """Maak facturen aan (nummer, leverancier, centen), laat de agent voorstellen en keur goed."""
        for nummer, leverancier, cents in facturen:
            await _factuur(leverancier, nummer, cents=cents)
        ref = (await _stel_voor())["ticket_ref"]
        antwoord = await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)
        assert antwoord.json()["executed"] is True, antwoord.json()

    async def test_the_file_has_the_right_amounts_and_ibans(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)
        await self._goedgekeurd(integration_app, ("INK-1", a, 120000), ("INK-2", b, 45050))

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 200, antwoord.text
        wortel = ET.fromstring(antwoord.json()["data"]["bestand"])
        bedragen = sorted(e.text for e in wortel.findall(".//p:InstdAmt", NS))  # type: ignore[type-var]
        ibans = sorted(e.text for e in wortel.findall(".//p:CdtrAcct/p:Id/p:IBAN", NS))  # type: ignore[type-var]
        assert (bedragen, ibans) == (["1200.00", "450.50"], sorted([IBAN_A, IBAN_B]))
        assert wortel.findtext(".//p:GrpHdr/p:CtrlSum", namespaces=NS) == "1650.50"
        assert wortel.findtext(".//p:DbtrAcct/p:Id/p:IBAN", namespaces=NS) == EIGEN_IBAN

    async def test_the_invoices_are_in_the_payment_file_afterwards(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))

        await _haal_bestand(integration_app)

        assert await _statussen() == {"INK-1": "in_betaalbestand"}

    async def test_an_invoice_cannot_get_into_a_second_file(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))
        await _haal_bestand(integration_app)

        tweede = await _haal_bestand(integration_app)

        assert tweede.status_code == 409, tweede.text
        assert "hooguit" in tweede.json()["detail"]

    async def test_two_people_asking_at_the_same_time_get_one_file_between_them(
        self, integration_app: Any
    ) -> None:
        import asyncio

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))

        antwoorden = await asyncio.gather(
            _haal_bestand(integration_app), _haal_bestand(integration_app, door=ANDERE_GOEDKEURDER)
        )

        assert sorted(r.status_code for r in antwoorden) == [200, 409]

    async def test_a_file_without_approved_invoices_is_refused(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_a_bad_own_iban_refuses_the_file_and_leaves_the_invoices_approved(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))

        antwoord = await _haal_bestand(integration_app, debiteur_iban="NL91ABNA0417164301")

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "goedgekeurd"}

    async def test_after_a_refused_file_a_correct_request_still_works(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))
        await _haal_bestand(integration_app, debiteur_iban="NL91ABNA0417164301")

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 200, antwoord.text

    async def test_an_execution_date_in_the_past_refuses_the_file(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))

        antwoord = await _haal_bestand(
            integration_app, uitvoerdatum=(_vandaag() - timedelta(days=1)).isoformat()
        )

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "goedgekeurd"}

    async def test_a_supplier_changed_after_the_approval_refuses_the_file(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))
        await _sql(
            "UPDATE suppliers SET iban = :n, updated_at = now() WHERE id = :i", n=IBAN_B, i=a
        )

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 409
        assert "teruggezet" in antwoord.json()["detail"]
        assert await _statussen() == {"INK-1": "gecontroleerd"}

    async def test_the_request_may_not_carry_a_tenant(self, integration_app: Any) -> None:
        antwoord = await _haal_bestand(integration_app, tenant_id=2)

        assert antwoord.status_code == 422

    async def test_the_file_leaves_a_log_line_with_the_count_and_no_iban(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await self._goedgekeurd(integration_app, ("INK-1", a, 100000))

        await _haal_bestand(integration_app)

        regels = (
            await _sql(
                "SELECT event_metadata FROM audit_logs WHERE event_type = 'payment_file_created' AND tenant_id = :t",
                t=TENANT,
            )
        ).all()
        assert regels and regels[-1][0]["aantal"] == 1 and IBAN_A not in str(regels[-1])


@pytest.mark.integration
@pytest.mark.asyncio
class TestIsolatieEnRecht:
    async def test_another_tenant_sees_neither_the_proposal_nor_the_file(
        self, integration_app: Any
    ) -> None:
        from src.core.database.database import db_manager
        from src.core.tool_broker.hitl_repository import HITLTicketRepository
        from src.core.tool_broker.payment_run_registry import BetaalrunToolRegistry

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]

        async with db_manager.get_session() as session:
            gevonden = await HITLTicketRepository(session).get(ref, ANDERE_TENANT)
        selectie = await BetaalrunToolRegistry().selecteer(ANDERE_TENANT)

        assert (gevonden, selectie["regels"]) == (None, [])

    async def test_an_approved_invoice_of_another_tenant_never_ends_up_in_my_file(
        self, integration_app: Any
    ) -> None:
        vreemde_leverancier = await _leverancier("Vreemd BV", IBAN_B, tenant=ANDERE_TENANT)
        vreemd = await _factuur(
            vreemde_leverancier, "VREEMD-1", status="goedgekeurd", tenant=ANDERE_TENANT
        )
        await _sql("UPDATE payables SET checked_at = now() WHERE id = :i", i=vreemd)
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)

        bestand = await _haal_bestand(integration_app)

        assert "VREEMD" not in bestand.json()["data"]["bestand"]
        rij = (await _sql("SELECT status FROM payables WHERE id = :i", i=vreemd)).one()
        assert rij[0] == "goedgekeurd"

    async def test_a_user_without_the_approval_right_cannot_get_the_file(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", status="goedgekeurd")
        await _sql("UPDATE payables SET checked_at = now() WHERE tenant_id = :t", t=TENANT)

        antwoord = await _haal_bestand(integration_app, door=999)

        assert antwoord.status_code in (401, 403, 404), antwoord.text
        assert await _statussen() == {"INK-1": "goedgekeurd"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestReparatiesUitGate2:
    """Elke reparatie uit de twee reviews van 2026-10-25 heeft hier een toets die de oude fout laat zien."""

    async def test_the_copilot_identity_cannot_make_a_payment_run_ticket(self) -> None:
        """De Co-Pilot en de workflow-uitvoering maken tickets met de identiteit `copilot`; `propose_payment_run` staat alleen in het
        profiel `crediteuren`, dus zij kunnen er geen maken (dit is de echte bescherming tegen een zelfgemaakt voorstel)."""
        from src.core.database.database import db_manager
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        async with db_manager.get_session() as session:
            with pytest.raises(PermissionError):
                await HITLTicketRepository(session).create_hitl_request(
                    tenant_id=TENANT,
                    user_id=STARTER,
                    decision_id="d3-test",
                    reason="een eigen voorstel zonder vier ogen",
                    action_type="propose_payment_run",
                    action_params={"regels": [], "vier_ogen_vereist": False},
                )
        assert await _tickets() == []

    async def test_four_eyes_is_decided_from_the_database_not_from_the_flag_in_the_ticket(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-GROOT", cents=300000)
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE hitl_tickets SET payload = jsonb_set(payload, '{vier_ogen_vereist}', 'false') WHERE ticket_ref = :r",
            r=ref,
        )

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.status_code == 403, antwoord.text
        assert await _statussen() == {"INK-GROOT": "ontvangen"}

    async def test_an_expired_open_proposal_no_longer_holds_its_invoices(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE hitl_tickets SET expires_at = now() - interval '1 hour' WHERE ticket_ref = :r", r=ref
        )

        assert (await _stel_voor())["uitkomst"] == "ticket"

    async def test_a_ticket_with_another_supplier_name_is_not_executed(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE hitl_tickets SET payload = jsonb_set(payload, '{regels,0,supplier_name}', '\"Andere BV\"') "
            "WHERE ticket_ref = :r",
            r=ref,
        )

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is False, antwoord.json()
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_a_ticket_with_another_invoice_number_is_not_executed(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE hitl_tickets SET payload = jsonb_set(payload, '{regels,0,invoice_number}', '\"INK-VALS\"') "
            "WHERE ticket_ref = :r",
            r=ref,
        )

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is False, antwoord.json()

    async def test_one_changed_supplier_does_not_block_the_other_invoices(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)
        for nummer, leverancier in (("INK-1", a), ("INK-2", b)):
            await _factuur(leverancier, nummer)
        ref = (await _stel_voor())["ticket_ref"]
        await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)
        await _sql("UPDATE suppliers SET email = 'nieuw@leverancier.test', updated_at = now() WHERE id = :i", i=b)

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 200, antwoord.text
        data = antwoord.json()["data"]
        assert (data["aantal"], [o["invoice_number"] for o in data["overgeslagen"]]) == (1, ["INK-2"])
        assert await _statussen() == {"INK-1": "in_betaalbestand", "INK-2": "gecontroleerd"}

    async def test_an_invoice_returned_for_a_changed_supplier_can_be_proposed_and_approved_again(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)
        await _sql("UPDATE suppliers SET iban = :n, updated_at = now() WHERE id = :i", n=IBAN_B, i=a)
        assert (await _haal_bestand(integration_app)).status_code == 409

        opnieuw = await _stel_voor()
        antwoord = await _goedkeuren(integration_app, opnieuw["ticket_ref"], ANDERE_GOEDKEURDER)

        assert antwoord.json()["executed"] is True, antwoord.json()
        assert (await _haal_bestand(integration_app)).status_code == 200

    async def test_the_log_line_holds_a_fingerprint_of_the_file(self, integration_app: Any) -> None:
        import hashlib

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)

        antwoord = await _haal_bestand(integration_app)

        regels = (
            await _sql(
                "SELECT event_metadata FROM audit_logs WHERE event_type = 'payment_file_created' AND tenant_id = :t",
                t=TENANT,
            )
        ).all()
        verwacht = hashlib.sha256(antwoord.json()["data"]["bestand"].encode("utf-8")).hexdigest()
        assert regels[-1][0]["bestand_sha256"] == verwacht

    async def test_the_starter_may_approve_a_run_with_an_invoice_exactly_on_the_threshold(
        self, integration_app: Any
    ) -> None:
        """De HITL-route beslist zelf (uit de database) en `boven` is strikt: precies het drempelbedrag vraagt geen vier ogen."""
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-GRENS", cents=250000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is True, antwoord.json()

    @pytest.mark.parametrize(
        "regels",
        [None, [], "geen lijst", [{"payable_id": "1"}], [{"payable_id": True}], [{"payable_id": 987654321}], [42]],
    )
    async def test_four_eyes_fails_secure_when_the_lines_cannot_be_read(self, regels: object) -> None:
        from src.core.database.database import db_manager
        from src.core.tool_broker.payment_run_registry import vier_ogen_nodig

        async with db_manager.get_session() as session:
            assert await vier_ogen_nodig(session, TENANT, regels) is True

    async def test_four_eyes_is_not_needed_for_small_invoices_of_this_tenant(self) -> None:
        from src.core.database.database import db_manager
        from src.core.tool_broker.payment_run_registry import vier_ogen_nodig

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        klein = await _factuur(a, "INK-KLEIN", cents=1000)

        async with db_manager.get_session() as session:
            assert await vier_ogen_nodig(session, TENANT, [{"payable_id": klein}]) is False

    async def test_an_invoice_of_another_tenant_in_the_lines_asks_for_four_eyes(self) -> None:
        from src.core.database.database import db_manager
        from src.core.tool_broker.payment_run_registry import vier_ogen_nodig

        vreemde_leverancier = await _leverancier("Vreemd BV", IBAN_B, tenant=ANDERE_TENANT)
        vreemd = await _factuur(vreemde_leverancier, "VREEMD-1", cents=1000, tenant=ANDERE_TENANT)

        async with db_manager.get_session() as session:
            assert await vier_ogen_nodig(session, TENANT, [{"payable_id": vreemd}]) is True

    async def test_a_total_exactly_on_the_threshold_does_not_need_four_eyes(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=125000)
        await _factuur(a, "INK-2", cents=125000)

        payload = await _ticket_payload((await _stel_voor())["ticket_ref"])

        assert (payload["totaal_cents"], payload["vier_ogen_vereist"]) == (250000, False)

    async def test_the_starter_cannot_approve_a_run_whose_total_is_above_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=200000)
        await _factuur(a, "INK-2", cents=200000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.status_code == 403, antwoord.text
        assert await _statussen() == {"INK-1": "ontvangen", "INK-2": "ontvangen"}

    async def test_another_person_can_approve_a_run_whose_total_is_above_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=200000)
        await _factuur(a, "INK-2", cents=200000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)

        assert antwoord.json()["executed"] is True, antwoord.json()

    async def test_the_starter_may_approve_a_run_whose_total_is_exactly_on_the_threshold(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1", cents=125000)
        await _factuur(a, "INK-2", cents=125000)
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = await _goedkeuren(integration_app, ref, STARTER)

        assert antwoord.json()["executed"] is True, antwoord.json()

    async def test_the_database_decision_adds_up_the_invoices_of_the_lines(self) -> None:
        from src.core.database.database import db_manager
        from src.core.tool_broker.payment_run_registry import vier_ogen_nodig

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        een = await _factuur(a, "INK-1", cents=200000)
        twee = await _factuur(a, "INK-2", cents=200000)

        async with db_manager.get_session() as session:
            samen = await vier_ogen_nodig(session, TENANT, [{"payable_id": een}, {"payable_id": twee}])
            alleen = await vier_ogen_nodig(session, TENANT, [{"payable_id": een}])

        assert (samen, alleen) == (True, False)
