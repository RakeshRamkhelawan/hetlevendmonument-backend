"""GDPR Compliance composite router (ADR-033 Laag 1).

Assembles all GDPR sub-routers. The prefix /api/gdpr lives on each
sub-router so domain_router in __init__.py carries NO prefix.

Sub-routers:
  portability_router  -- POST /export, GET /export/download/{export_id}
  erasure_router      -- POST /delete-all
  access_router       -- GET  /audit-trail
  utility_router      -- GET  /status, GET /checklist, PUT /checklist/{id}
  explanation_router  -- GET  /decisions/{decision_id}/explanation (EU AI Act Art. 13/86)
"""

from fastapi import APIRouter

from .access_router import router as access_router
from .erasure_router import router as erasure_router
from .explanation_router import router as explanation_router
from .portability_router import router as portability_router
from .utility_router import router as utility_router
from .wissing_planning_router import router as wissing_planning_router

router = APIRouter()
router.include_router(portability_router)
router.include_router(erasure_router)
router.include_router(wissing_planning_router)
router.include_router(access_router)
router.include_router(utility_router)
router.include_router(explanation_router)
