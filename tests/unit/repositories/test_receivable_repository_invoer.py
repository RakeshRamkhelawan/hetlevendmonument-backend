"""Handmatige invoer van debiteuren: bedrag, valuta en wijzigen (debiteurenagent dag 2).

P2 uit de review van dag 1: een negatief bedrag of een valuta als `eur` werd geaccepteerd. Nu de
invoerroutes er komen, is dat de plek waar zo'n fout binnenkomt. Echte SQLite-sessie, geen mocks
(zelfde opzet als `test_receivable_repository.py`, zie daar wat de autouse-fixtures uitzetten).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.rbac_models import Tenant
from src.core.repositories.receivable_repository import (
    NewReceivable,
    ReceivableChanges,
    ReceivableRepository,
)


async def _tenant(session: AsyncSession, tenant_id: int, slug: str) -> None:
    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()


def _factuur(nummer: str, **extra: object) -> NewReceivable:
    velden: dict[str, object] = {
        "customer_name": "Bakkerij De Korst",
        "customer_email": "administratie@dekorst.example",
        "invoice_number": nummer,
        "amount": Decimal("100.00"),
        "currency": "EUR",
        "due_date": date(2026, 9, 1),
    }
    velden.update(extra)
    return NewReceivable(**velden)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
class TestInvoerWordtGetoetst:
    async def test_a_negative_amount_is_refused(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "inv-a")
        with pytest.raises(ValueError, match="bedrag"):
            await ReceivableRepository(db_session).add(
                1, _factuur("N-1", amount=Decimal("-0.01"))
            )

    async def test_a_zero_amount_is_accepted(self, db_session: AsyncSession) -> None:
        """De grens zelf: nul is geen negatief bedrag (een creditnota-saldo van nul bestaat)."""
        await _tenant(db_session, 1, "inv-a")
        rij = await ReceivableRepository(db_session).add(1, _factuur("N-0", amount=Decimal("0")))
        assert rij.amount == Decimal("0")

    @pytest.mark.parametrize("valuta", ["eur", "EURO", "E1R", "", "EU"])
    async def test_a_currency_that_is_not_three_capital_letters_is_refused(
        self, db_session: AsyncSession, valuta: str
    ) -> None:
        await _tenant(db_session, 1, "inv-a")
        with pytest.raises(ValueError, match="valuta"):
            await ReceivableRepository(db_session).add(1, _factuur("C-1", currency=valuta))


@pytest.mark.unit
@pytest.mark.asyncio
class TestWijzigen:
    async def test_a_change_is_written_within_the_own_tenant(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "inv-a")
        repo = ReceivableRepository(db_session)
        rij = await repo.add(1, _factuur("W-1"))

        gewijzigd = await repo.update(1, rij.id, ReceivableChanges(status="betaald"))

        assert gewijzigd is not None and gewijzigd.status == "betaald"

    async def test_a_change_to_another_tenants_receivable_finds_nothing(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "inv-a")
        await _tenant(db_session, 2, "inv-b")
        repo = ReceivableRepository(db_session)
        vreemd = await repo.add(2, _factuur("W-2"))

        assert await repo.update(1, vreemd.id, ReceivableChanges(status="betaald")) is None
        onveranderd = await repo.get(2, vreemd.id)
        assert onveranderd is not None and onveranderd.status == "open"

    async def test_a_change_is_validated_like_new_input(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "inv-a")
        repo = ReceivableRepository(db_session)
        rij = await repo.add(1, _factuur("W-3"))

        with pytest.raises(ValueError, match="bedrag"):
            await repo.update(1, rij.id, ReceivableChanges(amount=Decimal("-5")))
