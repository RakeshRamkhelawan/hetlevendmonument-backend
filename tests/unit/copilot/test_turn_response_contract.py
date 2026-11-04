"""Contract guard: the /copilot/turn response must carry decision_id.

The frontend CopilotSidebar reads `decision_id` from the turn response to render
the AI Act art. 13 right-to-explanation link. This test locks the field into the
CopilotTurnResponse contract so a future refactor cannot silently drop it.

Context: AGENTIC-COPILOT-TAAKBEHEER Dag 5 -- sidebar on the real governance path.
"""

from src.core.copilot.schemas import CopilotTurnResponse


def test_turn_response_contract_includes_required_decision_id() -> None:
    fields = CopilotTurnResponse.model_fields
    assert "decision_id" in fields, "decision_id must be part of the turn-response contract"
    # Required (no default): every turn response carries a decision_id for right-to-explanation.
    assert fields["decision_id"].is_required(), "decision_id must be required, not optional"
