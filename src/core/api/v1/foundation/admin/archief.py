"""Archief-export (BagIt) voor beheerders van een portaal (ADR-029 Cat 4, BE-EP-054).

- POST   /admin/archief/exports                 maak nu een volledige momentopname
- GET    /admin/archief/exports                 eerdere exports, nieuwste eerst
- GET    /admin/archief/exports/{id}/download   het zip-bestand, na controle van het
                                               controlegetal

Curator of admin, en altijd van DEZE tenant (tenant-match 403, zelfde patroon als curatie).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http_status
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    TRIGGER_HANDMATIG,
    ArchiveExportError,
    AuditService,
    ExportTenant,
    FoundationArchiveExport,
    FoundationArchiveService,
    PortalUser,
    best_effort,
    get_db,
    public_tenant_scope,
    require_curator,
    utc_now,
)
from src.core.api.v1.foundation.schemas import ArchiveExportItem, ArchiveExportListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/archief", tags=["foundation-admin"])

#: Minimale tijd tussen twee handmatige exports van dezelfde tenant. Een export leest de hele
#: collectie in; dubbel klikken of parallelle verzoeken mogen dat niet vermenigvuldigen
#: (Gate 2 HIGH-1 / M5).
_WACHTTIJD = timedelta(minutes=1)

#: Eerste sleutel van het advisory lock (BE-EP-054); de tweede is de tenant-id. Zo wachten
#: gelijktijdige exports van dezelfde tenant op elkaar en ziet de tweede de rij van de eerste
#: (Gate 2 ronde 2, MEDIUM-A). Transactie-gebonden: vrij na commit of rollback.
_SLOT_SLEUTEL = 54


def _eigen_tenant(current_user: PortalUser, tenant_id: int) -> None:
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )


@router.post(
    "/exports",
    response_model=ArchiveExportItem,
    status_code=http_status.HTTP_201_CREATED,
    summary="Maak nu een BagIt-archiefexport van de publieke collectie",
)
async def create_archive_export(
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> FoundationArchiveExport:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(current_user, tenant.id)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": _SLOT_SLEUTEL, "b": tenant.id}
        )
        nu = utc_now()
        laatste = (
            await session.execute(
                select(func.max(FoundationArchiveExport.created_at)).where(
                    FoundationArchiveExport.tenant_id == tenant.id
                )
            )
        ).scalar_one_or_none()
        if laatste is not None and nu - laatste < _WACHTTIJD:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Er is net een archiefexport gemaakt; probeer het over een minuut opnieuw.",
            )
        dienst = FoundationArchiveService()
        export: FoundationArchiveExport | None = None
        try:
            export = await dienst.export(
                session=session,
                tenant=ExportTenant(id=tenant.id, slug=tenant.slug, name=tenant.name),
                now=nu,
                trigger=TRIGGER_HANDMATIG,
                portal_user_id=current_user.id,
            )
            await session.commit()
        except (ArchiveExportError, SQLAlchemyError) as e:
            await session.rollback()
            if export is not None:
                # De rij is teruggedraaid; het pakket mag dan niet blijven staan.
                await dienst.discard(export)
            logger.error(
                "archive_export_failed tenant_id=%s: %s: %s",
                tenant.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="De archiefexport is mislukt; er is niets opgeslagen.",
            ) from e

        async with best_effort("audit_archive_export_created", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="foundation_archive_export_created",
                severity="medium",
                source_ip="internal",
                endpoint=f"/{tenantSlug}/foundation/admin/archief/exports",
                description=f"Archiefexport {export.bag_name} met {export.item_count} items",
                user_id=None,
                tenant_id=tenant.id,
                action="archive_export",
                resource=f"foundation_archive_export:{export.id}",
                metadata={
                    "portal_user_id": current_user.id,
                    "sha256": export.sha256,
                    "item_count": export.item_count,
                },
            )
        return export


@router.get(
    "/exports",
    response_model=ArchiveExportListResponse,
    summary="Eerdere archiefexports, nieuwste eerst",
)
async def list_archive_exports(
    tenantSlug: str,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> ArchiveExportListResponse:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(current_user, tenant.id)
        totaal = (
            await session.execute(
                select(func.count(FoundationArchiveExport.id)).where(
                    FoundationArchiveExport.tenant_id == tenant.id
                )
            )
        ).scalar_one()
        rijen = (
            await session.execute(
                select(FoundationArchiveExport)
                .where(FoundationArchiveExport.tenant_id == tenant.id)
                .order_by(FoundationArchiveExport.created_at.desc(), FoundationArchiveExport.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return ArchiveExportListResponse(
            items=[ArchiveExportItem.model_validate(r) for r in rijen],
            total=int(totaal),
            limit=limit,
            offset=offset,
        )


@router.get(
    "/exports/{export_id}/download",
    summary="Download een archiefexport (zip, BagIt 1.0)",
    response_class=Response,
)
async def download_archive_export(
    tenantSlug: str,
    export_id: int,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> Response:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(current_user, tenant.id)
        export = (
            await session.execute(
                select(FoundationArchiveExport).where(
                    FoundationArchiveExport.id == export_id,
                    FoundationArchiveExport.tenant_id == tenant.id,
                )
            )
        ).scalar_one_or_none()
        if export is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Archiefexport niet gevonden"
            )
        try:
            data = await FoundationArchiveService().read_archive(export)
        except ArchiveExportError as e:
            logger.error(
                "archive_download_failed export_id=%s: %s: %s",
                export.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="Het archiefpakket is niet beschikbaar of niet meer ongeschonden.",
            ) from e
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{export.bag_name}.zip"',
                "X-Content-SHA256": export.sha256,
            },
        )
