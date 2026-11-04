# orphan:exempt reason: sub-router samengesteld door routing/router.py (ADR-033 Laag 1)
"""Routing API -- statistics and health endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth.api_deps import UserResponse, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["routing"])


@router.get("/stats")
async def get_routing_stats(
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get GunaRouter statistics.

    Shows distribution of routing across the Three Guna layers.
    """
    try:
        from src.main import app

        guna_router = getattr(app.state, "guna_router", None)

        if not guna_router:
            raise HTTPException(status_code=503, detail="GunaRouter not initialized")

        stats = guna_router.get_stats()

        return {
            "statistics": stats,
            "guna_distribution": {
                "tamasic": f"{stats.get('tamasic_percentage', 0):.1f}%",
                "rajasic": f"{stats.get('rajasic_percentage', 0):.1f}%",
                "sattvic": f"{stats.get('sattvic_percentage', 0):.1f}%",
                "fallback": f"{stats.get('fallback_percentage', 0):.1f}%",
            },
            "prana_costs": guna_router.PRANA_COSTS,
        }

    except Exception as e:
        logger.error("get routing stats failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/health")
async def routing_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Check routing system health.
    """
    try:
        from src.main import app

        guna_router = getattr(app.state, "guna_router", None)

        health = {
            "guna_router_initialized": guna_router is not None,
            "tamasic_layer": "available",
            "rajasic_layer": "unknown",
            "sattvic_layer": "not_implemented",
        }

        if guna_router:
            embedder_health = await guna_router.rajasic.embedder.health_check()
            health["rajasic_layer"] = "healthy" if embedder_health else "unhealthy"
            health["ollama_model"] = guna_router.rajasic.embedder.model

        return health

    except Exception as e:
        logger.error("routing health check failed: %s: %s", type(e).__name__, e, exc_info=True)
        return {
            "status": "error",
            "message": "Internal error",
        }
