"""
SP-AGT-003 Dag 1 -- RED tests: AIContextEngine wiring in CopilotService.

These tests must FAIL before the fix (context_engine not yet a parameter of
CopilotService) and PASS after it (context_engine.enrich() wired in handle_turn).

Test taxonomy:
  1.1 -- happy path: context_engine parameter accepted by CopilotService.__init__
  1.2 -- happy path: context_engine.enrich() called during handle_turn
  1.3 -- happy path: EnrichedContext.context flows into LLM augmented_context
  1.4 -- unhappy path: context_engine.enrich() exception -> graceful degradation
  1.5 -- security: twin_service.get_profile() NOT called directly when context_engine present
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    OfficerVerdict,
    VerdictType,
)
from src.core.copilot.proposal_builder import ProposalBuilder
from src.core.copilot.schemas import CopilotAction
from src.core.copilot.service import CopilotService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_council(verdict: DecisionVerdict = DecisionVerdict.APPROVED) -> Any:
    from uuid import uuid4

    decision = CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=1,
        verdict=verdict,
        officer_verdicts=(
            OfficerVerdict(
                officer_name="ComplianceOfficer",
                officer_version="1.0.0",
                verdict=VerdictType.APPROVE,
                reason_code="OK",
                reason_text="OK",
                evidence={},
                deliberation_ms=100,
                confidence=1.0,
            ),
        ),
        explanation_for_user="OK",
        decision_hash="hash",
        previous_decision_hash=None,
        deliberation_ms=200,
    )
    council = MagicMock()
    council.deliberate = AsyncMock(return_value=decision)
    return council


def _make_llm_handler(action_message: str = "test response") -> Any:
    action = CopilotAction(
        message=action_message,
        action="none",
        action_params={},
        confidence=0.9,
        reasoning="test",
    )
    handler = MagicMock()
    handler.get_action = AsyncMock(return_value=action)
    handler.model_id = "deepseek-chat-v3.1"
    handler.model_version = "v3.1"
    return handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_copilot_service_accepts_context_engine_parameter() -> None:
    """CopilotService.__init__ moet context_engine parameter accepteren -- SP-AGT-003."""
    from src.core.agents.context_engine import AIContextEngine

    mock_db = AsyncMock()
    engine = AIContextEngine(db=mock_db, tenant_id=1)

    # Dit mag GEEN TypeError gooien na de fix.
    service = CopilotService(
        council=_make_council(),
        llm_handler=_make_llm_handler(),
        proposal_builder=ProposalBuilder(),
        context_engine=engine,
    )
    assert hasattr(service, "_context_engine"), (
        "CopilotService moet _context_engine opslaan na de fix (SP-AGT-003)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_turn_calls_context_engine_enrich() -> None:
    """handle_turn moet context_engine.enrich() aanroepen -- SP-AGT-003."""
    from src.core.agents.context_engine import EnrichedContext

    mock_engine = AsyncMock()
    mock_engine.enrich = AsyncMock(
        return_value=EnrichedContext(
            context={"memory_key": "memory_value"},
            twin_profile={"persona_name": "analyst"},
            surface="copilot",
            query="test",
        )
    )

    # Wanneer context_engine gewired is, moet handle_turn enrich() aanroepen.
    try:
        service = CopilotService(
            council=_make_council(),
            llm_handler=_make_llm_handler(),
            proposal_builder=ProposalBuilder(),
            context_engine=mock_engine,
        )
    except TypeError:
        pytest.fail("CopilotService accepteert context_engine nog niet. Fix __init__ eerst.")

    await service.handle_turn(
        tenant_id=1,
        user_id=1,
        message="wat zijn mijn taken?",
        context={"surface": "copilot"},
    )

    assert mock_engine.enrich.called, (
        "context_engine.enrich() werd NIET aangeroepen in handle_turn -- SP-AGT-003"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enriched_context_data_flows_into_llm_context() -> None:
    """EnrichedContext.context data moet in augmented_context terechtkomen voor LLM -- SP-AGT-003."""
    from src.core.agents.context_engine import EnrichedContext

    captured_context: dict[str, Any] = {}

    async def capture_get_action(
        message: str,
        context: dict[str, Any],
        **_kwargs: Any,
    ) -> CopilotAction:
        captured_context.update(context)
        return CopilotAction(
            message="ok",
            action="none",
            action_params={},
            confidence=0.9,
            reasoning="test",
        )

    llm_handler = MagicMock()
    llm_handler.get_action = capture_get_action
    llm_handler.model_id = "deepseek-chat-v3.1"
    llm_handler.model_version = "v3.1"

    mock_engine = AsyncMock()
    mock_engine.enrich = AsyncMock(
        return_value=EnrichedContext(
            context={"sp_agt_003_marker": "enriched_data_present"},
            twin_profile={"persona_name": "analyst"},
        )
    )

    try:
        service = CopilotService(
            council=_make_council(),
            llm_handler=llm_handler,
            proposal_builder=ProposalBuilder(),
            context_engine=mock_engine,
        )
    except TypeError:
        pytest.fail("CopilotService accepteert context_engine nog niet.")

    await service.handle_turn(
        tenant_id=1,
        user_id=1,
        message="test",
        context={},
    )

    assert "sp_agt_003_marker" in captured_context, (
        "EnrichedContext.context ('sp_agt_003_marker') bereikte de LLM niet -- SP-AGT-003"
    )
    assert captured_context.get("twin_profile", {}).get("persona_name") == "analyst", (
        "EnrichedContext.twin_profile bereikte de LLM niet -- SP-AGT-003"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_turn_graceful_when_context_engine_raises() -> None:
    """Wanneer context_engine.enrich() faalt, mag handle_turn NIET crashen -- SP-AGT-003."""
    mock_engine = AsyncMock()
    mock_engine.enrich = AsyncMock(side_effect=RuntimeError("ContextPacker DB timeout"))

    try:
        service = CopilotService(
            council=_make_council(),
            llm_handler=_make_llm_handler(),
            proposal_builder=ProposalBuilder(),
            context_engine=mock_engine,
        )
    except TypeError:
        pytest.fail("CopilotService accepteert context_engine nog niet.")

    response = await service.handle_turn(
        tenant_id=1,
        user_id=1,
        message="test",
        context={},
    )

    # Service degradeert gracefully -- response mag niet None zijn
    assert response is not None, (
        "handle_turn retourneerde None na context_engine fout -- SP-AGT-003"
    )
    # En er mag geen 500-achtige exception omhoog gaan
    assert hasattr(response, "verdict"), (
        "Response heeft geen verdict-veld -- SP-AGT-003 graceful fallback werkt niet"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_twin_service_not_called_directly_when_context_engine_present() -> None:
    """twin_service.get_profile() mag NIET direct aangeroepen worden als context_engine aanwezig is."""
    from src.core.agents.context_engine import EnrichedContext

    mock_twin_service = AsyncMock()
    mock_twin_service.get_profile = AsyncMock(return_value={"persona_name": "direct"})

    mock_engine = AsyncMock()
    mock_engine.enrich = AsyncMock(
        return_value=EnrichedContext(twin_profile={"persona_name": "via_engine"})
    )

    try:
        service = CopilotService(
            council=_make_council(),
            llm_handler=_make_llm_handler(),
            proposal_builder=ProposalBuilder(),
            twin_service=mock_twin_service,
            context_engine=mock_engine,
        )
    except TypeError:
        pytest.fail("CopilotService accepteert context_engine nog niet.")

    await service.handle_turn(
        tenant_id=1,
        user_id=1,
        message="test",
        context={},
    )

    assert not mock_twin_service.get_profile.called, (
        "twin_service.get_profile() werd direct aangeroepen terwijl context_engine aanwezig is -- "
        "SP-AGT-003: context_engine is de primaire enrichment-route"
    )
