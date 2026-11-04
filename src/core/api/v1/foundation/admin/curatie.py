"""Foundation admin endpoints (curator + admin only)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import cast, func, Numeric, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models.foundation_content import (
    ContentStatus,
    ContentTag,
    EducationalAccess,
    FoundationContent,
    NewsletterStatus,
    NewsletterSubscription,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)
from src.core.shared.datetime_utils import utc_now
from src.core.utils.best_effort import best_effort

from src.core.api.v1.foundation.dependencies import (
    AuditService,
    brevo_email_service,
    get_db,
    public_tenant_scope,
    require_admin,
    require_curator,
)
from src.core.api.v1.foundation.schemas import (
    BulkApproveRequest,
    BulkFailedItem,
    BulkModerationResponse,
    BulkRejectRequest,
    CurationAnalyticsResponse,
    CuratieQueueItem,
    CuratieQueueResponse,
    EducationalAnalytics,
    FoundationContentDetail,
    NewsletterAnalytics,
    RejectContentRequest,
    ReTagResponse,
    TagDistributionItem,
    TakedownDetailResponse,
    TakedownListItem,
    TakedownListResponse,
    TakedownResolveRequest,
    TakedownResolveResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["foundation-admin"])


# ============================================================================
# Curatie (moderation)
# ============================================================================


@router.get(
    "/curatie",
    response_model=CuratieQueueResponse,
    summary="Get moderation queue",
)
@router.get(
    "/curatie/queue",
    response_model=CuratieQueueResponse,
    summary="Get moderation queue (alias)",
    include_in_schema=False,
)
async def get_curatie_queue(
    tenantSlug: str,
    status: str = Query("pending", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List content waiting for moderation.

    - Curators and admins only
    - Filter by status: pending, approved, rejected
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Verify user belongs to tenant
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        # Validate status filter
        try:
            status_enum = ContentStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status}",
            )

        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == status_enum,
            )
            .order_by(FoundationContent.created_at.desc())
        )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Pagination
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        # Execute
        result = await session.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [CuratieQueueItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "status_filter": status,
        }


@router.post(
    "/curatie/{content_id}/approve",
    response_model=FoundationContentDetail,
    summary="Approve content",
)
async def approve_content(
    content_id: int,
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> FoundationContent:
    """Approve pending content.

    - Sets status to APPROVED
    - Logs moderation action (placeholder for audit)
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.PENDING,
            )
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Content not found or not in pending status",
            )

        content.status = ContentStatus.APPROVED
        await session.flush()

        stmt_refreshed = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(FoundationContent.id == content_id)
        )
        return (await session.execute(stmt_refreshed)).scalar_one()


@router.post(
    "/curatie/{content_id}/reject",
    response_model=FoundationContentDetail,
    summary="Reject content",
)
async def reject_content(
    content_id: int,
    tenantSlug: str,
    data: RejectContentRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> FoundationContent:
    """Reject pending content.

    - Sets status to REJECTED
    - Optional rejection reason stored
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.PENDING,
            )
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Content not found or not in pending status",
            )

        content.status = ContentStatus.REJECTED
        if data.rejection_reason:
            content.rejection_reason = data.rejection_reason

        # DSA Art. 17 motiveringsnotificatie naar uploader
        if content.uploader_id and data.rejection_reason:
            uploader_stmt = select(PortalUser).where(PortalUser.id == content.uploader_id)
            uploader_res = await session.execute(uploader_stmt)
            uploader = uploader_res.scalar_one_or_none()
            if uploader and uploader.email:
                tenant_name = getattr(tenant, "name", None)
                async with best_effort("dsa_curation_rejection_email"):
                    await brevo_email_service.send_curation_rejection_notification(
                        to_email=uploader.email,
                        content_title=content.title_nl or content.title_en or "Erfgoedbijdrage",
                        rejection_reason=data.rejection_reason,
                        to_name=uploader.display_name,
                        tenant_name=tenant_name,
                    )

        await session.flush()

        stmt_refreshed = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(FoundationContent.id == content_id)
        )
        return (await session.execute(stmt_refreshed)).scalar_one()


@router.post(
    "/curatie/bulk-approve",
    response_model=BulkModerationResponse,
    summary="Bulk approve content items",
)
async def bulk_approve_content(
    tenantSlug: str,
    data: BulkApproveRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> BulkModerationResponse:
    """Approve multiple pending content items in a single batch (BE-EP-053).

    - Curators and admins only
    - Strictly tenant-isolated
    - Returns 200 OK envelope with success_ids and failed_items
    - Logs audit event for moderation
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(FoundationContent).where(
            FoundationContent.id.in_(data.content_ids),
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        found_items = {item.id: item for item in result.scalars().all()}

        success_ids: list[int] = []
        failed_items: list[BulkFailedItem] = []

        for cid in data.content_ids:
            if cid not in found_items:
                failed_items.append(
                    BulkFailedItem(id=cid, reason="Item niet gevonden voor deze tenant")
                )
            else:
                item = found_items[cid]
                if item.status != ContentStatus.PENDING:
                    status_val = (
                        item.status.value if hasattr(item.status, "value") else str(item.status)
                    )
                    failed_items.append(
                        BulkFailedItem(
                            id=cid,
                            reason=f"Item heeft status '{status_val}', vereist 'pending'",
                        )
                    )
                else:
                    item.status = ContentStatus.APPROVED
                    success_ids.append(cid)

        if success_ids:
            await session.flush()

            # Audit logging
            async with best_effort("audit_bulk_content_approved", db_session=session):
                await AuditService.log_event(
                    db=session,
                    event_type="bulk_content_approved",
                    severity="medium",
                    source_ip="internal",
                    endpoint=f"/{tenantSlug}/foundation/admin/curatie/bulk-approve",
                    description=f"{len(success_ids)} items goedgekeurd in bulk moderatie",
                    user_id=None,
                    tenant_id=tenant.id,
                    action="bulk_approve",
                    resource="foundation_content:batch",
                    metadata={
                        "portal_user_id": current_user.id,
                        "success_count": len(success_ids),
                        "failed_count": len(failed_items),
                        "success_ids": success_ids,
                    },
                )

        msg = f"{len(success_ids)} item(s) succesvol goedgekeurd."
        if failed_items:
            msg += f" {len(failed_items)} item(s) konden niet worden verwerkt."

        return BulkModerationResponse(
            total_requested=len(data.content_ids),
            processed_count=len(data.content_ids),
            success_ids=success_ids,
            failed_items=failed_items,
            message=msg,
        )


@router.post(
    "/curatie/bulk-reject",
    response_model=BulkModerationResponse,
    summary="Bulk reject content items",
)
async def bulk_reject_content(
    tenantSlug: str,
    data: BulkRejectRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> BulkModerationResponse:
    """Reject multiple pending content items in a single batch (BE-EP-053).

    - Curators and admins only
    - Strictly tenant-isolated
    - Requires statement of reasons (DSA Art. 17)
    - Returns 200 OK envelope with success_ids and failed_items
    - Logs audit event for moderation
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(FoundationContent).where(
            FoundationContent.id.in_(data.content_ids),
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        found_items = {item.id: item for item in result.scalars().all()}

        success_ids: list[int] = []
        failed_items: list[BulkFailedItem] = []
        reason = data.rejection_reason.strip()

        for cid in data.content_ids:
            if cid not in found_items:
                failed_items.append(
                    BulkFailedItem(id=cid, reason="Item niet gevonden voor deze tenant")
                )
            else:
                item = found_items[cid]
                if item.status != ContentStatus.PENDING:
                    status_val = (
                        item.status.value if hasattr(item.status, "value") else str(item.status)
                    )
                    failed_items.append(
                        BulkFailedItem(
                            id=cid,
                            reason=f"Item heeft status '{status_val}', vereist 'pending'",
                        )
                    )
                else:
                    item.status = ContentStatus.REJECTED
                    item.rejection_reason = reason
                    success_ids.append(cid)

        if success_ids:
            await session.flush()

            # DSA Art. 17 notificaties per afgewezen item naar de uploader
            tenant_name = getattr(tenant, "name", None)
            for cid in success_ids:
                item = found_items[cid]
                if item.uploader_id and reason:
                    uploader_stmt = select(PortalUser).where(PortalUser.id == item.uploader_id)
                    uploader_res = await session.execute(uploader_stmt)
                    uploader = uploader_res.scalar_one_or_none()
                    if uploader and uploader.email:
                        async with best_effort(f"dsa_bulk_rejection_email_{cid}"):
                            await brevo_email_service.send_curation_rejection_notification(
                                to_email=uploader.email,
                                content_title=item.title_nl or item.title_en or "Erfgoedbijdrage",
                                rejection_reason=reason,
                                to_name=uploader.display_name,
                                tenant_name=tenant_name,
                            )

            # Audit logging
            async with best_effort("audit_bulk_content_rejected", db_session=session):
                await AuditService.log_event(
                    db=session,
                    event_type="bulk_content_rejected",
                    severity="medium",
                    source_ip="internal",
                    endpoint=f"/{tenantSlug}/foundation/admin/curatie/bulk-reject",
                    description=f"{len(success_ids)} items afgewezen in bulk moderatie (DSA Art. 17)",
                    user_id=None,
                    tenant_id=tenant.id,
                    action="bulk_reject",
                    resource="foundation_content:batch",
                    metadata={
                        "portal_user_id": current_user.id,
                        "success_count": len(success_ids),
                        "failed_count": len(failed_items),
                        "success_ids": success_ids,
                        "rejection_reason": reason,
                    },
                )

        msg = f"{len(success_ids)} item(s) afgewezen."
        if failed_items:
            msg += f" {len(failed_items)} item(s) konden niet worden verwerkt."

        return BulkModerationResponse(
            total_requested=len(data.content_ids),
            processed_count=len(data.content_ids),
            success_ids=success_ids,
            failed_items=failed_items,
            message=msg,
        )


@router.post(
    "/curatie/{content_id}/re-tag",
    response_model=ReTagResponse,
    summary="Re-trigger AI tagging for content item",
)
async def retag_content(
    content_id: int,
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> ReTagResponse:
    """Re-trigger AI tagging for a content item (ADR-029 P1-1).

    - Curators and admins only
    - Verifies content exists in this tenant
    - Dispatches tag_foundation_content_async actor
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        try:
            from src.workers.actors import tag_foundation_content_async

            tag_foundation_content_async.send(content.id, tenant.id)
        except Exception as e:
            # De uitzonderingstekst hoort in het log, niet in het antwoord: hij kan
            # broker-adressen of interne paden bevatten (tests/architecture/
            # test_geen_uitzonderingstekst_in_een_antwoord.py).
            logger.error(
                "retag_enqueue_failed content_id=%s: %s: %s",
                content.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Het opnieuw inplannen van AI-tagging is mislukt.",
            ) from e

        return ReTagResponse(
            content_id=content.id,
            status="queued",
            message="AI-tagging is opnieuw ingepland voor dit item.",
        )


@router.get(
    "/curatie/analytics",
    response_model=CurationAnalyticsResponse,
    summary="Get curation analytics and platform KPIs",
)
@router.get(
    "/analytics",
    response_model=CurationAnalyticsResponse,
    summary="Get curation analytics and platform KPIs (alias)",
    include_in_schema=False,
)
async def get_curation_analytics(
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> CurationAnalyticsResponse:
    """Get aggregated curation KPIs and platform metrics.

    - Curators and admins only
    - Strictly scoped to current tenant
    - Includes status breakdown, average moderation duration, top NDE tags,
      newsletter growth, and active educational codes.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        # 1. Status counts
        status_stmt = (
            select(
                FoundationContent.status,
                func.count(FoundationContent.id),
            )
            .where(FoundationContent.tenant_id == tenant.id)
            .group_by(FoundationContent.status)
        )
        status_rows = (await session.execute(status_stmt)).all()
        status_counts: dict[str, int] = {s.value: 0 for s in ContentStatus}
        for s_val, count in status_rows:
            key = s_val.value if hasattr(s_val, "value") else str(s_val)
            status_counts[key] = count

        # 2. Total content
        total_stmt = select(func.count(FoundationContent.id)).where(
            FoundationContent.tenant_id == tenant.id
        )
        total_content = (await session.execute(total_stmt)).scalar() or 0

        # 3. Moderation duration (average seconds between created_at and updated_at for moderated items)
        dur_stmt = select(
            func.avg(
                func.extract(
                    "epoch",
                    FoundationContent.updated_at - FoundationContent.created_at,
                )
            )
        ).where(
            FoundationContent.tenant_id == tenant.id,
            FoundationContent.status.in_([ContentStatus.APPROVED, ContentStatus.REJECTED]),
            FoundationContent.updated_at > FoundationContent.created_at,
        )
        avg_dur_val = (await session.execute(dur_stmt)).scalar()
        avg_moderation_seconds = float(avg_dur_val) if avg_dur_val is not None else None

        # 4. Tag distribution (top 20)
        tag_stmt = (
            select(
                ContentTag.value,
                ContentTag.tag_type,
                func.count(ContentTag.id).label("count"),
                func.round(cast(func.avg(ContentTag.confidence), Numeric), 2).label("average_confidence"),
            )
            .join(FoundationContent, ContentTag.content_id == FoundationContent.id)
            .where(FoundationContent.tenant_id == tenant.id)
            .group_by(ContentTag.value, ContentTag.tag_type)
            .order_by(func.count(ContentTag.id).desc())
            .limit(20)
        )
        tag_rows = (await session.execute(tag_stmt)).all()
        tag_distribution = [
            TagDistributionItem(
                tag=str(row[0]),
                tag_type=row[1].value if hasattr(row[1], "value") else str(row[1]),
                count=int(row[2]),
                average_confidence=float(row[3]) if row[3] is not None else 1.0,
            )
            for row in tag_rows
        ]

        # 5. Newsletter metrics
        news_total_stmt = select(func.count(NewsletterSubscription.id)).where(
            NewsletterSubscription.tenant_id == tenant.id
        )
        news_total = (await session.execute(news_total_stmt)).scalar() or 0

        news_ver_stmt = select(func.count(NewsletterSubscription.id)).where(
            NewsletterSubscription.tenant_id == tenant.id,
            NewsletterSubscription.status == NewsletterStatus.SUBSCRIBED,
        )
        news_ver = (await session.execute(news_ver_stmt)).scalar() or 0

        # 6. Educational metrics
        now = utc_now()
        edu_active_stmt = select(func.count(EducationalAccess.id)).where(
            EducationalAccess.tenant_id == tenant.id,
            EducationalAccess.is_active.is_(True),
            (EducationalAccess.expires_at.is_(None) | (EducationalAccess.expires_at > now)),
        )
        edu_active = (await session.execute(edu_active_stmt)).scalar() or 0

        edu_total_stmt = select(func.count(EducationalAccess.id)).where(
            EducationalAccess.tenant_id == tenant.id
        )
        edu_total = (await session.execute(edu_total_stmt)).scalar() or 0

        return CurationAnalyticsResponse(
            status_counts=status_counts,
            total_content=total_content,
            average_moderation_seconds=avg_moderation_seconds,
            tag_distribution=tag_distribution,
            newsletter=NewsletterAnalytics(
                total_subscribers=news_total,
                verified_subscribers=news_ver,
            ),
            education=EducationalAnalytics(
                active_codes=edu_active,
                total_codes=edu_total,
            ),
        )


# ============================================================================
# Notice & Takedown Moderation (BE-EP-051 / DSA Art. 16/17)
# ============================================================================


@router.get(
    "/curatie/takedowns",
    response_model=TakedownListResponse,
    summary="List Notice & Takedown requests",
)
@router.get(
    "/takedowns",
    response_model=TakedownListResponse,
    summary="List Notice & Takedown requests (alias)",
    include_in_schema=False,
)
async def get_curatie_takedowns(
    tenantSlug: str,
    status: str | None = Query(
        None, description="Filter by status (pending, approved, rejected, escalated)"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> TakedownListResponse:
    """List Notice & Takedown requests waiting for curation or already resolved.

    - Curators and admins only
    - Filter by status: pending, approved, rejected, escalated
    - Joins with FoundationContent for title and current status
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(
                TakedownRequest,
                FoundationContent.title_nl,
                FoundationContent.title_en,
                FoundationContent.type,
                FoundationContent.status.label("content_status"),
            )
            .outerjoin(FoundationContent, TakedownRequest.content_id == FoundationContent.id)
            .where(TakedownRequest.tenant_id == tenant.id)
        )

        if status:
            try:
                status_enum = TakedownStatus(status.lower())
                stmt = stmt.where(TakedownRequest.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid takedown status filter: {status}",
                )

        stmt = stmt.order_by(TakedownRequest.created_at.desc())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).all()

        items = []
        for row in rows:
            td = row[0]
            title_nl = row[1]
            title_en = row[2]
            c_type = row[3]
            c_status = row[4]

            content_title = title_nl or title_en or f"Erfgoeditem #{td.content_id}"
            type_val = c_type.value if hasattr(c_type, "value") else str(c_type) if c_type else None
            status_val = (
                c_status.value
                if hasattr(c_status, "value")
                else str(c_status)
                if c_status
                else None
            )
            items.append(
                TakedownListItem(
                    id=td.id,
                    content_id=td.content_id,
                    content_title=content_title,
                    content_type=type_val,
                    content_status=status_val,
                    requester_name=td.requester_name,
                    requester_email=td.requester_email,
                    legal_basis=td.legal_basis,
                    status=td.status.value if hasattr(td.status, "value") else str(td.status),
                    resolution_note=td.resolution_note,
                    resolved_at=td.resolved_at,
                    created_at=td.created_at,
                )
            )

        return TakedownListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            status_filter=status,
        )


@router.get(
    "/curatie/takedowns/{takedown_id}",
    response_model=TakedownDetailResponse,
    summary="Get single Notice & Takedown request detail",
)
async def get_curatie_takedown_detail(
    takedown_id: int,
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> TakedownDetailResponse:
    """Get detailed Notice & Takedown request report for curation."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(TakedownRequest).where(
            TakedownRequest.id == takedown_id,
            TakedownRequest.tenant_id == tenant.id,
        )
        takedown = (await session.execute(stmt)).scalar_one_or_none()
        if takedown is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Takedown request not found",
            )

        content_stmt = select(FoundationContent).where(
            FoundationContent.id == takedown.content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        content = (await session.execute(content_stmt)).scalar_one_or_none()

        content_title = (
            getattr(content, "title_nl", None) or getattr(content, "title_en", None)
            if content
            else None
        )
        content_type = (
            content.type.value
            if (content and hasattr(content.type, "value"))
            else str(content.type)
            if content
            else None
        )
        content_status = (
            content.status.value
            if (content and hasattr(content.status, "value"))
            else str(content.status)
            if content
            else None
        )
        content_desc = (
            (content.description_nl or content.body_nl[:200])
            if content and (content.description_nl or content.body_nl)
            else None
        )

        return TakedownDetailResponse(
            id=takedown.id,
            content_id=takedown.content_id,
            content_title=content_title,
            content_type=content_type,
            content_status=content_status,
            content_description=content_desc,
            content_creator_name=getattr(content, "creator_name", None) if content else None,
            content_file_url=getattr(content, "file_url", None) if content else None,
            requester_name=takedown.requester_name,
            requester_email=takedown.requester_email,
            legal_basis=takedown.legal_basis,
            status=takedown.status.value
            if hasattr(takedown.status, "value")
            else str(takedown.status),
            resolution_note=takedown.resolution_note,
            resolved_at=takedown.resolved_at,
            created_at=takedown.created_at,
        )


@router.put(
    "/curatie/takedowns/{takedown_id}",
    response_model=TakedownResolveResponse,
    summary="Resolve Notice & Takedown request",
)
@router.patch(
    "/curatie/takedowns/{takedown_id}",
    response_model=TakedownResolveResponse,
    summary="Resolve Notice & Takedown request (alias)",
    include_in_schema=False,
)
async def resolve_curatie_takedown(
    takedown_id: int,
    tenantSlug: str,
    data: TakedownResolveRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> TakedownResolveResponse:
    """Resolve, reject, or escalate a Notice & Takedown request.

    - Curators and admins only
    - If status == APPROVED: content.status -> REMOVED, takedown_reason and takedown_at populated.
    - If status == REJECTED: content remains active.
    - If status == ESCALATED: marked for board/legal review.
    - Sends transactional notification via Brevo to requester (DSA Art. 16(5)).
    - Logs audit event takedown_resolved with severity HIGH.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(TakedownRequest).where(
            TakedownRequest.id == takedown_id,
            TakedownRequest.tenant_id == tenant.id,
        )
        takedown = (await session.execute(stmt)).scalar_one_or_none()
        if takedown is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Takedown request not found",
            )

        content_stmt = select(FoundationContent).where(
            FoundationContent.id == takedown.content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        content = (await session.execute(content_stmt)).scalar_one_or_none()

        target_status = (
            data.status
            if isinstance(data.status, TakedownStatus)
            else TakedownStatus(str(data.status).lower())
        )
        now = utc_now()

        takedown.status = target_status
        takedown.resolution_note = data.resolution_note
        takedown.resolved_at = now

        content_status_str = "unknown"
        if content:
            if target_status == TakedownStatus.APPROVED:
                content.status = ContentStatus.REMOVED
                content.takedown_reason = data.resolution_note
                content.takedown_at = now
            content_status_str = (
                content.status.value if hasattr(content.status, "value") else str(content.status)
            )

        await session.flush()

        # Send Brevo email notification to requester
        if data.notify_requester and takedown.requester_email:
            async with best_effort("takedown_resolution_email"):
                content_title = (
                    getattr(content, "title_nl", getattr(content, "title_en", "Erfgoeditem"))
                    if content
                    else "Erfgoeditem"
                )
                await brevo_email_service.send_takedown_resolution(
                    to_email=takedown.requester_email,
                    takedown_id=takedown.id,
                    content_title=content_title,
                    status=target_status.value,
                    resolution_note=data.resolution_note,
                    tenant_name=getattr(tenant, "name", None),
                )

        # Audit log event (ADR-019)
        async with best_effort("audit_takedown_resolved", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="takedown_resolved",
                severity="high",
                source_ip="internal",
                endpoint=f"/{tenantSlug}/foundation/admin/curatie/takedowns/{takedown_id}",
                description=f"Takedown #{takedown.id} resolved as {target_status.value}",
                user_id=None,
                tenant_id=tenant.id,
                action=f"takedown_{target_status.value}",
                resource=f"takedown:{takedown.id}",
                metadata={
                    "portal_user_id": current_user.id,
                    "takedown_id": takedown.id,
                    "content_id": takedown.content_id,
                    "target_status": target_status.value,
                    "content_status": content_status_str,
                },
            )

        return TakedownResolveResponse(
            id=takedown.id,
            content_id=takedown.content_id,
            status=target_status.value,
            content_status=content_status_str,
            resolution_note=takedown.resolution_note,
            resolved_at=takedown.resolved_at,
            message=f"Notice & Takedown melding #{takedown.id} succesvol afgehandeld ({target_status.value}).",
        )


@router.post(
    "/curatie/{content_id}/restore",
    response_model=FoundationContentDetail,
    summary="Restore removed content",
)
async def restore_content(
    content_id: int,
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> FoundationContent:
    """Restore removed content back to approved status.

    - Curators and admins only
    - Allows reversal of takedown if objection was sustained
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.REMOVED,
            )
        )
        content = (await session.execute(stmt)).scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Content not found or not in removed status",
            )

        content.status = ContentStatus.APPROVED
        content.takedown_reason = None
        content.takedown_at = None
        await session.flush()

        async with best_effort("audit_content_restored", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="content_restored",
                severity="medium",
                source_ip="internal",
                endpoint=f"/{tenantSlug}/foundation/admin/curatie/{content_id}/restore",
                description=f"Content #{content_id} restored to APPROVED",
                user_id=None,
                tenant_id=tenant.id,
                action="content_restore",
                resource=f"content:{content_id}",
                metadata={
                    "portal_user_id": current_user.id,
                    "content_id": content_id,
                },
            )

        stmt_refreshed = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(FoundationContent.id == content_id)
        )
        return (await session.execute(stmt_refreshed)).scalar_one()
