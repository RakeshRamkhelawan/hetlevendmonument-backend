"""Foundation content endpoints (public + authenticated)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.shared.datetime_utils import utc_now

logger = logging.getLogger(__name__)

from src.core.api.v1.foundation.dependencies import (
    get_db,
    get_optional_portal_user,
    portal_public_write_limit,
    public_tenant_scope,
    require_portal_user,
)
from src.core.api.v1.foundation.schemas import (
    FoundationBestandItem,
    FoundationContentCreateRequest,
    FoundationContentDeleteResponse,
    FoundationContentDetail,
    FoundationContentListItem,
    FoundationContentListResponse,
    FoundationContentUpdateRequest,
)
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    FoundationContentBestand,
    PortalRole,
    PortalUser,
    Privacy,
    Visibility,
)

router = APIRouter(tags=["foundation-content"])


@router.get(
    "/content",
    response_model=FoundationContentListResponse,
    summary="List approved content",
)
async def list_content(
    tenantSlug: str,
    category: str | None = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Public list of approved foundation content.

    - Anonymous users see only PUBLIC privacy content
    - Authenticated users (via optional JWT) see PUBLIC + COMMUNITY
      (only if user belongs to the same tenant)
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Determine privacy filter based on auth
        privacy_filter = [Privacy.PUBLIC]
        if current_user is not None and current_user.tenant_id == tenant.id:
            privacy_filter.append(Privacy.COMMUNITY)

        # O5 (BE-EP-039, audit N-2-invariant): filter on the publication
        # CHANNEL too, mirroring the privacy levels. Edu content must never
        # appear in the public archive; the BE-MIG-014 backfill keeps this
        # identical to the privacy filter for pre-existing rows.
        visibility_filter = [Visibility.PUBLIC]
        if current_user is not None and current_user.tenant_id == tenant.id:
            visibility_filter.append(Visibility.COMMUNITY)

        # Base query: approved status + tenant
        stmt = (
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.privacy.in_(privacy_filter),
                FoundationContent.visibility.in_(visibility_filter),
            )
            .order_by(FoundationContent.created_at.desc())
        )

        # Category filter
        if category:
            stmt = stmt.where(FoundationContent.category == category)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Pagination
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [FoundationContentListItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get(
    "/content/my-submissions",
    response_model=FoundationContentListResponse,
    summary="List current user's submitted content",
)
async def list_my_submissions(
    tenantSlug: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all content items submitted by the authenticated portal user, including pending/rejected."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        base_stmt = select(FoundationContent).where(
            FoundationContent.tenant_id == tenant.id,
            FoundationContent.uploader_id == current_user.id,
            FoundationContent.status != ContentStatus.REMOVED,
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        items_stmt = (
            base_stmt.order_by(FoundationContent.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = (await session.execute(items_stmt)).scalars().all()

        return {
            "items": [FoundationContentListItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get(
    "/content/{content_id}",
    response_model=FoundationContentDetail,
    summary="Get content detail",
)
async def get_content(
    content_id: int,
    tenantSlug: str,
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
) -> FoundationContentDetail:
    """Detail view of a single content item.

    Goedgekeurde items zijn voor iedereen (met de privacyregels hieronder). BE-EP-057: een
    item dat nog niet (of niet meer) is goedgekeurd, is alleen zichtbaar voor een curator of
    beheerder van deze tenant, of, zolang het in behandeling of afgewezen is, voor de
    inzender zelf. Zo kan de curator een inzending met al haar bestanden bekijken voordat
    hij beslist. Iedereen anders krijgt dezelfde 404 als bij een onbekend id.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                # O5 (BE-EP-039, audit N-2-invariant): the edu channel is only
                # reachable via /edu/* with a session. Uniform 404 below, so the
                # public endpoint does not reveal that the row exists.
                FoundationContent.visibility != Visibility.EDU,
            )
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()

        if content is not None and content.status != ContentStatus.APPROVED:
            is_curator = (
                current_user is not None
                and current_user.tenant_id == tenant.id
                and current_user.role in (PortalRole.ADMIN, PortalRole.CURATOR)
            )
            is_inzender = (
                current_user is not None
                and current_user.tenant_id == tenant.id
                and content.uploader_id is not None
                and current_user.id == content.uploader_id
                and content.status in (ContentStatus.PENDING, ContentStatus.REJECTED)
            )
            if not (is_curator or is_inzender):
                content = None

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        # Privacy check: COMMUNITY content requires auth AND same tenant
        if content.privacy == Privacy.COMMUNITY:
            if current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required for community content",
                )
            if current_user.tenant_id != tenant.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not belong to this tenant",
                )

        # BE-EP-057: de extra bestanden, op volgorde (de bytes via de media-route).
        bestanden = (
            (
                await session.execute(
                    select(FoundationContentBestand)
                    .where(
                        FoundationContentBestand.content_id == content.id,
                        FoundationContentBestand.tenant_id == tenant.id,
                    )
                    .order_by(FoundationContentBestand.volgorde)
                )
            )
            .scalars()
            .all()
        )
        detail = FoundationContentDetail.model_validate(content)
        detail.bestanden = [FoundationBestandItem.model_validate(b) for b in bestanden]
        return detail


@router.post(
    "/content",
    response_model=FoundationContentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload new content",
)
@portal_public_write_limit
async def create_content(
    tenantSlug: str,
    request: Request,
    data: FoundationContentCreateRequest,
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
) -> FoundationContent:
    """Upload new content. Goes to PENDING status, requires moderation.

    - Supports both authenticated portal users and guest submissions
    - Content starts as PENDING until approved by curator
    - Rights confirmation required (copyright)
    - Rate limit: 10/min per IP (audit N-4, BE-EP-036); the ``request``
      parameter is required for the rate-limit decorator to engage
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        uploader_id = None
        if current_user is not None:
            # Verify user belongs to this tenant
            if current_user.tenant_id != tenant.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not belong to this tenant",
                )
            uploader_id = current_user.id

        # Create content
        content = FoundationContent(
            tenant_id=tenant.id,
            uploader_id=uploader_id,
            type=ContentType(data.type),
            title_nl=data.title_nl,
            title_en=data.title_en,
            description_nl=data.description_nl,
            description_en=data.description_en,
            body_nl=data.body_nl,
            body_en=data.body_en,
            creator_name=data.creator_name,
            is_anonymous=data.is_anonymous,
            language=data.language,
            privacy=Privacy(data.privacy),
            status=ContentStatus.PENDING,
            rights_confirmed=data.rights_confirmed,
            external_url=data.external_url,
            lat=data.lat,
            lng=data.lng,
            location_name=data.location_name,
            license=data.license,
            category=data.category,
            metadata_=data.metadata,
        )

        session.add(content)
        await session.flush()

        stmt_refreshed = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(FoundationContent.id == content.id)
        )
        content = (await session.execute(stmt_refreshed)).scalar_one()

        # Dispatch async AI tagging (ADR-029 P1-1)
        try:
            from src.workers.actors import tag_foundation_content_async

            tag_foundation_content_async.send(content.id, tenant.id)
        except Exception as e:
            logger.warning("Failed to enqueue tag_foundation_content_async: %s", e)

        return content


@router.put(
    "/content/{content_id}",
    response_model=FoundationContentDetail,
    summary="Update content metadata",
)
async def update_content(
    content_id: int,
    tenantSlug: str,
    data: FoundationContentUpdateRequest,
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
) -> FoundationContent:
    """Update editable content metadata (ADR-029 P1-2).

    - User must belong to tenant
    - User must be the uploader OR have role: admin, curator
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status != ContentStatus.REMOVED,
            )
        )
        content = (await session.execute(stmt)).scalar_one_or_none()
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        is_owner = content.uploader_id == current_user.id
        is_curator_or_admin = current_user.role in ("admin", "curator")
        if not (is_owner or is_curator_or_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to update this content",
            )

        update_data = data.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if key == "privacy" and val is not None:
                setattr(content, key, Privacy(val))
            elif key == "metadata" and val is not None:
                content.metadata_ = val
            elif hasattr(content, key):
                setattr(content, key, val)

        content.updated_at = utc_now()
        await session.flush()

        return content


@router.delete(
    "/content/{content_id}",
    response_model=FoundationContentDeleteResponse,
    summary="Soft-delete content",
)
async def delete_content(
    content_id: int,
    tenantSlug: str,
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
) -> FoundationContentDeleteResponse:
    """Soft-delete content by marking status as REMOVED (ADR-029 P1-2).

    - Preserves audit trail and relational integrity
    - User must be the uploader OR have role: admin, curator
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant.id,
            FoundationContent.status != ContentStatus.REMOVED,
        )
        content = (await session.execute(stmt)).scalar_one_or_none()
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        is_owner = content.uploader_id == current_user.id
        is_curator_or_admin = current_user.role in ("admin", "curator")
        if not (is_owner or is_curator_or_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to delete this content",
            )

        content.status = ContentStatus.REMOVED
        content.updated_at = utc_now()
        await session.flush()

        return FoundationContentDeleteResponse(
            id=content.id,
            status="removed",
            message="Content successfully removed",
        )
