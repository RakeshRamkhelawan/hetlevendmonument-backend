"""
Agent analytics endpoints.

GET /analytics/agents/{agent_id}/ooda -- agent OODA metrics (stub, SP-C02-B).
Per ADR-032 WE-011 fix: frontend calls /analytics/agents/{id}/ooda.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth.api_deps import get_current_user
from src.core.middleware.tenant_context import require_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics/agents", tags=["Analytics"])


@router.get("/{agent_id}/ooda")
async def get_agent_ooda_metrics(
    agent_id: str,
    tenant_id: int = Depends(require_tenant_id),
    current_user: object = Depends(get_current_user),
) -> dict[str, object]:
    """Agent OODA-loop metrics endpoint.

    TODO(SP-C02-B): implement real OODA metrics aggregation per ADR-032.
    """
    logger.info(
        "agent_ooda_metrics_requested",
        extra={"agent_id": agent_id, "tenant_id": tenant_id},
    )
    raise HTTPException(
        status_code=501,
        detail={
            "success": False,
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": "Agent OODA metrics are planned for SP-C02-B.",
            },
        },
    )
