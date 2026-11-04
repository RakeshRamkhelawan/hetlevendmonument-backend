"""`ReceivableRepository` -- de databron van de debiteurenagent (dag 1, 2026-10-04).

Echte database-sessie, geen mocks: alleen een echte query tegen rijen van twee tenants
bewijst tenant-isolatie (patroon: `TestScheduleTrainingTenantIsolation` in
`tests/unit/tool_broker/test_hr_schedule_training.py`).

**Wat de opstelling uitzet, nagelopen.** `tests/conftest.py::_reset_global_state` (autouse)
haalt de globale `do_orm_execute`-tenantfilter weg. Dat is hier gewenst: zonder die
listener is het het EIGEN filter van de repository dat de isolatie moet leveren, en dat is
precies wat deze module meet. Er staat geen patch op de repository of het model.

**Wat deze module NIET zegt.** Of de DATABASE tenant B afschermt als de repository zich
vergist: dat meet `tests/integration/security/test_receivables_is_confined_to_its_tenant.py`
(RLS, als niet-eigenaar).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau: `create_all` in de `async_engine`-fixture ziet alleen wat op dat
# moment in de metadata staat (zelfde reden als test_hr_schedule_training.py).
import src.core.database.import_all_models  # noqa: F401
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable
from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository


async def _tenant(session: AsyncSession, tenant_id: int, slug: str) -> None:
    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()


def _factuur(nummer: str, **extra: object) -> NewReceivable:
    velden: dict[str, object] = {
        "customer_name": "Bakkerij De Korst",
        "customer_email": "administratie@dekorst.example",
        "invoice_number": nummer,
        "amount": Decimal("1250.50"),
        "currency": "EUR",
        "due_date": date(2026, 9, 1),
    }
    velden.update(extra)
    return NewReceivable(**velden)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
class TestReceivableTenantIsolation:
    async def test_tenant_a_does_not_list_a_receivable_of_tenant_b(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "deb-a")
        await _tenant(db_session, 2, "deb-b")
        repo = ReceivableRepository(db_session)
        await repo.add(1, _factuur("A-001"))
        await repo.add(2, _factuur("B-001"))

        nummers = {r.invoice_number for r in await repo.list_for_tenant(1)}

        assert nummers == {"A-001"}, (
            f"Tenant 1 ziet {sorted(nummers)}; verwacht alleen zijn eigen A-001."
        )

    async def test_tenant_a_cannot_get_a_receivable_of_tenant_b_by_id(
        self, db_session: AsyncSession
    ) -> None:
        """Ook met het exacte id van de buren: geen rij."""
        await _tenant(db_session, 1, "deb-a")
        await _tenant(db_session, 2, "deb-b")
        repo = ReceivableRepository(db_session)
        vreemd = await repo.add(2, _factuur("B-001"))

        assert await repo.get(1, vreemd.id) is None
        eigen = await repo.get(2, vreemd.id)
        assert eigen is not None and eigen.invoice_number == "B-001", (
            "De eigen tenant vindt zijn rij niet terug: dan bewijst de weigering hierboven niets."
        )

    async def test_the_row_is_written_under_the_given_tenant_and_nothing_else(
        self, db_session: AsyncSession
    ) -> None:
        """Een directe query (buiten de repository om) toont de tenant van de aanroeper."""
        await _tenant(db_session, 1, "deb-a")
        await _tenant(db_session, 2, "deb-b")
        await ReceivableRepository(db_session).add(2, _factuur("B-777"))

        rijen = (await db_session.execute(select(Receivable))).scalars().all()

        assert [(r.tenant_id, r.invoice_number) for r in rijen] == [(2, "B-777")]

    def test_the_input_has_no_tenant_field(self) -> None:
        """tenant_id komt uit de context (parameter), nooit uit de payload."""
        velden = {f.name for f in dataclasses.fields(NewReceivable)}

        assert "tenant_id" not in velden, (
            "NewReceivable heeft een tenant_id-veld: dan kan een verzoek de tenant kiezen."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestReceivableDefaults:
    async def test_a_new_receivable_is_open_manual_and_timestamped(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "deb-a")
        rij = await ReceivableRepository(db_session).add(1, _factuur("A-002"))

        assert rij.status == "open"
        assert rij.source == "handmatig"
        assert rij.external_id is None
        assert rij.amount == Decimal("1250.50")
        assert rij.created_at is not None

    async def test_an_unknown_status_is_refused(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "deb-a")

        with pytest.raises(ValueError, match="status"):
            await ReceivableRepository(db_session).add(1, _factuur("A-003", status="weg"))

    async def test_a_float_amount_is_refused(self, db_session: AsyncSession) -> None:
        """Geld is decimaal; een float wordt niet stil omgezet."""
        await _tenant(db_session, 1, "deb-a")

        with pytest.raises(TypeError, match="Decimal"):
            await ReceivableRepository(db_session).add(1, _factuur("A-004", amount=12.5))
