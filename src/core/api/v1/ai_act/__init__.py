"""AI Act API endpoints for EU AI Act compliance."""

from __future__ import annotations

from src.core.api.v1.ai_act.incident_router import router as incident_router

__all__ = ["incident_router"]
