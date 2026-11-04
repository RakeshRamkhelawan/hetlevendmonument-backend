# orphan:exempt reason: dead code, not registered in any registry (SP-API-008 cutover)
# All routes migrated to v1/<domein>/ or permanently removed.
# Compatibility shim for legacy imports.

import logging
import os

from fastapi import HTTPException

from src.core.api.v1.company.goal_router import router  # noqa: F401

logger = logging.getLogger(__name__)

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_INMEMORY_ENABLED = os.getenv("ENABLE_INMEMORY_GOALS", "").lower() in (
    "1",
    "true",
    "yes",
)

if _ENVIRONMENT != "production":
    logger.warning(
        "goal_endpoints: using in-memory storage (MVP). "
        "Data verloren bij restart. Migreer naar database voor productie. "
        "Zet ENABLE_INMEMORY_GOALS=true om dit in production te forceren (NIET AANBEVOLEN)."
    )

if _ENVIRONMENT == "production" and _INMEMORY_ENABLED:
    logger.critical(
        "KRITIEKE WAARSCHUWING: goal_endpoints draait in PRODUCTIE met in-memory storage! "
        "ENABLE_INMEMORY_GOALS=true is gezet in een productieomgeving. "
        "Data gaat verloren bij iedere container restart."
    )


def _check_production_guard() -> None:
    """Check if in-memory storage is allowed in current environment."""
    if _ENVIRONMENT == "production" and not _INMEMORY_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Goal storage is niet geconfigureerd voor productie.",
        )
