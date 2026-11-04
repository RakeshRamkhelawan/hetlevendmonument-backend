"""Onboarding API Router - 3-step wizard for company creation.

Provides endpoints for:
- Step 1: Get recommended templates (filtered by company type/sector)
- Step 2: AI-powered template matching (keyword-based)
- Step 3: Complete onboarding (create company with template)

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md S.7.5
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md S.4.6
UIUX: docs/UIUX_PAPERCLIP_INTEGRATION.md S.3.1
"""

from __future__ import annotations

import re
import uuid
from typing import Any, List, Optional, Tuple, Type, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db, require_authenticated_user
from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.company.schemas import (
    CompanyResponse,
    OnboardingAIMatchRequest,
    OnboardingAIMatchResponse,
    OnboardingCompleteRequest,
    TemplateInstantiateRequest,
    TemplateListResponse,
    TemplateResponse,
)
from src.core.company.template_service import TemplateService
from src.core.api.v1.company.dependencies import DatabaseManager
from src.core.exceptions.exceptions import NotFoundError, ValidationError

router = APIRouter(
    prefix="/onboarding",
    tags=["onboarding"],
    dependencies=[Depends(require_company_layer_enabled)],
)


class SimpleTenantContext:
    """Simple tenant context for TemplateService."""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id


def get_template_service(
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # TODO(TYPE): replace Any with concrete type
) -> TemplateService:
    """Dependency to get TemplateService instance."""
    tenant_id = current_user.get("tenant_id", 1)
    tenant_context = SimpleTenantContext(tenant_id)

    class SimpleDBManager:
        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        def get_session(self) -> Any:  # TODO(TYPE): replace Any with concrete type
            class SessionContext:
                def __init__(self, session: AsyncSession) -> None:
                    self.session = session

                async def __aenter__(self) -> AsyncSession:
                    return self.session

                async def __aexit__(self, *args: Any) -> bool | None:
                    return False

            return SessionContext(self._session)

    # Cast SimpleDBManager to DatabaseManager for type compatibility
    # SimpleDBManager provides the same get_session() interface
    db_manager = cast(DatabaseManager, SimpleDBManager(db))
    return TemplateService(db_manager, tenant_context)


# Keyword matching patterns for AI template matching
KEYWORD_PATTERNS: dict[str, list[str]] = {
    "tech_startup": [
        "tech",
        "startup",
        "software",
        "app",
        "ai",
        "machine learning",
        "development",
        "code",
        "programming",
        "saas",
        "platform",
        "technologie",
        "software ontwikkeling",
        "applicatie",
    ],
    "freelance_consultant": [
        "consultant",
        "advisor",
        "adviseur",
        "consultancy",
        "freelance",
        "zzp",
        "zelfstandige",
        "project",
        "projecten",
        "freelancer",
        "independent",
        "advice",
    ],
    "freelance_designer": [
        "design",
        "designer",
        "creative",
        "branding",
        "logo",
        "ui",
        "ux",
        "grafisch",
        "graphic",
        "visual",
        "ontwerp",
        "creative",
        "creatief",
        "art",
        "kunst",
    ],
    "freelance_developer": [
        "developer",
        "programmer",
        "ontwikkelaar",
        "coding",
        "web development",
        "app development",
        "backend",
        "frontend",
        "fullstack",
        "software engineer",
        "dev",
    ],
    "horeca": [
        "restaurant",
        "cafe",
        "cafe",
        "hotel",
        "horeca",
        "food",
        "drink",
        "eten",
        "drinken",
        "kitchen",
        "keuken",
        "service",
        "bediening",
        "gastvrijheid",
        "hospitality",
    ],
    "retail": [
        "retail",
        "winkel",
        "shop",
        "store",
        "verkoop",
        "e-commerce",
        "webshop",
        "online store",
        "producten",
        "sales",
        "verkoop",
        "inventory",
        "voorraad",
    ],
    "enterprise_corporate": [
        "enterprise",
        "corporate",
        "large company",
        "big organization",
        "multinational",
        "concern",
        "groot bedrijf",
        "organisatie",
    ],
    "enterprise_saas": [
        "saas",
        "subscription",
        "subscription business",
        "recurring revenue",
        "arr",
        "mrr",
        "cloud software",
        "platform business",
    ],
    "enterprise_fintech": [
        "fintech",
        "finance",
        "financial",
        "banking",
        "payments",
        "bank",
        "financieel",
        "betalingen",
        "crypto",
        "insurance",
    ],
    "enterprise_healthcare": [
        "healthcare",
        "health",
        "medical",
        "zorg",
        "gezondheid",
        "hospital",
        "ziekenhuis",
        "patient",
        "care",
        "kliniek",
    ],
}


def _match_description_to_template(description: str) -> tuple[str, float, str]:
    """Match description to best template using keyword analysis.

    Args:
        description: User's company description

    Returns: Tuple[Any, ...] of (template_key, confidence, match_reason)  # TODO(TYPE): replace Any with concrete type
    """
    description_lower = description.lower()
    scores: dict[str, int] = {}

    for template_key, keywords in KEYWORD_PATTERNS.items():
        score = 0
        for keyword in keywords:
            if keyword in description_lower:
                score += 1
        if score > 0:
            scores[template_key] = score

    if not scores:
        # Default to tech_startup with low confidence
        return (
            "tech_startup",
            0.3,
            "Geen specifieke match gevonden, tech startup aanbevolen als default",
        )

    # Get best match
    best_match = max(scores.items(), key=lambda x: x[1])
    template_key = best_match[0]
    score = best_match[1]

    # Calculate confidence (normalize based on max possible keywords)
    max_keywords = len(KEYWORD_PATTERNS[template_key])
    confidence = min(score / max_keywords * 2, 1.0)  # Scale factor 2 for reasonable confidence

    # Generate match reason
    matched_keywords = [k for k in KEYWORD_PATTERNS[template_key] if k in description_lower][:3]
    match_reason = f"Match gebaseerd op trefwoorden: {', '.join(matched_keywords)}"

    return (template_key, confidence, match_reason)


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="Get recommended templates",
    description="Get top 3 recommended templates based on company type and sector.",
)
async def get_recommended_templates(
    company_type: str = Query(..., description="Company type (mkb, zzp, enterprise)"),
    sector: str | None = Query(None, description="Industry sector (optional)"),
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # TODO(TYPE): replace Any with concrete type
) -> TemplateListResponse:
    """Step 1: Get recommended templates for onboarding.

    Returns top 3 templates matching the specified company type and sector,
    ordered by usage count and rating.

    Args:
        company_type: Type of company (mkb, zzp, enterprise)
        sector: Optional sector filter

    Returns: List[Any] of up to 3 recommended templates  # TODO(TYPE): replace Any with concrete type
    """
    filters = {"company_type": company_type}
    if sector:
        filters["sector"] = sector

    templates = await template_service.list_templates(filters)

    # Return top 3 by usage count (already sorted by service)
    top_templates = templates[:3]

    return TemplateListResponse(
        templates=top_templates,
        total=len(top_templates),
    )


@router.post(
    "/ai-match",
    response_model=OnboardingAIMatchResponse,
    summary="AI template matching",
    description="Match user's description to best template using keyword analysis.",
)
async def ai_match_template(
    data: OnboardingAIMatchRequest,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # TODO(TYPE): replace Any with concrete type
) -> OnboardingAIMatchResponse:
    """Step 2: AI-powered template matching.

    Analyzes user's description using keyword matching to find the
    best template. Returns confidence score and match explanation.

    Args:
        data: Request with company description

    Returns:
        Best matching template with confidence score
    """
    # Match description to template key
    template_key, confidence, match_reason = _match_description_to_template(data.description)

    # Map template key to actual template name
    TEMPLATE_NAME_MAP: dict[str, str] = {
        "tech_startup": "Tech Startup MKB",
        "freelance_consultant": "Freelance Consultant",
        "freelance_designer": "Freelance Designer",
        "freelance_developer": "Freelance Developer",
        "horeca": "Horeca MKB",
        "retail": "Retail Winkel MKB",
        "enterprise_corporate": "Enterprise Corporate",
        "enterprise_saas": "Enterprise SaaS",
        "enterprise_fintech": "Enterprise Fintech",
        "enterprise_healthcare": "Enterprise Healthcare",
    }

    template_name = TEMPLATE_NAME_MAP.get(template_key, "Tech Startup MKB")

    # Find template by name
    all_templates = await template_service.list_templates({})
    matched_template: TemplateResponse | None = None

    for template in all_templates:
        if template.name == template_name:
            matched_template = template
            break

    # If not found, return first template with low confidence
    if not matched_template and all_templates:
        matched_template = all_templates[0]
        confidence = 0.5
        match_reason = "Standaard template geselecteerd"

    if not matched_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geen templates beschikbaar",
        )

    return OnboardingAIMatchResponse(
        template_id=matched_template.id,
        template_name=matched_template.name,
        confidence=confidence,
        match_reason=match_reason,
    )


@router.post(
    "/complete",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Complete onboarding",
    description="Create company using template or manual configuration.",
)
async def complete_onboarding(
    data: OnboardingCompleteRequest,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # TODO(TYPE): replace Any with concrete type
) -> CompanyResponse:
    """Step 3: Complete onboarding and create company.

    Creates a new company using either:
    - A template (template_id provided) - instantiates template
    - Manual configuration (no template_id) - creates blank company

    Args:
        data: Complete onboarding request with company details

    Returns:
        Created company

    Raises:
        404: Template not found
        422: Invalid company data
    """
    if data.template_id:
        # Use template
        instantiate_request = TemplateInstantiateRequest(
            template_id=data.template_id,
            company_name=data.company_name,
            customizations={},  # Could add customizations from data in future
        )

        try:
            return await template_service.instantiate(
                template_id=data.template_id,
                data=instantiate_request,
            )
        except NotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
    else:
        # Manual company creation without template
        # This would require CompanyService - for now we raise an error
        # In future, this could create a blank company structure
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Template is vereist voor onboarding. Selecteer een template of gebruik AI matching.",
        )


@router.get(
    "/status",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get onboarding status",
    description="Check if user has completed onboarding (has a company).",
)
async def get_onboarding_status(
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check onboarding status for current user.

    Returns whether user has completed onboarding
    and basic company info if available.

    Args:
        current_user: Current authenticated user

    Returns:
        Onboarding status with company info if available
    """
    # For now, simple check based on user data
    # In future, could check if user has any companies
    company_id = current_user.get("company_id")

    return {
        "completed": company_id is not None,
        "company_id": company_id,
        "next_step": None if company_id else "template_selection",
    }
