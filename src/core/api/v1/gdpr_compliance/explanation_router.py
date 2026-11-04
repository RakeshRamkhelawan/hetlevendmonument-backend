# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""EU AI Act Art. 13/86 -- AI Decision Explainability endpoint.

Routes:
  GET /api/gdpr/decisions/{decision_id}/explanation
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import AIDecision, get_current_tenant_id, get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])


@router.get(
    "/decisions/{decision_id}/explanation",
    summary="Get AI Decision Explanation (EU AI Act Art. 13/86)",
    description=(
        "Returns the explanation for a specific AI decision, including the decision type, "
        "confidence score, and human-readable rationale. "
        "EU AI Act Art. 13/86: transparency and explainability for automated decisions."
    ),
)
async def get_decision_explanation(
    decision_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return explanation for an AI decision (EU AI Act Art. 13 / AUDIT-EU-AI-007)."""
    # AIDecision.tenant_id is Mapped[int]; tenant_id from JWT is str -- cast explicitly
    try:
        tenant_id_int = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid tenant context")

    result = await db.execute(
        select(AIDecision).where(
            AIDecision.id == decision_id,
            AIDecision.tenant_id == tenant_id_int,
        )
    )
    decision = result.scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="AI decision not found")

    # Intra-tenant ownership check: only the decision's owner may retrieve it
    current_user_id = str(getattr(current_user, "id", ""))
    if decision.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="AI decision not found")

    logger.info(
        "AI decision explanation accessed by user %s for decision %s",
        getattr(current_user, "id", "unknown"),
        decision_id,
    )

    return {
        "success": True,
        "data": {
            "decision_id": decision.id,
            "decision_type": decision.decision_type,
            "agent_id": decision.agent_id,
            "explanation": decision.explanation,
            "confidence_score": decision.confidence_score,
            "profiling_involved": decision.profiling_involved,
            "human_review_available": decision.human_review_available,
            "human_review_requested": decision.human_review_requested,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
            "eu_ai_act": {
                "article": "Art. 13/86",
                "disclosure": "This decision was made by an AI system.",
            },
        },
    }
