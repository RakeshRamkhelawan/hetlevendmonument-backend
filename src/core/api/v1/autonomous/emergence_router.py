"""Emergent Intelligence sub-router (ADR-033 Laag 1)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user

from src.core.auth.api_deps import UserResponse, require_scopes, OAuth2Scope
from src.core.api.autonomous_endpoints import EmergenceFacilitationRequest
from src.core.emergence.emergent_intelligence import get_emergent_intelligence

logger = logging.getLogger(__name__)

emergence_router = APIRouter(prefix="/api/v1/autonomous")


@emergence_router.post("/emergence/facilitate")
async def facilitate_emergence(
    request: EmergenceFacilitationRequest,
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Facilitate emergent intelligence behaviors. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): faciliteert emergent
    gedrag tussen agents zonder ooit GovernanceContract.is_action_permitted()
    aan te roepen. Zelfde onderliggende oorzaak als D12.5, ontdekt tijdens de
    Gate 2-doc-review van die fix.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Emergent intelligence facilitation is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )


@emergence_router.get("/emergence/behaviors")
async def get_emergent_behaviors(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detected emergent behaviors. Requires: AGENTS_READ"""
    try:
        emergence_system = get_emergent_intelligence()
        behaviors = await emergence_system.get_detected_behaviors()
        return {
            "detected_behaviors": [
                {
                    "behavior_id": behavior.behavior_id,
                    "type": behavior.emergence_type.value,
                    "participants": behavior.participants,
                    "intelligence_level": behavior.intelligence_level.value,
                    "emergence_strength": behavior.emergence_strength,
                    "stability": behavior.stability_score,
                    "outcomes": behavior.observed_outcomes,
                    "discovered_at": behavior.emergence_timestamp.isoformat(),
                }
                for behavior in behaviors
            ],
            "count": len(behaviors),
        }
    except Exception as e:
        logger.error("Failed to get emergent behaviors: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@emergence_router.get("/emergence/intelligence-levels")
async def get_intelligence_analysis(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get system-wide intelligence level analysis. Requires: AGENTS_READ"""
    try:
        emergence_system = get_emergent_intelligence()
        analysis = await emergence_system.analyze_collective_intelligence()
        return {
            "collective_intelligence_level": analysis.get("collective_level", 0),
            "individual_levels": analysis.get("individual_levels", {}),
            "emerging_capabilities": analysis.get("new_capabilities", []),
            "intelligence_trends": analysis.get("trends", []),
            "complexity_metrics": analysis.get("complexity", {}),
            "adaptation_rate": analysis.get("adaptation_rate", 0.0),
            "innovation_potential": analysis.get("innovation_score", 0.0),
        }
    except Exception as e:
        logger.error(
            "Failed to analyze intelligence levels: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal error") from e
