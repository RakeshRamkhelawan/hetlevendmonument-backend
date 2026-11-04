"""Crediteuren nazorg (brief 2026-10-27-sprint-dag-crediteuren-nazorg, op develop 3ab31d76): vier punten, tegen een echte database.

1. een mislukte uitvoering na goedkeuren geeft de goedkeurder een vaste Nederlandse reden;
2. een goedgekeurde factuur en een goedgekeurd betaalvoorstel zijn in te trekken zolang er geen betaalbestand is, met reden, alleen met
   goedkeurrecht, met een auditregel;
3. een ticket voorbij zijn termijn telt als verlopen zonder de uurlijkse job en wordt opnieuw voorgelegd; een verlopen leveranciersticket
   laat de koppeling van de upload los;
4. een IBAN hoort bij een leverancier per tenant; het betaalbestand weigert twee leveranciers op een IBAN.

Echt zijn Postgres op netwerkpoort 5455 (eigen database `crd_agent`), de Council, de HITL-vloer, het ticket, de routes en de registry.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401
from tests.integration.test_crediteuren_betaalvoorstel_en_betaalbestand import (
    ANDERE_GOEDKEURDER,
    ANDERE_TENANT,
    IBAN_A,
    IBAN_B,
    STARTER,
    TENANT,
    _factuur,
    _goedkeuren,
    _haal_bestand,
    _leverancier,
    _stel_voor,
    _statussen,
    _ticket_payload,
)
from tests.integration.test_crediteurenagent_verwerkt_factuur import (  # noqa: F401
    _audit,
    _NepWorker,
    _post,
    _sql,
    _upload,
    _verwerk,
    worker,
)


@pytest_asyncio.fixture(autouse=True)
async def _opruimen(goedkeurder_gebruikers: None) -> AsyncGenerator[None, None]:
    yield
    await _sql("DELETE FROM payables WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM suppliers WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM hitl_tickets WHERE tenant_id = :t", t=TENANT)


REDEN = "Deze factuur hoort niet betaald te worden: dubbel besteld."
#: Een gebruiker van tenant 1 met de rol `crediteuren` (lezen en schrijven op payables) maar ZONDER het goedkeurrecht.
CREDITEUR = 2


@pytest_asyncio.fixture
async def crediteur_zonder_goedkeurrecht() -> AsyncGenerator[None, None]:
    await _sql(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = 'crediteuren' "
        "AND NOT EXISTS (SELECT 1 FROM user_roles x WHERE x.user_id = :u AND x.role_id = roles.id)",
        u=CREDITEUR,
        t=TENANT,
    )
    yield
    await _sql(
        "DELETE FROM user_roles WHERE user_id = :u AND tenant_id = :t "
        "AND role_id IN (SELECT id FROM roles WHERE tenant_id = :t AND name = 'crediteuren')",
        u=CREDITEUR,
        t=TENANT,
    )


async def _gekeurd(leverancier: int, nummer: str) -> int:
    """Een factuur die een mens heeft goedgekeurd (status EN wie en wanneer, zoals de goedkeuring zelf dat zet)."""
    factuur = await _factuur(leverancier, nummer, status="goedgekeurd")
    await _sql(
        "UPDATE payables SET checked_at = now(), checked_by_user_id = :d WHERE id = :i",
        d=ANDERE_GOEDKEURDER,
        i=factuur,
    )
    return factuur


async def _goedgekeurde_factuur(nummer: str = "INK-1", iban: str = IBAN_A) -> tuple[int, int]:
    leverancier = await _leverancier(f"Leverancier {nummer}", iban)
    return leverancier, await _gekeurd(leverancier, nummer)


async def _intrek_factuur(
    app: Any, payable_id: int, reden: str = REDEN, door: int = STARTER
) -> Any:
    return await _post(
        app, f"/api/v1/payables/{payable_id}/intrekken", {"reden": reden}, user_id=door
    )


async def _intrek_voorstel(app: Any, ref: str, reden: str = REDEN, door: int = STARTER) -> Any:
    return await _post(
        app,
        "/api/v1/payables/betaalvoorstel/intrekken",
        {"ticket_ref": ref, "reden": reden},
        user_id=door,
    )


async def _goedgekeurd_voorstel(app: Any) -> tuple[str, dict[str, int]]:
    """Twee facturen, een voorstel, goedgekeurd door een tweede persoon (veilig ook boven de drempel)."""
    a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
    b = await _leverancier("Kantoor Totaal", IBAN_B)
    ids = {"INK-1": await _factuur(a, "INK-1"), "INK-2": await _factuur(b, "INK-2")}
    ref = (await _stel_voor())["ticket_ref"]
    antwoord = await _goedkeuren(app, ref, ANDERE_GOEDKEURDER)
    assert antwoord.json()["executed"] is True, antwoord.json()
    return ref, ids


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenNederlandseRedenBijEenMislukteUitvoering:
    async def test_a_changed_iban_after_the_proposal_gives_a_dutch_reason_for_the_approver(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE suppliers SET iban = :n, updated_at = now() WHERE id = :i", n=IBAN_B, i=a
        )

        antwoord = (await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)).json()

        assert antwoord["executed"] is False
        assert "rekeningnummer" in antwoord["execution_message"]
        assert "opnieuw worden voorgelegd" in antwoord["execution_message"]

    async def test_the_reason_never_holds_the_raw_tool_text_or_the_invoice_number(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-GEHEIM-9")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql(
            "UPDATE suppliers SET iban = :n, updated_at = now() WHERE id = :i", n=IBAN_B, i=a
        )

        antwoord = (await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)).json()

        assert "INK-GEHEIM-9" not in str(antwoord["execution_message"])
        assert antwoord["execution_error"] == "tool_failure"

    async def test_a_changed_invoice_gives_its_own_sentence(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        factuur = await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]
        await _sql("UPDATE payables SET amount_cents = 1 WHERE id = :i", i=factuur)

        antwoord = (await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)).json()

        assert "veranderd" in antwoord["execution_message"]

    async def test_a_successful_approval_has_no_failure_message(self, integration_app: Any) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]

        antwoord = (await _goedkeuren(integration_app, ref, ANDERE_GOEDKEURDER)).json()

        assert antwoord.get("execution_message") is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenGoedgekeurdeFactuurIntrekken:
    async def test_an_approved_invoice_outside_a_file_can_be_withdrawn_with_a_reason(
        self, integration_app: Any
    ) -> None:
        _, factuur = await _goedgekeurde_factuur()

        antwoord = await _intrek_factuur(integration_app, factuur)

        assert antwoord.status_code == 200, antwoord.text
        assert await _statussen() == {"INK-1": "afgewezen"}

    async def test_the_withdrawal_leaves_an_audit_line_with_the_reason(
        self, integration_app: Any
    ) -> None:
        _, factuur = await _goedgekeurde_factuur()

        await _intrek_factuur(integration_app, factuur)

        regels = [r for r in await _audit("payable_withdrawn") if r[1].get("payable_id") == factuur]
        assert len(regels) == 1
        assert regels[0][1]["reden"] == REDEN

    @pytest.mark.parametrize("reden", ["", "kort", "          "])
    async def test_a_missing_or_too_short_reason_is_refused_and_nothing_changes(
        self, integration_app: Any, reden: str
    ) -> None:
        _, factuur = await _goedgekeurde_factuur()

        antwoord = await _intrek_factuur(integration_app, factuur, reden)

        assert antwoord.status_code in (400, 422)
        assert await _statussen() == {"INK-1": "goedgekeurd"}

    async def test_an_invoice_in_a_payment_file_cannot_be_withdrawn(
        self, integration_app: Any
    ) -> None:
        _, factuur = await _goedgekeurde_factuur()
        assert (await _haal_bestand(integration_app)).status_code == 200

        antwoord = await _intrek_factuur(integration_app, factuur)

        assert antwoord.status_code == 409
        assert "betaalbestand" in antwoord.json()["detail"]
        assert await _statussen() == {"INK-1": "in_betaalbestand"}

    async def test_an_invoice_that_is_not_approved_cannot_be_withdrawn(
        self, integration_app: Any
    ) -> None:
        leverancier = await _leverancier("Leverancier X", IBAN_A)
        factuur = await _factuur(leverancier, "INK-1", status="gecontroleerd")

        antwoord = await _intrek_factuur(integration_app, factuur)

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "gecontroleerd"}

    async def test_a_user_without_the_approval_right_cannot_withdraw(
        self, integration_app: Any, crediteur_zonder_goedkeurrecht: None
    ) -> None:
        _, factuur = await _goedgekeurde_factuur()

        antwoord = await _intrek_factuur(integration_app, factuur, door=CREDITEUR)

        assert antwoord.status_code == 403
        assert await _statussen() == {"INK-1": "goedgekeurd"}

    async def test_an_invoice_of_another_tenant_does_not_exist_here(
        self, integration_app: Any
    ) -> None:
        leverancier = await _leverancier("Leverancier X", IBAN_A, tenant=ANDERE_TENANT)
        factuur = await _factuur(leverancier, "INK-X", status="goedgekeurd", tenant=ANDERE_TENANT)

        antwoord = await _intrek_factuur(integration_app, factuur)

        assert (antwoord.status_code, antwoord.json()["detail"]) == (404, "Payable not found")
        rij = (await _sql("SELECT status FROM payables WHERE id = :i", i=factuur)).one()
        assert rij[0] == "goedgekeurd"

    async def test_a_withdrawn_invoice_is_never_proposed_again(self, integration_app: Any) -> None:
        _, factuur = await _goedgekeurde_factuur()
        await _intrek_factuur(integration_app, factuur)

        assert (await _stel_voor())["uitkomst"] == "niets_te_betalen"


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenGoedgekeurdBetaalvoorstelIntrekken:
    async def test_an_approved_run_without_a_file_can_be_withdrawn_and_the_invoices_are_free_again(
        self, integration_app: Any
    ) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)

        antwoord = await _intrek_voorstel(integration_app, ref)

        assert antwoord.status_code == 200, antwoord.text
        assert await _statussen() == {"INK-1": "gecontroleerd", "INK-2": "gecontroleerd"}
        assert (await _stel_voor())["uitkomst"] == "ticket"

    async def test_the_run_binding_survives_the_approval_in_the_ticket_itself(
        self, integration_app: Any
    ) -> None:
        ref, ids = await _goedgekeurd_voorstel(integration_app)

        payload = await _ticket_payload(ref)

        assert sorted(payload["_betaalrun_facturen"]) == sorted(ids.values())

    async def test_the_withdrawal_leaves_an_audit_line_with_the_reason(
        self, integration_app: Any
    ) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)

        await _intrek_voorstel(integration_app, ref)

        regels = [r for r in await _audit("payment_run_withdrawn") if r[1].get("ticket_ref") == ref]
        assert len(regels) == 1
        assert regels[0][1]["reden"] == REDEN

    async def test_after_the_file_is_made_the_run_cannot_be_withdrawn(
        self, integration_app: Any
    ) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)
        assert (await _haal_bestand(integration_app)).status_code == 200

        antwoord = await _intrek_voorstel(integration_app, ref)

        assert antwoord.status_code == 409
        assert "eenmalig" in antwoord.json()["detail"]
        assert await _statussen() == {"INK-1": "in_betaalbestand", "INK-2": "in_betaalbestand"}

    async def test_withdrawing_twice_is_refused_the_second_time(self, integration_app: Any) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)
        await _intrek_voorstel(integration_app, ref)

        assert (await _intrek_voorstel(integration_app, ref)).status_code == 409

    async def test_a_user_without_the_approval_right_cannot_withdraw_a_run(
        self, integration_app: Any, crediteur_zonder_goedkeurrecht: None
    ) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)

        antwoord = await _intrek_voorstel(integration_app, ref, door=CREDITEUR)

        assert antwoord.status_code == 403
        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "goedgekeurd"}

    async def test_a_reason_is_required_for_a_run_too(self, integration_app: Any) -> None:
        ref, _ = await _goedgekeurd_voorstel(integration_app)

        antwoord = await _intrek_voorstel(integration_app, ref, "kort")

        assert antwoord.status_code in (400, 422)
        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "goedgekeurd"}

    async def test_a_ticket_that_is_not_an_approved_run_cannot_be_withdrawn(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        ref = (await _stel_voor())["ticket_ref"]  # nog niet goedgekeurd

        antwoord = await _intrek_voorstel(integration_app, ref)

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "ontvangen"}

    async def test_a_second_withdrawal_of_an_old_ticket_does_not_release_the_invoices_of_a_newer_run(
        self, integration_app: Any
    ) -> None:
        eerste, _ = await _goedgekeurd_voorstel(integration_app)
        await _intrek_voorstel(integration_app, eerste)
        nieuw = (await _stel_voor())["ticket_ref"]
        antwoord = await _goedkeuren(integration_app, nieuw, ANDERE_GOEDKEURDER)
        assert antwoord.json()["executed"] is True, antwoord.json()

        tweede_keer = await _intrek_voorstel(integration_app, eerste)

        assert tweede_keer.status_code == 409
        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "goedgekeurd"}

    async def test_a_run_of_which_one_invoice_is_already_in_a_file_is_not_withdrawn_at_all(
        self, integration_app: Any
    ) -> None:
        ref, ids = await _goedgekeurd_voorstel(integration_app)
        await _sql("UPDATE payables SET status = 'in_betaalbestand' WHERE id = :i", i=ids["INK-2"])

        antwoord = await _intrek_voorstel(integration_app, ref)

        assert antwoord.status_code == 409
        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "in_betaalbestand"}

    async def test_an_unknown_ticket_gives_404(self, integration_app: Any) -> None:
        antwoord = await _intrek_voorstel(integration_app, "hitl_bestaat_niet")

        assert (antwoord.status_code, antwoord.json()["detail"]) == (404, "Ticket not found")


@pytest.mark.integration
@pytest.mark.asyncio
class TestNietsBlijftStilLiggen:
    async def _verloop(self, ref: str) -> None:
        await _sql(
            "UPDATE hitl_tickets SET expires_at = now() - interval '1 hour' WHERE ticket_ref = :r",
            r=ref,
        )

    async def test_a_new_proposal_after_an_expired_one_says_it_was_presented_before(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")
        eerste = (await _stel_voor())["ticket_ref"]
        await self._verloop(eerste)

        tweede = (await _stel_voor())["ticket_ref"]

        assert tweede != eerste
        assert (
            "eerder voorgelegd, niet op tijd beoordeeld"
            in (await _ticket_payload(tweede))["waarom"]
        )

    async def test_a_first_proposal_does_not_carry_that_sentence(self) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _factuur(a, "INK-1")

        ref = (await _stel_voor())["ticket_ref"]

        assert "eerder voorgelegd" not in (await _ticket_payload(ref))["waarom"]

    async def test_an_expired_supplier_ticket_releases_the_upload_so_it_is_presented_again(
        self, worker: _NepWorker
    ) -> None:
        bestand_id = _upload(worker)
        eerste = (await _verwerk(bestand_id))["ticket_ref"]
        await self._verloop(eerste)

        opnieuw = await _verwerk(bestand_id)

        assert opnieuw["uitkomst"] == "ticket", opnieuw
        assert opnieuw["ticket_ref"] != eerste
        assert (
            "eerder voorgelegd, niet op tijd beoordeeld"
            in (await _ticket_payload(opnieuw["ticket_ref"]))["waarom"]
        )

    async def test_a_supplier_ticket_that_is_still_open_keeps_the_upload_claimed(
        self, worker: _NepWorker
    ) -> None:
        bestand_id = _upload(worker)
        await _verwerk(bestand_id)

        opnieuw = await _verwerk(bestand_id)

        assert opnieuw["uitkomst"] == "al_verwerkt"


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenIbanHoortBijEenLeverancier:
    async def test_a_second_supplier_with_an_existing_iban_is_refused_in_dutch(self) -> None:
        from src.core.exceptions import ValidatieFout

        await _leverancier("Drukkerij Van Dijk BV", IBAN_A)

        with pytest.raises(ValidatieFout, match="IBAN"):
            await _leverancier("Een Andere BV", IBAN_A)

    async def test_the_same_iban_in_another_tenant_is_allowed(self) -> None:
        await _leverancier("Drukkerij Van Dijk BV", IBAN_A)

        assert await _leverancier("Drukkerij Van Dijk BV", IBAN_A, tenant=ANDERE_TENANT) > 0

    async def test_the_iban_is_compared_without_spaces_and_case(self) -> None:
        from src.core.exceptions import ValidatieFout

        await _leverancier("Drukkerij Van Dijk BV", IBAN_A)

        with pytest.raises(ValidatieFout):
            await _leverancier("Een Andere BV", "nl02 abna 0123 4567 89")

    async def test_changing_the_iban_of_a_supplier_to_one_of_another_supplier_is_refused(
        self,
    ) -> None:
        from src.core.database.database import db_manager
        from src.core.exceptions import ValidatieFout
        from src.core.repositories.payable_repository import SupplierRepository

        await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)

        async with db_manager.get_session() as session:
            with pytest.raises(ValidatieFout, match="IBAN"):
                await SupplierRepository(session).update_iban(TENANT, b, IBAN_A)

    async def test_setting_the_same_iban_on_the_same_supplier_is_fine(self) -> None:
        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import SupplierRepository

        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)

        async with db_manager.get_session() as session:
            assert await SupplierRepository(session).update_iban(TENANT, a, IBAN_A) is not None

    async def test_the_payment_file_refuses_two_suppliers_on_one_iban_and_pays_nothing(
        self, integration_app: Any
    ) -> None:
        # Een bestaande tweedeling (van voor de controle) laat zich niet via de repository maken: direct in de database.
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        b = await _leverancier("Kantoor Totaal", IBAN_B)
        await _sql("UPDATE suppliers SET iban = :n WHERE id = :i", n=IBAN_A, i=b)
        await _gekeurd(a, "INK-1")
        await _gekeurd(b, "INK-2")

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 409, antwoord.text
        assert (
            "Drukkerij Van Dijk BV" in antwoord.json()["detail"]
            and "Kantoor Totaal" in antwoord.json()["detail"]
        )
        assert await _statussen() == {"INK-1": "goedgekeurd", "INK-2": "goedgekeurd"}

    async def test_two_invoices_of_the_same_supplier_on_one_iban_are_fine(
        self, integration_app: Any
    ) -> None:
        a = await _leverancier("Drukkerij Van Dijk BV", IBAN_A)
        await _gekeurd(a, "INK-1")
        await _gekeurd(a, "INK-2")

        antwoord = await _haal_bestand(integration_app)

        assert antwoord.status_code == 200, antwoord.text
