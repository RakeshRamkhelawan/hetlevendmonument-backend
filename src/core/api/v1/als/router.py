"""ALS API router composite (ADR-033 Laag 2)."""
# orphan:exempt reason: registered via importlib.import_module in registries/agentic.py (ADR-033)

from fastapi import APIRouter

from src.core.api.v1.als.als_tasks_router import als_tasks_router
from src.core.api.v1.als.als_health_router import als_health_router
from src.core.api.v1.als.als_agents_router import als_agents_router

from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

router = APIRouter(prefix="/als", tags=["als"])
router.include_router(als_tasks_router)
router.include_router(als_health_router)
router.include_router(als_agents_router)
