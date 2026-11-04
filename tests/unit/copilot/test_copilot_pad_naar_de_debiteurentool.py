"""Meting: komt de copilot via de debiteurentool bij een goedkeuringsticket? (dag 2, taak 6)

Aanleiding: de bouwer van de copilot-500-fix (`23cdc8e8`) meldde dat
`config/tool_permissions.yml` copilot-acties beschrijft als "uitgevoerd door de
copilot-actiehandlers", terwijl `_execute_decision` (`copilot/service.py`) ze altijd naar de
broker stuurt. De vraag voor dag 2: blokkeert DAT het pad copilot -> debiteurentool -> ticket?

Gemeten, met de ECHTE `HITLTicketRepository` (alleen de database-sessie is een dubbel) en de
echte `ToolPermissionManager`:

1. Het HITL-pad van `handle_turn` komt niet bij `_execute_decision`: die loopt alleen bij
   APPROVED. De bevinding over `_execute_decision` raakt dit pad dus NIET.
2. Wat het pad wel blokkeert, is de identiteit: de copilot maakt tickets aan met de
   standaardidentiteit `copilot`, en die mag `send_payment_reminder` niet uitvoeren
   (`create_hitl_request` weigert met PermissionError, ADR-036 OP-90). Dat is opzet: alleen de
   debiteurenagent (`dunning`) heeft die tool in zijn profiel.
3. Die PermissionError kwam ongevangen naar boven (in een HTTP-verzoek een 500). Sinds de brief
   `docs/agent-briefs/generated/2026-10-05-sprint-dag-copilot-weigering-zonder-500.md` vangt
   `handle_turn` hem en geeft verdict "blocked", met een tekst die naar de debiteurenagent
   verwijst. Het ticket komt van die agent, onder zijn eigen identiteit `dunning`.

Deze tests leggen de stand van vandaag vast. Wordt het pad later bewust geopend (de copilot
vraagt namens de debiteurenagent aan), dan horen ze mee te veranderen.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.types import DecisionVerdict

TOOL = "send_payment_reminder"


def _service(verdict: DecisionVerdict) -> tuple[Any, AsyncMock]:
    from src.core.copilot.proposal_builder import ProposalBuilder
    from src.core.copilot.schemas import CopilotAction
    from src.core.copilot.service import CopilotService
    from src.core.tool_broker.hitl_repository import HITLTicketRepository
    from tests.unit.copilot.test_service import _make_council_decision

    actie = CopilotAction(
        message="Ik stuur een herinnering",
        action=TOOL,
        action_params={"receivable_id": 1, "kind": "herinnering"},
        confidence=0.9,
        reasoning="factuur is te laat",
    )
    llm = MagicMock()
    llm.get_action = AsyncMock(return_value=actie)
    llm.model_id = "m"
    llm.model_version = "v1"
    council = MagicMock()
    council.deliberate = AsyncMock(return_value=_make_council_decision(verdict))
    broker = AsyncMock()
    service = CopilotService(
        council=council,
        llm_handler=llm,
        proposal_builder=ProposalBuilder(),
        hitl_repo=HITLTicketRepository(AsyncMock()),
        tool_broker=broker,
        audit_writer=None,
    )
    return service, broker


@pytest.mark.unit
class TestCopilotNaarDeDebiteurentool:
    def test_the_copilot_identity_may_not_send_a_reminder(self) -> None:
        from src.core.tool_broker.permission_manager import ToolPermissionManager

        assert ToolPermissionManager().is_tool_allowed("copilot", TOOL) is False

    async def test_a_hitl_verdict_never_reaches_execute_decision(self) -> None:
        service, broker = _service(DecisionVerdict.HITL_REQUIRED)

        response = await service.handle_turn(
            tenant_id=1, user_id=1, message="herinner", context={}
        )

        assert response.verdict == "blocked"
        assert response.hitl_request_id is None
        broker.execute_tool.assert_not_awaited()

    async def test_the_refusal_points_to_the_receivables_agent(self) -> None:
        service, _ = _service(DecisionVerdict.HITL_REQUIRED)

        response = await service.handle_turn(
            tenant_id=1, user_id=1, message="herinner", context={}
        )

        assert "debiteurenagent" in response.message

    async def test_the_receivables_agent_route_ends_in_a_ticket(self) -> None:
        """Route van scenario 5: de debiteurenagent vraagt aan onder zijn eigen identiteit."""
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        repo = HITLTicketRepository(AsyncMock())
        repo.create = AsyncMock()  # type: ignore[method-assign]

        ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=1,
            decision_id="d-1",
            reason="factuur is te laat",
            action_type=TOOL,
            action_params={"receivable_id": 1, "kind": "herinnering"},
            executing_identity="dunning",
        )

        assert ref
        repo.create.assert_awaited_once()
        assert repo.create.await_args.kwargs["tool_name"] == TOOL
