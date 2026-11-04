"""
Compliance API router composite (ADR-033 Laag 2).

Provides:
- GET /api/v1/compliance/score
- GET /api/v1/compliance/score/history
- GET /api/v1/compliance/report/gdpr/summary
- GET /api/v1/compliance/report/gdpr/dsar
- GET /api/v1/compliance/report/ai-act/summary
- GET /api/v1/compliance/report/ai-act/decisions
- GET /api/v1/compliance/integrity/verify
- GET /api/v1/compliance/integrity/status
- POST /api/v1/compliance/integrity/verify-entry
- GET /api/v1/compliance/report/pdf
"""

from fastapi import APIRouter

from src.core.auth.api_deps import get_current_user  # noqa: F401
from .dependencies import (  # noqa: F401
    ComplianceAggregationService,
    ComplianceScoreCalculator,
    HashChainVerifier,
)
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

from src.core.api.v1.compliance.ai_act_decisions_router import ai_act_decisions_router
from src.core.api.v1.compliance.ai_act_summary_router import ai_act_summary_router
from src.core.api.v1.compliance.gdpr_dsar_router import gdpr_dsar_router
from src.core.api.v1.compliance.gdpr_summary_router import gdpr_summary_router
from src.core.api.v1.compliance.integrity_status_router import integrity_status_router
from src.core.api.v1.compliance.integrity_verify_router import integrity_verify_router
from src.core.api.v1.compliance.pdf_router import pdf_router
from src.core.api.v1.compliance.score_router import score_router

router = APIRouter(prefix="/compliance", tags=["Compliance"])

router.include_router(score_router)
router.include_router(gdpr_summary_router)
router.include_router(gdpr_dsar_router)
router.include_router(ai_act_summary_router)
router.include_router(ai_act_decisions_router)
router.include_router(integrity_verify_router)
router.include_router(integrity_status_router)
router.include_router(pdf_router)
