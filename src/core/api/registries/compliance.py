"""Compliance domain registry (ADR-033 Laag 2, max 80 regels).

Covers: governance (EU AI Act), gatekeeper (ADR-017), GDPR/compliance router.
"""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register governance, gatekeeper and compliance routers. Returns count."""
    count = 0

    # Governance -- EU AI Act REST API (ADR-031)
    from src.core.api.v1.governance.router import router as governance_v1_router

    app.include_router(governance_v1_router, tags=["governance"])
    count += 1

    # Gatekeeper -- deterministic policy enforcement (ADR-017)
    try:
        from src.core.api.v1.gatekeeper.router import router as gatekeeper_router

        app.include_router(gatekeeper_router, tags=["Gatekeeper"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Gatekeeper router: %s", e)

    # Council -- pending HITL decisions for the compliance dashboard (SP-ARCH-ARCH-2)
    try:
        from src.core.api.v1.council.router import router as council_router

        app.include_router(council_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping Council router: %s", e)

    # Compliance -- GDPR + compliance endpoints
    from src.core.api.v1.compliance.router import router as compliance_router

    app.include_router(compliance_router, prefix="/api/v1")
    count += 1

    # GDPR Compliance -- migrated to v1/gdpr_compliance/ (SP-API-005 Dag 1)
    try:
        from src.core.api.v1.gdpr_compliance import domain_router as gdpr_domain_router

        app.include_router(gdpr_domain_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping GDPR Compliance router: %s", e)

    logger.debug("compliance routers registered: %s", count)
    return count
