"""De twee debiteurentools: lezen (MEDIUM) en een herinnering klaarzetten (HIGH) -- dag 2.

Echte SQLite-sessie via een fabriek die de testsessie teruggeeft; geen mock van de database.
`tests/conftest.py::_reset_global_state` haalt de globale tenantfilter weg, dus het is het EIGEN
filter van de registry dat hier de isolatie moet leveren -- precies wat deze module meet.

Wat hier NIET gemeten wordt: de HITL-poort (die zit in de broker, VOOR deze registry) en de
goedkeuring zelf. Dat doet `tests/integration/scenarios/test_scenario_5_betalingsherinnering.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401

LEZEN = "list_receivables"
VERSTUREN = "send_payment_reminder"


class _Fabriek:
    """Geeft de bestaande testsessie terug; commit niet zelf, dat moet de tool doen."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _Fabriek:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> None:
        return None


def _registry(session: AsyncSession) -> Any:
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    return ReceivablesToolRegistry(_Fabriek(session))


async def _seed(session: AsyncSession, tenant_id: int, slug: str, nummer: str) -> int:
    from src.core.models.rbac_models import Tenant
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    if await session.get(Tenant, tenant_id) is None:
        session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
        await session.flush()
    rij = await ReceivableRepository(session).add(
        tenant_id,
        NewReceivable(
            customer_name=f"Klant {slug}",
            customer_email=f"{slug}@klant.example",
            invoice_number=nummer,
            amount=Decimal("250.00"),
            currency="EUR",
            due_date=date(2026, 9, 1),
        ),
    )
    await session.commit()
    return rij.id


async def _berichten(session: AsyncSession) -> list[Any]:
    from src.core.models.outgoing_message_models import OutgoingMessage

    return list((await session.execute(select(OutgoingMessage))).scalars().all())


async def _brief(session: AsyncSession, tenant_id: int, receivable_id: int) -> dict[str, object]:
    voorbeeld = await _registry(session).preview_payment_reminder(
        tenant_id, receivable_id, "herinnering"
    )
    assert voorbeeld["success"] is True, voorbeeld
    params = voorbeeld["params"]
    assert isinstance(params, dict)
    return dict(params)


@pytest.mark.unit
@pytest.mark.asyncio
class TestLezen:
    async def test_a_tenant_lists_only_its_own_receivables(self, db_session: AsyncSession) -> None:
        await _seed(db_session, 1, "a", "A-1")
        await _seed(db_session, 2, "b", "B-1")

        uit = await _registry(db_session).execute_receivables_tool(LEZEN, {}, tenant_id=1)

        assert [r["invoice_number"] for r in uit["receivables"]] == ["A-1"]

    async def test_the_list_carries_no_name_and_no_email(self, db_session: AsyncSession) -> None:
        """Het resultaat gaat de event bus en de leeropslag in; geen persoonsgegevens daar."""
        await _seed(db_session, 1, "a", "A-1")

        uit = await _registry(db_session).execute_receivables_tool(LEZEN, {}, tenant_id=1)

        assert set(uit["receivables"][0]) == {
            "receivable_id",
            "invoice_number",
            "amount",
            "currency",
            "due_date",
            "status",
        }

    async def test_an_unknown_filter_is_refused(self, db_session: AsyncSession) -> None:
        uit = await _registry(db_session).execute_receivables_tool(
            LEZEN, {"customer_email": "x@y"}, tenant_id=1
        )
        assert uit["success"] is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestVoorbeeld:
    async def test_the_preview_takes_recipient_and_text_from_the_receivable(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")

        params = await _brief(db_session, 1, rid)

        assert params["recipient_email"] == "a@klant.example"
        assert "A-1" in str(params["subject"]) and "EUR 250.00" in str(params["body"])

    async def test_another_tenants_receivable_gives_no_preview(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 2, "b", "B-1")

        uit = await _registry(db_session).preview_payment_reminder(1, rid, "herinnering")

        assert uit["success"] is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestVersturen:
    async def test_exactly_one_message_with_exactly_the_approved_text_is_written(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t1"}, tenant_id=1
        )

        berichten = await _berichten(db_session)
        assert uit["success"] is True
        assert [(b.recipient, b.subject, b.body, b.hitl_ticket_ref) for b in berichten] == [
            (params["recipient_email"], params["subject"], params["body"], "hitl_t1")
        ]

    async def test_queueing_the_letter_does_not_mark_the_receivable_as_reminded(
        self, db_session: AsyncSession
    ) -> None:
        """`herinnerd` zet de verzendlus na verzending (wfb-dag1 stap 2), niet het klaarzetten."""
        from src.core.models.receivable_models import Receivable

        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t2"}, tenant_id=1
        )

        rij = await db_session.get(Receivable, rid)
        assert rij is not None and (rij.status, rij.herinnerd_op) == ("open", None)

    async def test_a_changed_text_is_refused_and_nothing_is_written(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        params["body"] = "Betaal nu of anders."

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t2"}, tenant_id=1
        )

        assert uit["success"] is False and await _berichten(db_session) == []

    async def test_another_tenants_receivable_is_refused(self, db_session: AsyncSession) -> None:
        rid = await _seed(db_session, 2, "b", "B-1")
        params = await _brief(db_session, 2, rid)

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t2"}, tenant_id=1
        )

        assert uit["success"] is False and await _berichten(db_session) == []

    async def test_an_unknown_field_is_refused(self, db_session: AsyncSession) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "cc": "baas@klant.example", "_hitl_ticket_ref": "x"}, tenant_id=1
        )

        assert uit["success"] is False and await _berichten(db_session) == []

    async def test_a_paid_receivable_gets_no_reminder(self, db_session: AsyncSession) -> None:
        from src.core.repositories.receivable_repository import (
            ReceivableChanges,
            ReceivableRepository,
        )

        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        await ReceivableRepository(db_session).update(1, rid, ReceivableChanges(status="betaald"))
        await db_session.commit()

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t2"}, tenant_id=1
        )

        assert uit["success"] is False and await _berichten(db_session) == []

    async def test_the_answer_does_not_echo_the_letter(self, db_session: AsyncSession) -> None:
        """Via `act()` gaat het antwoord de LLM-context in; die is niet gedigest."""
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_t2"}, tenant_id=1
        )

        assert str(params["body"]) not in str(uit) and "a@klant.example" not in str(uit)

    async def test_without_an_approved_ticket_nothing_is_written(
        self, db_session: AsyncSession
    ) -> None:
        """UNIQUE telt NULL niet als dubbel; zonder ticketref zou eenmaligheid wegvallen."""
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)

        uit = await _registry(db_session).execute_receivables_tool(VERSTUREN, params, tenant_id=1)

        assert uit["success"] is False and await _berichten(db_session) == []
