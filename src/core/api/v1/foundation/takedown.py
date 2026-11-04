"""Foundation Portal takedown endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    AuditService,
    brevo_email_service,
    get_db,
    notification_service,
    public_tenant_scope,
    require_portal_takedown_rate_limit,
    require_portal_user,
)
from src.core.api.v1.foundation.schemas import (
    TakedownCreateRequest,
    TakedownResponse,
)
from src.core.models.foundation_content import (
    FoundationContent,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)
from src.core.security.hcaptcha import require_hcaptcha
from src.core.utils.best_effort import best_effort

router = APIRouter(tags=["foundation-takedown"])


@router.post(
    "/takedown",
    response_model=TakedownResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit takedown request",
)
async def create_takedown(
    tenantSlug: str,
    request: Request,
    data: TakedownCreateRequest = Body(...),
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
    _check: None = Depends(require_portal_takedown_rate_limit),
) -> dict[str, str | int]:
    """Submit a content takedown request.

    - Requires valid portal JWT
    - Content must exist and belong to the same tenant
    - Creates TakedownRequest record
    - Sends notification to admin (best_effort)
    - Rate limit: 5 per hour per IP
    """
    client_ip = request.client.host if request.client else None
    await require_hcaptcha(data.hcaptcha_token, remote_ip=client_ip)

    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Verify user belongs to this tenant
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        # Verify content exists and belongs to tenant
        stmt = select(FoundationContent).where(
            FoundationContent.id == data.content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        content: FoundationContent | None = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        # Create takedown request
        takedown = TakedownRequest(
            tenant_id=tenant.id,
            content_id=data.content_id,
            requester_email=data.contact_email,
            requester_name=current_user.display_name or current_user.email,
            legal_basis=data.reason,
            status=TakedownStatus.PENDING,
        )
        session.add(takedown)
        await session.flush()
        await session.refresh(takedown)

        # Notify admin (best_effort)
        async with best_effort("takedown_notification", db_session=session):
            await notification_service.notify_tenant(
                tenant_id=str(tenant.id),
                title="New Takedown Request",
                message=f"Takedown request #{takedown.id} for content #{data.content_id}",
            )

        # Send confirmation email to requester (best_effort)
        async with best_effort("takedown_confirmation_email"):
            content_title = getattr(
                content, "title_nl", getattr(content, "title_en", "Erfgoeditem")
            )
            await brevo_email_service.send_takedown_confirmation(
                to_email=data.contact_email,
                takedown_id=takedown.id,
                content_title=content_title,
                tenant_name=getattr(tenant, "name", None),
            )

        # Audit log (best-effort, never blocks takedown)
        async with best_effort("audit_takedown_created", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="takedown_created",
                severity="medium",
                source_ip=request.client.host if request.client else "unknown",
                endpoint=f"/{tenantSlug}/foundation/takedown",
                description=f"Takedown request #{takedown.id} submitted",
                user_id=None,
                tenant_id=tenant.id,
                action="takedown_create",
                resource=f"content:{data.content_id}",
                metadata={
                    "content_id": data.content_id,
                    "takedown_id": takedown.id,
                    "portal_user_id": current_user.id,
                },
            )

        return {
            "id": takedown.id,
            "status": "pending",
            "message": "Takedown request submitted successfully.",
        }
