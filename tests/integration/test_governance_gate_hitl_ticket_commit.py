"""Integration test: het HITL-ticket dat require_council_approval()/execute_flow()
aanmaken moet de daaropvolgende 403 OVERLEVEN (ADR-036 OP-167-vervolg, dag 4).

Gevonden door de BE-AGT-064-feature-doc-reviewer, empirisch bevestigd voor commit
(zie de final-approver-brief): `HITLTicketRepository.create()` doet zelf alleen
`add()` + `flush()`, nooit `commit()`. `governance_gate.py::require_council_approval`
en `execution_router.py::execute_flow` raisen meteen daarna een `HTTPException(403)`
op DEZELFDE `Depends(get_db)`-sessie. FastAPI laat die exception door de generator van
`database.py::get_db()` propageren, en die vangt ELKE exception met
`await session.rollback()` -- wat het net geflushte ticket ONGEDAAN maakt voordat het
ooit op schijf staat. De `hitl_request_id` in de 403-body verwees dus naar een ticket
dat nooit had bestaan.

Draait tegen de echte testdatabase (poort 5455, via tests/integration/conftest.py).
Simuleert `get_db()`'s except-rollback-tak RECHTSTREEKS op dezelfde sessie in plaats
van de volledige FastAPI-dependency-laag op te tuigen -- dat is precies het mechanisme
van de bug, en de kortste weg om het te bewijzen.

Gebruikt `action_type="create_task"` (een ECHT geregistreerde tool, en de identiteit
"copilot" mag hem uitvoeren -- zie hitl_repository.py's docstring) om deze test los te
koppelen van de aparte, nog openstaande vraag of de HTTP-domeinlabels (cva.chat,
agent.execute, etc.) ooit een eigen registratie krijgen. Deze test bewijst alleen dat
EEN SUCCESVOLLE ticketaanmaak de daaropvolgende rollback overleeft, onafhankelijk van
welke namen ooit als bekend geregistreerd worden.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.council.governance_gate import require_council_approval
from src.core.copilot.council.types import CouncilDecision, DecisionVerdict

pytestmark = pytest.mark.asyncio

SEEDED_ADMIN_ID = 1


def _hitl_required_decision(tenant_id: int) -> CouncilDecision:
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=tenant_id,
        user_id=SEEDED_ADMIN_ID,
        verdict=DecisionVerdict.HITL_REQUIRED,
        officer_verdicts=(),
        explanation_for_user="test: menselijke goedkeuring vereist",
        decision_hash="deadbeef",
        previous_decision_hash=None,
        deliberation_ms=1,
    )


@pytest.fixture(autouse=True)
async def clear_hitl_tickets(db_session: AsyncSession):
    await db_session.execute(text("DELETE FROM hitl_tickets;"))
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM hitl_tickets;"))
    await db_session.commit()


class TestTheTicketSurvivesTheFollowingRollback:
    async def test_governance_gate_ticket_is_still_in_the_db_after_the_403_rolls_back(
        self, db_session: AsyncSession, test_tenant_id: int
    ) -> None:
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(return_value=_hitl_required_decision(test_tenant_id))

        with pytest.raises(HTTPException) as exc_info:
            await require_council_approval(
                council=fake_council,
                tenant_id=test_tenant_id,
                user_id=SEEDED_ADMIN_ID,
                action_type="create_task",
                action_params={"title": "test"},
                reasoning="integration test",
                db=db_session,
            )
        ticket_ref = exc_info.value.detail["hitl_request_id"]
        assert ticket_ref is not None, (
            "create_task is een bekende, toegestane tool -- de aanmaak had moeten "
            "slagen, geen None-terugval."
        )

        # Simuleert database.py::get_db()'s `except Exception: await session.rollback()`
        # op DEZELFDE sessie -- exact wat FastAPI doet zodra deze HTTPException door de
        # Depends(get_db)-generator propageert.
        await db_session.rollback()

        row = await db_session.execute(
            text("SELECT status FROM hitl_tickets WHERE ticket_ref = :ref"),
            {"ref": ticket_ref},
        )
        assert row.scalar_one_or_none() == "pending", (
            "Het ticket verdween na de rollback die op de 403 volgt -- de "
            "hitl_request_id in de foutrespons verwijst dan naar een ticket dat "
            "nooit heeft bestaan (ADR-036 OP-167-vervolg, dag 4)."
        )
