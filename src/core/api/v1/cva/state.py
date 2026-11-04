"""CVA module-level agent cache -- gedeelde staat voor alle sub-routers (ADR-033)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from src.core.api.v1.cva.dependencies import UltimateCVAAgent  # own-domain -- ADR-033

logger = logging.getLogger(__name__)

_cva_agents: dict[int, "UltimateCVAAgent"] = {}


async def get_cva_agent(tenant_id: int = 0) -> "UltimateCVAAgent":
    """Get or create CVA agent instance met per-tenant caching."""
    from src.core.api.v1.cva.dependencies import create_cva_agent_factory  # own-domain -- ADR-033

    if tenant_id not in _cva_agents:
        try:
            _cva_agents[tenant_id] = await create_cva_agent_factory()
        except Exception as e:
            logger.exception("Failed to create CVA agent: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CVA agent is not available. Please check LLM configuration.",
            )
    return _cva_agents[tenant_id]
