"""Health check domain package (ADR-033 Laag 2, ADR-012 3-tier health).

GEEN prefix -- registries leggen prefix op (dual-registration):
  - analytics.py: registreerd zonder extra prefix (liveness/readiness op root)
  - agents.py: registreerd met prefix="/api/v1/agents" (diagnostics)
"""

from fastapi import APIRouter

from src.core.api.v1.health.router import router as health_composite_router

domain_router = APIRouter(tags=["Health"])
domain_router.include_router(health_composite_router)

__all__ = ["domain_router"]
