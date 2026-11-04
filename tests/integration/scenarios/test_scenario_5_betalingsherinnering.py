"""Meetlat scenario 5 als integratietest: de debiteurenagent wil een herinnering sturen.

1. De agent wil een brief sturen (riskant) -> er komt een goedkeuringsticket.
2. Het ticket toont wat er gebeurt, aan wie en met welke inhoud.
3a. Goedkeuren voert precies die actie uit: EEN rij in `outgoing_messages`, met precies die tekst.
3b. Afkeuren stopt echt: GEEN rij.
4. Elke beslissing staat als `hitl_decision` met tijdstip in `audit_logs`.

Twee standen van de vier-ogen-instelling (ADR-039): UIT (de aanvrager beslist zelf) en AAN (de
aanvrager mag niet, een collega wel).

**Wat echt is en wat niet.** Echt: Postgres op netwerkpoort 5455, de Council
(`request_council_decision_for_agent`), de hitl-vloer en het ticket in `hitl_tickets`, de
HITL-routes met `get_tool_broker_service`, de broker met zijn verzilvering, de registry en de
auditketen. Vervangen: het taalmodel (een scriptdubbel met een vaste TOOL_CALL -- de
mock-provider komt nooit bij een tool), `get_current_user` (de gezaaide gebruikers 1 en 101 van
tenant 1, beide beheerder; het JWT voor de middleware wordt met de testhelper gemaakt) en de
CSRF-controle (Redis-gebonden; heeft eigen tests).

**Waarom `db_manager` en niet `postgres_session`.** De agent, de Council en de registry openen
hun eigen sessies via `db_manager`; wat in de terugrollende testtransactie staat, zien zij niet.
Daarom wordt hier echt gecommit en na elke test opgeruimd.

Wat NIET gemeten is: een draaiende applicatie met een scherm (dag 3/4), en de start van de agent
via een route (dag 3). Dit is de keten eronder.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401

TENANT = 1
AANVRAGER = 1
COLLEGA = 101
_TICKET = re.compile(r"goedkeuringsticket aangemaakt: (hitl_[0-9a-f]+)")


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


async def _zet_vier_ogen(aan: bool) -> None:
    waarde = '{"four_eyes_actions": ["send_payment_reminder"]}' if aan else "{}"
    await _sql("UPDATE tenants SET settings = CAST(:s AS JSON) WHERE id = :t", s=waarde, t=TENANT)


@pytest_asyncio.fixture
async def debiteur(goedkeurder_gebruikers: None) -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    async with db_manager.get_session() as session:
        rij = await ReceivableRepository(session).add(
            TENANT,
            NewReceivable(
                customer_name="Bakkerij De Korst",
                customer_email="administratie@dekorst.example",
                invoice_number="F-2026-042",
                amount=Decimal("1250.50"),
                currency="EUR",
                due_date=date(2026, 9, 1),
            ),
        )
        await session.commit()
        rid = rij.id
    yield rid
    await _sql("DELETE FROM outgoing_messages WHERE tenant_id = :t", t=TENANT)
    await _sql("DELETE FROM hitl_tickets WHERE tenant_id = :t", t=TENANT)
    await _sql("DELETE FROM receivables WHERE id = :r", r=rid)
    await _zet_vier_ogen(False)


async def _agent_vraagt_aan(receivable_id: int) -> str:
    """Stap 1: de agent, met een scriptdubbel als taalmodel. Geeft de ticketref terug."""
    from src.core.als.agents.skills.dunning import DunningSkill

    agent = DunningSkill(tenant_id=TENANT)
    model = AsyncMock()
    model.generate = AsyncMock(
        return_value=(
            "Factuur F-2026-042 is over de vervaldatum.\n"
            f'TOOL_CALL: send_payment_reminder {{"receivable_id": {receivable_id}, '
            '"kind": "herinnering"}'
        )
    )

    async def _model() -> Any:
        return model

    agent._get_llm_service = _model  # type: ignore[method-assign]
    resultaat = await agent.execute_with_manifest_prompt(
        {"task": "Stuur een herinnering voor F-2026-042"}, initiated_by_user_id=AANVRAGER
    )
    fouten = " ".join(str(f.get("error")) for f in resultaat.result_data.get("errors", []))
    gevonden = _TICKET.search(fouten)
    assert gevonden, f"geen goedkeuringsticket; de agent meldde: {fouten}"
    return gevonden.group(1)


def _beslisser(user_id: int) -> Any:
    from src.core.auth.auth_service import UserResponse

    return UserResponse(
        id=user_id, email=f"u{user_id}@integration.test", tenant_id=TENANT, roles=["admin"]
    )


async def _beslis(
    integration_app: Any, user_id: int, pad: str, body: dict[str, str]
) -> Any:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import db_manager, get_db

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    overrides = {
        get_db: _db,
        get_current_user: lambda: _beslisser(user_id),
        validate_csrf_token: _geen_csrf,
    }
    from tests.integration.conftest import _build_test_token

    token = _build_test_token(
        user_id=user_id, email=f"u{user_id}@integration.test", tenant_id=TENANT
    )
    integration_app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.post(f"/api/v1/tools/hitl/{pad}", json=body)
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


async def _ticket_payload(ref: str) -> dict[str, Any]:
    rij = (await _sql("SELECT payload FROM hitl_tickets WHERE ticket_ref = :r", r=ref)).one()
    return dict(rij[0])


async def _berichten() -> list[Any]:
    return list(
        (
            await _sql(
                "SELECT recipient, subject, body, hitl_ticket_ref FROM outgoing_messages "
                "WHERE tenant_id = :t",
                t=TENANT,
            )
        ).all()
    )


async def _beslissingen(ref: str) -> list[Any]:
    return list(
        (
            await _sql(
                "SELECT action, timestamp, user_id FROM audit_logs "
                "WHERE event_type = 'hitl_decision' AND event_metadata->>'ticket_ref' = :r",
                r=ref,
            )
        ).all()
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestVierOgenUit:
    async def test_the_ticket_shows_what_to_whom_and_the_content(self, debiteur: int) -> None:
        ref = await _agent_vraagt_aan(debiteur)

        payload = await _ticket_payload(ref)

        assert payload["recipient_email"] == "administratie@dekorst.example"
        assert payload["subject"] == "Herinnering: factuur F-2026-042"
        assert "EUR 1250.50" in payload["body"] and payload["kind"] == "herinnering"

    async def test_rejecting_stops_the_action_and_is_logged(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)

        antwoord = await _beslis(
            integration_app, AANVRAGER, "reject", {"ticket_ref": ref, "reason": "klant belde net"}
        )

        assert antwoord.status_code == 200, antwoord.text
        assert await _berichten() == []
        beslissingen = await _beslissingen(ref)
        assert [b.action for b in beslissingen] == ["rejected"]
        assert beslissingen[0].timestamp is not None

    async def test_approving_creates_exactly_the_shown_message_and_is_logged(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        getoond = await _ticket_payload(ref)

        antwoord = await _beslis(integration_app, AANVRAGER, "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["executed"] is True, antwoord.json()
        assert [tuple(b) for b in await _berichten()] == [
            (getoond["recipient_email"], getoond["subject"], getoond["body"], ref)
        ]
        beslissingen = await _beslissingen(ref)
        assert [(b.action, b.user_id) for b in beslissingen] == [("approved", AANVRAGER)]
        assert beslissingen[0].timestamp is not None

    async def test_the_same_approval_never_sends_twice(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _beslis(integration_app, AANVRAGER, "approve", {"ticket_ref": ref})

        tweede = await _beslis(integration_app, AANVRAGER, "approve", {"ticket_ref": ref})

        assert tweede.status_code == 400
        assert len(await _berichten()) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestVierOgenAan:
    async def test_the_requester_cannot_approve_and_nothing_is_sent(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _zet_vier_ogen(True)
        ref = await _agent_vraagt_aan(debiteur)

        antwoord = await _beslis(integration_app, AANVRAGER, "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 403
        assert await _berichten() == []

    async def test_a_colleague_approves_and_exactly_the_shown_message_is_created(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _zet_vier_ogen(True)
        ref = await _agent_vraagt_aan(debiteur)
        getoond = await _ticket_payload(ref)

        antwoord = await _beslis(integration_app, COLLEGA, "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 200, antwoord.text
        assert [tuple(b) for b in await _berichten()] == [
            (getoond["recipient_email"], getoond["subject"], getoond["body"], ref)
        ]
        beslissingen = await _beslissingen(ref)
        assert [(b.action, b.user_id) for b in beslissingen] == [("approved", COLLEGA)]
