"""Orchestration API router composite (ADR-033 Laag 2)."""
# orphan:exempt reason: registered via importlib.import_module in registries/agentic.py (ADR-033)

from fastapi import APIRouter

from src.core.api.v1.orchestration.workflow_router import workflow_router
from src.core.api.v1.orchestration.critic_router import critic_router
from src.core.api.v1.orchestration.health_router import health_router
from src.core.api.v1.orchestration.stats_router import stats_router

router = APIRouter(prefix="/orchestrate", tags=["Orchestration"])
router.include_router(workflow_router)
router.include_router(critic_router)
router.include_router(health_router)
router.include_router(stats_router)
