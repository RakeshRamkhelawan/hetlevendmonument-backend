"""Foundation Portal settings endpoint (public, white-label branding)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    get_db,
    portal_public_read_limit,
    public_tenant_scope,
    require_curator,
)
from src.core.api.v1.foundation.schemas import (
    PortalSettingsResponse,
    PortalSettingsUpdateRequest,
)
from src.core.models.foundation_content import FoundationPortalSettings, PortalUser

router = APIRouter(tags=["foundation-settings"])


@router.get(
    "/settings",
    response_model=PortalSettingsResponse,
    summary="Get portal settings",
)
@portal_public_read_limit
async def get_settings(
    request: Request,
    tenantSlug: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Public endpoint returning portal branding/settings.

    - No authentication required
    - Returns portal name, theme colors, contact info, etc.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = select(FoundationPortalSettings).where(
            FoundationPortalSettings.tenant_id == tenant.id
        )
        result = await session.execute(stmt)
        settings: FoundationPortalSettings | None = result.scalar_one_or_none()

        if settings is None:
            # White-label: geen settings = geen branding. Een hardcoded default zou de
            # branding van een tenant aan een andere tenant tonen (multi-tenant lek).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portal settings not found",
            )

        return {
            "platform_name_nl": settings.platform_name_nl,
            "platform_name_en": settings.platform_name_en,
            "primary_color": settings.primary_color,
            "accent_color": settings.accent_color,
            "logo_url": settings.logo_url,
            "favicon_url": settings.favicon_url,
            "guidelines_nl": settings.guidelines_nl,
            "guidelines_en": settings.guidelines_en,
            "about_nl": settings.about_nl,
            "about_en": settings.about_en,
            "contact_email": settings.contact_email,
        }


@router.put(
    "/admin/settings",
    response_model=PortalSettingsResponse,
    summary="Update portal branding & settings (BE-EP-047)",
)
async def update_settings(
    tenantSlug: str,
    payload: PortalSettingsUpdateRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Curator/admin endpoint to update white-label portal branding and settings.

    - Requires curator or admin role.
    - Strictly scoped to the authenticated tenant.
    - Upserts settings if none exist yet for the tenant.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(FoundationPortalSettings).where(
            FoundationPortalSettings.tenant_id == tenant.id
        )
        result = await session.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings is None:
            settings = FoundationPortalSettings(
                tenant_id=tenant.id,
                platform_name_nl=payload.platform_name_nl or "Levend Monument",
                platform_name_en=payload.platform_name_en,
                primary_color=payload.primary_color or "#1a2f45",
                accent_color=payload.accent_color or "#e8b86d",
                logo_url=payload.logo_url,
                favicon_url=payload.favicon_url,
                guidelines_nl=payload.guidelines_nl,
                guidelines_en=payload.guidelines_en,
                about_nl=payload.about_nl,
                about_en=payload.about_en,
                contact_email=payload.contact_email,
            )
            session.add(settings)
        else:
            update_data = payload.model_dump(exclude_unset=True)
            for field, val in update_data.items():
                if hasattr(settings, field) and val is not None:
                    setattr(settings, field, val)

        await session.flush()

        return {
            "platform_name_nl": settings.platform_name_nl,
            "platform_name_en": settings.platform_name_en,
            "primary_color": settings.primary_color,
            "accent_color": settings.accent_color,
            "logo_url": settings.logo_url,
            "favicon_url": settings.favicon_url,
            "guidelines_nl": settings.guidelines_nl,
            "guidelines_en": settings.guidelines_en,
            "about_nl": settings.about_nl,
            "about_en": settings.about_en,
            "contact_email": settings.contact_email,
        }

