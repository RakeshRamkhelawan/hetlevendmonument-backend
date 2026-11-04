"""Council router -- pending decisions for the compliance dashboard (ADR-033).

SP-ARCH-ARCH-2 / ARCH-004: useCouncilDecisions.ts expects agent_id/risk_level/
timeout_at/description, but src.core.copilot.council's CouncilDecisionRow
records user-triggered proposals with no agent_id or timeout concept (verified
during implementation -- council decisions are proposal-centric, not agent-
centric). The gatekeeper's hitl_requests table (already reachable, already
tenant-isolated, and extended with agent_id in SP-GOV-ARCH-7) is the closest
real match for "pending items awaiting a human decision" -- this endpoint
surfaces those rather than inventing agent/risk/timeout data that doesn't
exist on the council-decision domain.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends, Query

from src.core.api.v1.council.dependencies import GatekeeperRepository, get_council_repository
from src.core.api.v1.council.schemas import CouncilDecisionListResponse, CouncilDecisionResponse

logger = logging.getLogger("council_api")

router = APIRouter(prefix="/api/v1/council", tags=["Council"])

# Matches the established HITL SLA window (src/core/tool_broker/hitl_repository.py::_SLA_HOURS)
_SLA_HOURS = 4

_CRITICAL_MARKERS = ("CRITICAL",)
_HIGH_MARKERS = ("HIGH",)
_MEDIUM_MARKERS = ("MEDIUM", "PII")


def _derive_risk_level(risk_factors: list[str]) -> str:
    """Best-effort risk_level from risk_factors -- no dedicated column exists yet."""
    upper_factors = [f.upper() for f in risk_factors]
    if any(marker in factor for factor in upper_factors for marker in _CRITICAL_MARKERS):
        return "critical"
    if any(marker in factor for factor in upper_factors for marker in _HIGH_MARKERS):
        return "high"
    if any(marker in factor for factor in upper_factors for marker in _MEDIUM_MARKERS):
        return "medium"
    return "low"


@router.get("/decisions", response_model=CouncilDecisionListResponse)
async def list_council_decisions(
    status: str = "pending",
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: GatekeeperRepository = Depends(get_council_repository),
) -> CouncilDecisionListResponse:
    """List pending HITL decisions for the compliance dashboard."""
    if status != "pending":
        raise HTTPException(status_code=400, detail="Only status=pending is supported")

    tickets = await repo.list_pending_hitl_requests(limit=limit, offset=offset)

    decisions = [
        CouncilDecisionResponse(
            id=hitl.ticket_ref,
            agent_id=hitl.agent_id or "system",
            risk_level=_derive_risk_level(hitl.risk_factors),
            timeout_at=(hitl.requested_at + timedelta(hours=_SLA_HOURS)).isoformat(),
            description=hitl.reason,
        )
        for hitl in tickets
    ]
    return CouncilDecisionListResponse(decisions=decisions)
