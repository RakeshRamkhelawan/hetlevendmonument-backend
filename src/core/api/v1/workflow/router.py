# orphan:exempt reason: Laag 2 composite router, included via registries/workflows.py (ADR-033)
"""
Workflow domain composite router (SP-API-003, ADR-033 Laag 2).

Aggregates all workflow sub-routers into a single composite.
Each sub-router retains its own prefix (e.g. /api/v1/workflows, /api/v1/vibe, /api/v1/builder).
"""

from fastapi import APIRouter

from src.core.api.v1.workflow.workflow_crud_router import router as crud_router
from src.core.api.v1.workflow.workflow_execution_core_router import router as execution_core_router
from src.core.api.v1.workflow.workflow_execution_cancel_router import (
    router as execution_cancel_router,
)
from src.core.api.v1.workflow.workflow_suggestions_router import router as suggestions_router
from src.core.api.v1.workflow.workflow_builder_router import router as builder_router
from src.core.api.v1.workflow.workflow_versioning_router import router as versioning_router
from src.core.api.v1.workflow.workflow_generation_router import router as generation_router
from src.core.api.v1.workflow.workflow_execution_ap_router import router as execution_ap_router
from src.core.api.v1.workflow.workflow_refinement_router import router as refinement_router
from src.core.api.v1.workflow.workflow_feedback_router import router as feedback_router
from src.core.api.v1.workflow.workflow_visualization_router import router as visualization_router

router = APIRouter()

# NOTE: Each sub-router has its own prefix -- do not add a prefix here.
# SP-API-003 Dag 2: execution_router split into core (execute/status/list) + cancel sub-routers.
# NOTE: execution_core_router MUST come before crud_router so that static routes
# like GET /executions are registered before the parameterised GET /{workflow_id} catch-all.
router.include_router(execution_core_router)
router.include_router(crud_router)
router.include_router(execution_cancel_router)
router.include_router(suggestions_router)
router.include_router(builder_router)
router.include_router(versioning_router)
router.include_router(generation_router)
router.include_router(execution_ap_router)
router.include_router(refinement_router)
router.include_router(feedback_router)
router.include_router(visualization_router)
