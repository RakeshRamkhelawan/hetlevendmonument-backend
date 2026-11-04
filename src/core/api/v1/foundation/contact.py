"""Foundation Portal contact and community support endpoints (BE-EP-048 / ADR-029 P2)."""

from __future__ import annotations

import secrets
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    brevo_email_service,
    get_db,
    portal_public_write_limit,
    public_tenant_scope,
    require_curator,
)
from src.core.api.v1.foundation.schemas import (
    ContactSubmissionRequest,
    ContactSubmissionResponse,
)
from src.core.models.foundation_content import (
    FoundationContactSubmission,
    FoundationPortalSettings,
    PortalUser,
)
from src.core.security.hcaptcha import require_hcaptcha
from src.core.shared.datetime_utils import utc_now
from src.core.utils.best_effort import best_effort

router = APIRouter(tags=["foundation-contact"])


@router.post(
    "/contact",
    response_model=ContactSubmissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit contact or support inquiry",
)
@portal_public_write_limit
async def submit_contact_inquiry(
    tenantSlug: str,
    request: Request,
    data: ContactSubmissionRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> ContactSubmissionResponse:
    """Submit a contact question, school inquiry or support request to the foundation.

    - Public endpoint (rate-limited via portal_public_write_limit)
    - Protected against automated bots via hCaptcha
    - Generates a unique tracking reference (CON-YYYYMMDD-XXXX)
    - Persists inquiry to PostgreSQL database table with tenant RLS isolation
    - Resolves tenant-specific contact destination
    - Records receipt with audit metadata
    """
    client_ip = request.client.host if request.client else None
    await require_hcaptcha(data.hcaptcha_token, remote_ip=client_ip)

    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Haal eventuele portal settings op voor de stichting
        settings_stmt = select(FoundationPortalSettings).where(
            FoundationPortalSettings.tenant_id == tenant.id
        )
        res = await session.execute(settings_stmt)
        portal_settings = res.scalars().first()
        target_email = (
            portal_settings.contact_email
            if portal_settings and portal_settings.contact_email
            else None
        )

        now = utc_now()
        date_str = now.strftime("%Y%m%d")
        random_suffix = secrets.token_hex(2).upper()
        reference_id = f"CON-{date_str}-{random_suffix}"

        # Persisteer direct in PostgreSQL (ADR-029 audit hardening)
        submission = FoundationContactSubmission(
            tenant_id=tenant.id,
            reference_number=reference_id,
            name=data.name,
            email=str(data.email),
            subject=data.subject,
            category=data.category,
            message=data.message,
        )
        session.add(submission)
        await session.commit()
        await session.refresh(submission)

        logger.info(
            "Contact inquiry received and stored: reference={} tenant={} category={} email={}",
            reference_id,
            tenantSlug,
            data.category,
            data.email,
        )

        # Stuur ontvangstbevestiging naar indiener
        tenant_name = getattr(tenant, "name", None)
        async with best_effort("contact_confirmation_email"):
            await brevo_email_service.send_contact_confirmation(
                to_email=str(data.email),
                reference_id=reference_id,
                sender_name=data.name,
                subject=data.subject,
                tenant_name=tenant_name,
            )

        # Stuur notificatie naar beheerder indien geconfigureerd
        if target_email:
            async with best_effort("contact_notification_email"):
                await brevo_email_service.send_contact_notification(
                    to_email=target_email,
                    reference_id=reference_id,
                    sender_name=data.name,
                    sender_email=str(data.email),
                    subject=data.subject,
                    category=data.category,
                    message=data.message,
                    tenant_name=tenant_name,
                )

        return ContactSubmissionResponse(
            reference_id=reference_id,
            status="received",
            message="Uw bericht is succesvol ontvangen. Ons team neemt zo spoedig mogelijk contact met u op.",
            created_at=now.isoformat(),
        )


@router.get(
    "/admin/contact-submissions",
    summary="List contact submissions for tenant (curator/admin only)",
)
async def list_contact_submissions(
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Curator and admin only endpoint listing contact submissions from database."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # BE-SEC-056: token-tenant moet overeenkomen met de pad-tenant, zoals
        # curatie.py/edu.py/settings.py al deden. Zonder deze check leest een
        # curator van tenant A met zijn eigen JWT contact-PII van tenant B.
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationContactSubmission)
            .where(FoundationContactSubmission.tenant_id == tenant.id)
            .order_by(FoundationContactSubmission.created_at.desc())
        )
        result = await session.execute(stmt)
        submissions = result.scalars().all()

        return {
            "total": len(submissions),
            "items": [
                {
                    "id": s.id,
                    "reference_number": s.reference_number,
                    "name": s.name,
                    "email": s.email,
                    "subject": s.subject,
                    "category": s.category,
                    "message": s.message,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in submissions
            ],
        }
