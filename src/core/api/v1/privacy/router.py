"""Privacy API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

from src.core.api.v1.privacy.dsar_router import collect_user_data, dsar_router  # noqa: F401
from src.core.api.v1.privacy.consent_router import consent_router
from src.core.api.v1.privacy.ai_transparency_router import ai_transparency_router
from src.core.api.v1.privacy.human_review_router import human_review_router

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])
router.include_router(dsar_router)
router.include_router(consent_router)
router.include_router(ai_transparency_router)
router.include_router(human_review_router)
