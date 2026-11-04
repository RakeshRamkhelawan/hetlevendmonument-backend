from __future__ import annotations

from src.core.auth.auth_service import UserResponse
from src.core.copilot.api.schemas import (
    DecisionExplanationResponse,
    OfficerVerdictResponse,
)
from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow


def build_explanation(
    decision: CouncilDecisionRow,
    verdicts: list[OfficerVerdictRow],
    language: str | None,
    viewing_user: UserResponse,
) -> DecisionExplanationResponse:
    """Build a user-facing explanation for a CouncilDecision."""
    officer_responses = [
        OfficerVerdictResponse(
            officer_name=v.officer_name,
            officer_version=v.officer_version,
            verdict=v.verdict,
            confidence=v.confidence,
            reason_code=v.reason_code,
            reason_text=v.reason_text,
        )
        for v in verdicts
    ]

    can_contest = True
    contest_url = f"/api/v1/copilot/audit/{decision.decision_id}/contest"

    return DecisionExplanationResponse(
        decision_id=decision.decision_id,
        timestamp=decision.timestamp,
        verdict=decision.verdict,
        action_type=decision.action_type,
        explanation_for_user=decision.explanation_for_user,
        reasoning_summary=decision.reasoning,
        officer_verdicts=officer_responses,
        model_id=decision.model_id,
        model_version=decision.model_version,
        data_classification=decision.data_classification,
        can_contest=can_contest,
        contest_url=contest_url,
    )
