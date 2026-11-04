"""Digital Twin router -- AUDIT-DB14b ADR-033 compliant (geen directe DB-imports)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.api.v1.digital_twin.dependencies import get_digital_twin_service
from src.core.api.v1.digital_twin.service import ConsentSettings, DigitalTwinService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digital-twin", tags=["digital-twin"])


@router.post("/agents/{agent_id}/consent")
async def update_consent(
    agent_id: int,
    consent: ConsentSettings,
    svc: DigitalTwinService = Depends(get_digital_twin_service),
) -> dict[str, object]:
    try:
        event = await svc.update_consent(agent_id=agent_id, consent=consent)
    except ValueError as exc:
        logger.warning("update_consent afgewezen: %s", exc)
        raise HTTPException(status_code=404, detail="Agent niet gevonden") from exc
    return {
        "success": True,
        "data": {
            "agent_id": event.agent_id,
            "tenant_id": event.tenant_id,
            "observe": event.observe,
        },
    }


@router.get("/agents/{agent_id}/state")
async def get_twin_state(
    agent_id: int,
    svc: DigitalTwinService = Depends(get_digital_twin_service),
) -> dict[str, object]:
    try:
        result = await svc.get_twin_state(agent_id=agent_id)
    except ValueError as exc:
        logger.warning("get_twin_state afgewezen: %s", exc)
        raise HTTPException(status_code=404, detail="Agent niet gevonden") from exc
    return {"success": True, "data": result}


@router.get("/agents/{agent_id}/consent-history")
async def get_consent_history(
    agent_id: int,
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    svc: DigitalTwinService = Depends(get_digital_twin_service),
) -> dict[str, object]:
    history = await svc.get_consent_history(agent_id=agent_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": [
            {
                "agent_id": e.agent_id,
                "tenant_id": e.tenant_id,
                "observe": e.observe,
                "created_at": str(e.created_at),
            }
            for e in history
        ],
    }


@router.get("/health")
async def digital_twin_health() -> dict[str, object]:
    return {"success": True, "data": {"status": "ok"}}
