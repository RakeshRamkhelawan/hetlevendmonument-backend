"""Router Registry -- thin Laag 3 orchestrator (ADR-033, ~80 regels).

All domain routers are registered via Laag 2 registry files under
src/core/api/registries/. Each registry file is <= 80 lines with lazy
imports inside the register() function body.

Dead code removed in SP-API-001 Dag 5. Optional + Scheduling registries
extracted in SP-API-002 Dag 2.
"""

from fastapi import FastAPI
from loguru import logger

from src.core.api.registries import (
    agentic,
    agents,
    analytics,
    auth_admin,
    bonnen,
    company,
    compliance,
    copilot,
    core_api,
    foundation,  # NEW: ADR-029 Foundation Portal
    hr,
    integrations,
    noodstop,
    optional,
    packs,
    payables,
    realtime,
    receivables,
    scheduling,
    tenants,
    workflows,
)


def register_all_routers(app: FastAPI) -> int:
    """Register all API routers. Returns total count."""
    logger.info("Starting router registration...")
    total: int = 0

    total += auth_admin.register(app)
    total += tenants.register(app)
    total += agents.register(app)
    total += agentic.register(app)
    total += workflows.register(app)
    total += core_api.register(app)
    total += company.register(app)
    total += integrations.register(app)
    total += analytics.register(app)
    total += optional.register(app)
    total += scheduling.register(app)
    total += compliance.register(app)
    total += foundation.register(app)  # NEW: ADR-029 Foundation Portal
    total += copilot.register(app)
    total += realtime.register(app)
    total += hr.register(app)
    total += packs.register(app)
    total += noodstop.register(app)
    total += receivables.register(app)
    total += bonnen.register(app)
    total += payables.register(app)

    logger.info("api.routers_registered total=%d", total)
    return total


def _register_governance_v1(app: FastAPI) -> int:
    """Backward-compat shim: register only the governance v1 router.

    Previously a top-level function in router_registry.py; now delegated to
    the compliance registry. Kept for tests that import this function directly.
    """
    from src.core.api.v1.governance.router import router as governance_v1_router

    app.include_router(governance_v1_router, tags=["governance"])
    return 1
