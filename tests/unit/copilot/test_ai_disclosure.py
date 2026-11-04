"""AI-disclosure (ADR-036 D9 / EU AI Act art. 50) op copilot-antwoorden.

Elk agent-gegenereerd antwoord uit het taak-pad moet een machine-leesbare
AI-disclosure dragen. Daarnaast borgt dit bestand dat de copilot/turn-laag
fail-secure is: bij een Council-infrastructuurfout wordt het antwoord geblokkeerd
(bestaand gedrag -- regressiebewaking).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.schemas import CopilotTurnResponse
from src.core.copilot.service import CopilotService


class TestAIDisclosureField:
    def test_turn_response_has_machine_readable_disclosure(self) -> None:
        """4.1 -- CopilotTurnResponse draagt een niet-lege, machine-leesbare AI-disclosure."""
        resp = CopilotTurnResponse(
            decision_id="dec-1",
            verdict="approved",
            message="Taak aangemaakt.",
        )
        assert resp.ai_disclosure, "ai_disclosure moet standaard aanwezig en niet-leeg zijn"
        assert "AI" in resp.ai_disclosure


class TestCopilotTurnFailSecure:
    @pytest.mark.asyncio
    async def test_handle_turn_blocks_on_council_error(self) -> None:
        """3.2 -- handle_turn blokkeert bij een Council-fout (fail-secure) en discloset AI."""
        council = MagicMock()
        council.deliberate = AsyncMock(side_effect=RuntimeError("council backend down"))

        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=MagicMock())
        llm_handler.model_id = "test-model"
        llm_handler.model_version = "1.0"

        proposal_builder = MagicMock()
        proposal_builder.build = MagicMock(return_value=MagicMock())

        service = CopilotService(
            council=council,
            llm_handler=llm_handler,
            proposal_builder=proposal_builder,
            redis=None,
        )

        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Verwijder taak X",
            context={},
        )

        assert response.verdict == "blocked"
        assert response.ai_disclosure
