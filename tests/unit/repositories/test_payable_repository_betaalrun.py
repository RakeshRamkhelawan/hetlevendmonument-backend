"""`PayableRepository.keur_goed_voor_betaling` en `claim_voor_betaalbestand` -- crediteuren dag 3 (Keten F).

Echte database-sessie, zelfde opstelling als `test_payable_repository.py`. Wat hier wordt gemeten:

- elke methode raakt alleen rijen van de EIGEN tenant (isolatietest per methode, backend-patterns par. 11);
- een factuur komt hooguit een keer in `goedgekeurd` en hooguit een keer in `in_betaalbestand` (de statusvoorwaarde staat in de
  WHERE van een atomaire UPDATE, dus een tweede aanroep vindt niets meer).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau: `create_all` ziet alleen wat op dat moment in de metadata staat.
import src.core.database.import_all_models  # noqa: F401
from src.core.models.rbac_models import Tenant
from src.core.repositories.payable_repository import (
    NewPayable,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
)


async def _tenant(session: AsyncSession, tenant_id: int, slug: str) -> None:
    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()


async def _factuur(
    session: AsyncSession, tenant_id: int, nummer: str, status: str = "ontvangen"
) -> int:
    # Een leverancier per tenant: een IBAN hoort bij een leverancier (crediteuren nazorg), dus elke factuur een eigen leverancier met
    # hetzelfde IBAN kan niet meer.
    leveranciers = SupplierRepository(session)
    gevonden = await leveranciers.find_match(tenant_id, naam="Testleverancier", iban=None)
    leverancier = (
        gevonden[0]
        if gevonden
        else await leveranciers.add(
            tenant_id, NewSupplier(name="Testleverancier", iban="NL91ABNA0417164300")
        )
    )
    repo = PayableRepository(session)
    rij = await repo.add(
        tenant_id,
        NewPayable(
            supplier_id=leverancier.id,
            invoice_number=nummer,
            amount_cents=10000,
            invoice_date=date(2026, 10, 1),
            due_date=date(2026, 10, 31),
        ),
        created_by=None,
    )
    if status != "ontvangen":
        rij.status = status
        await session.flush()
    return int(rij.id)


async def _status(session: AsyncSession, tenant_id: int, payable_id: int) -> str | None:
    rij = await PayableRepository(session).get(tenant_id, payable_id)
    if rij is None:
        return None
    await session.refresh(rij)
    return str(rij.status)


@pytest.mark.unit
@pytest.mark.asyncio
class TestKeurGoedVoorBetaling:
    async def test_a_received_invoice_becomes_approved(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1")

        gedaan = await PayableRepository(db_session).keur_goed_voor_betaling(1, [eigen], door=5)

        assert (gedaan, await _status(db_session, 1, eigen)) == ([eigen], "goedgekeurd")

    async def test_a_checked_invoice_becomes_approved(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1", status="gecontroleerd")

        gedaan = await PayableRepository(db_session).keur_goed_voor_betaling(1, [eigen], door=5)

        assert gedaan == [eigen]

    async def test_the_approver_and_the_time_are_recorded(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1")
        repo = PayableRepository(db_session)

        await repo.keur_goed_voor_betaling(1, [eigen], door=5)

        rij = await repo.get(1, eigen)
        assert rij is not None
        await db_session.refresh(rij)
        assert (rij.checked_by_user_id, rij.checked_at is not None) == (5, True)

    async def test_an_invoice_of_another_tenant_is_never_touched(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        vreemd = await _factuur(db_session, 2, "B-1")

        gedaan = await PayableRepository(db_session).keur_goed_voor_betaling(1, [vreemd], door=5)

        assert (gedaan, await _status(db_session, 2, vreemd)) == ([], "ontvangen")

    async def test_the_same_invoice_is_approved_only_once(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1")
        repo = PayableRepository(db_session)
        await repo.keur_goed_voor_betaling(1, [eigen], door=5)

        tweede = await repo.keur_goed_voor_betaling(1, [eigen], door=6)

        assert tweede == []

    @pytest.mark.parametrize("status", ["betaald", "in_betaalbestand", "afgewezen", "goedgekeurd"])
    async def test_an_invoice_that_is_further_along_is_left_alone(
        self, db_session: AsyncSession, status: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1", status=status)

        gedaan = await PayableRepository(db_session).keur_goed_voor_betaling(1, [eigen], door=5)

        assert (gedaan, await _status(db_session, 1, eigen)) == ([], status)

    async def test_an_empty_list_does_nothing(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        assert await PayableRepository(db_session).keur_goed_voor_betaling(1, [], door=5) == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestClaimVoorBetaalbestand:
    async def test_approved_invoices_move_to_the_payment_file(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1", status="goedgekeurd")

        rijen = await PayableRepository(db_session).claim_voor_betaalbestand(1)

        assert ([r.id for r in rijen], await _status(db_session, 1, eigen)) == (
            [eigen],
            "in_betaalbestand",
        )

    async def test_the_rows_come_with_their_supplier(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _factuur(db_session, 1, "A-1", status="goedgekeurd")

        rijen = await PayableRepository(db_session).claim_voor_betaalbestand(1)

        assert rijen[0].supplier.iban == "NL91ABNA0417164300"

    async def test_a_second_claim_finds_nothing_so_an_invoice_is_in_one_file_only(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _factuur(db_session, 1, "A-1", status="goedgekeurd")
        repo = PayableRepository(db_session)
        await repo.claim_voor_betaalbestand(1)

        assert await repo.claim_voor_betaalbestand(1) == []

    @pytest.mark.parametrize(
        "status", ["ontvangen", "gecontroleerd", "in_betaalbestand", "betaald"]
    )
    async def test_an_invoice_that_is_not_approved_is_left_alone(
        self, db_session: AsyncSession, status: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        eigen = await _factuur(db_session, 1, "A-1", status=status)

        rijen = await PayableRepository(db_session).claim_voor_betaalbestand(1)

        assert (rijen, await _status(db_session, 1, eigen)) == ([], status)

    async def test_an_invoice_of_another_tenant_is_never_claimed(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        vreemd = await _factuur(db_session, 2, "B-1", status="goedgekeurd")

        rijen = await PayableRepository(db_session).claim_voor_betaalbestand(1)

        assert (rijen, await _status(db_session, 2, vreemd)) == ([], "goedgekeurd")

    async def test_the_rows_are_ordered_by_due_date(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        laat = await _factuur(db_session, 1, "A-LAAT", status="goedgekeurd")
        vroeg = await _factuur(db_session, 1, "A-VROEG", status="goedgekeurd")
        rij = await PayableRepository(db_session).get(1, vroeg)
        assert rij is not None
        rij.due_date = date(2026, 10, 5)
        await db_session.flush()

        rijen = await PayableRepository(db_session).claim_voor_betaalbestand(1)

        assert [r.id for r in rijen] == [vroeg, laat]


@pytest.mark.unit
@pytest.mark.asyncio
class TestTrekGoedkeuringIn:
    """`trek_goedkeuring_in` (crediteuren nazorg, punt 2): alleen `goedgekeurd`, alleen de eigen tenant, atomair."""

    async def test_an_approved_invoice_can_be_withdrawn_to_rejected(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        factuur = await _factuur(db_session, 1, "A-1", status="goedgekeurd")

        gedaan = await PayableRepository(db_session).trek_goedkeuring_in(1, [factuur], naar="afgewezen")

        assert (gedaan, await _status(db_session, 1, factuur)) == ([factuur], "afgewezen")

    async def test_an_approved_invoice_can_be_freed_for_a_new_proposal(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        factuur = await _factuur(db_session, 1, "A-1", status="goedgekeurd")

        await PayableRepository(db_session).trek_goedkeuring_in(1, [factuur], naar="gecontroleerd")

        assert await _status(db_session, 1, factuur) == "gecontroleerd"

    @pytest.mark.parametrize("status", ["ontvangen", "gecontroleerd", "in_betaalbestand", "betaald", "afgewezen"])
    async def test_an_invoice_that_is_not_approved_is_not_touched(
        self, db_session: AsyncSession, status: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        factuur = await _factuur(db_session, 1, "A-1", status=status)

        gedaan = await PayableRepository(db_session).trek_goedkeuring_in(1, [factuur], naar="afgewezen")

        assert (gedaan, await _status(db_session, 1, factuur)) == ([], status)

    async def test_an_invoice_of_another_tenant_is_not_touched(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        van_b = await _factuur(db_session, 2, "B-1", status="goedgekeurd")

        gedaan = await PayableRepository(db_session).trek_goedkeuring_in(1, [van_b], naar="afgewezen")

        assert (gedaan, await _status(db_session, 2, van_b)) == ([], "goedgekeurd")

    async def test_a_second_withdrawal_finds_nothing_any_more(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        factuur = await _factuur(db_session, 1, "A-1", status="goedgekeurd")
        repo = PayableRepository(db_session)
        await repo.trek_goedkeuring_in(1, [factuur], naar="afgewezen")

        assert await repo.trek_goedkeuring_in(1, [factuur], naar="afgewezen") == []

    async def test_any_other_target_status_is_refused(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        factuur = await _factuur(db_session, 1, "A-1", status="goedgekeurd")

        with pytest.raises(ValueError):
            await PayableRepository(db_session).trek_goedkeuring_in(1, [factuur], naar="betaald")

    async def test_an_empty_list_changes_nothing(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        assert await PayableRepository(db_session).trek_goedkeuring_in(1, [], naar="afgewezen") == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenIbanHoortBijEenLeverancier:
    """`SupplierRepository.add` en `update_iban` (crediteuren nazorg, punt 4): per tenant, hoofdletter- en spatieongevoelig."""

    async def test_a_second_supplier_with_the_same_iban_in_the_tenant_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        from src.core.exceptions import ValidatieFout

        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Een", iban="NL91ABNA0417164300"))

        with pytest.raises(ValidatieFout, match="IBAN"):
            await repo.add(1, NewSupplier(name="Twee", iban="nl91 abna 0417 1643 00"))

    async def test_the_same_iban_in_another_tenant_is_allowed(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Een", iban="NL91ABNA0417164300"))

        andere = await repo.add(2, NewSupplier(name="Een", iban="NL91ABNA0417164300"))

        assert andere.tenant_id == 2

    async def test_a_supplier_without_an_iban_never_clashes(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Een"))

        assert (await repo.add(1, NewSupplier(name="Twee"))).name == "Twee"

    async def test_changing_to_the_iban_of_another_supplier_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        from src.core.exceptions import ValidatieFout

        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Een", iban="NL91ABNA0417164300"))
        twee = await repo.add(1, NewSupplier(name="Twee", iban="NL02ABNA0123456789"))

        with pytest.raises(ValidatieFout, match="IBAN"):
            await repo.update_iban(1, twee.id, "NL91ABNA0417164300")

    async def test_the_message_names_the_other_supplier_of_the_same_tenant(
        self, db_session: AsyncSession
    ) -> None:
        from src.core.exceptions import ValidatieFout

        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Een", iban="NL91ABNA0417164300"))

        with pytest.raises(ValidatieFout, match="'Een'"):
            await repo.add(1, NewSupplier(name="Twee", iban="NL91ABNA0417164300"))
