"""ProposalBuilder attaches the EU AI Act art. 50 disclosure to every proposal.

Sprint dag-9 F2 (Fix B): a copilot-proposed action is always AI-generated, so the
Proposal must carry action_params["ai_disclosure"]. Without it the Council's
ComplianceOfficer returns APPROVE_WITH_MODIFICATION (MISSING_AI_DISCLOSURE) and the
action never reaches APPROVED -- so no task is ever created via the copilot loop.
"""

from __future__ import annotations

import pytest

from src.core.copilot.council.types import Proposal, ProposalTrigger
from src.core.copilot.proposal_builder import ProposalBuilder
from src.core.copilot.schemas import AI_DISCLOSURE_NOTICE, CopilotAction


def _action(action_params: dict[str, object]) -> CopilotAction:
    return CopilotAction(
        message="ok",
        action="create_task",
        action_params=action_params,
        confidence=0.9,
        reasoning="test",
    )


def _build(action: CopilotAction) -> Proposal:
    return ProposalBuilder().build(
        tenant_id=1,
        user_id=2,
        action=action,
        trigger=ProposalTrigger.USER_REQUEST,
        model_id="m",
        model_version="v",
        context_snapshot={},
    )


@pytest.mark.unit
def test_build_sets_ai_disclosure_when_absent() -> None:
    """A proposal without an explicit ai_disclosure gets the canonical notice."""
    proposal = _build(_action({"title": "Q3 deck"}))
    assert proposal.action_params["ai_disclosure"] == AI_DISCLOSURE_NOTICE


@pytest.mark.unit
def test_build_respects_explicit_ai_disclosure() -> None:
    """An explicit ai_disclosure value is not overwritten."""
    proposal = _build(_action({"title": "Q3 deck", "ai_disclosure": "custom notice"}))
    assert proposal.action_params["ai_disclosure"] == "custom notice"
