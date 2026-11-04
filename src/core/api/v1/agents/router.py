"""
Agents composite router (ADR-033 Laag 1 composite).

Assembles sub-routers in correct order (static paths before path-parameter routes).
Max 200 regels per ADR-033 Laag 1 constraint.
"""

from fastapi import APIRouter

from src.core.api.v1.agents.agent_management_router import router as management_router
from src.core.api.v1.agents.agent_execution_router import router as execution_router
from src.core.api.v1.agents.agent_crud_router import router as crud_router

# NOTE: Route declaration order matters for FastAPI path matching.
# Static paths (/register, /execute, /collaborate, /stats, /health, /catalog)
# must be registered BEFORE the catch-all /{agent_id} path-parameter route.
router = APIRouter(prefix="/agents")

# 1. Management routes (collaborate, stats, health, catalog) -- no path params
router.include_router(management_router)

# 2. Execution routes (execute, agent/execute/{id}) -- static prefix beats /{id}
router.include_router(execution_router)

# 3. CRUD routes (register, /, /{agent_id}, PATCH /{agent_id}) -- path param last
router.include_router(crud_router)
