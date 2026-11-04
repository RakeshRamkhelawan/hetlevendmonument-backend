"""GDPR Article 15: Right of Access (audit-trail endpoint).

Routes:
  GET /api/gdpr/audit-trail
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import User

from .dependencies import (
    AuditLog,
    audit_rows_about_user,
    LawfulBasisMissingError,
    LawfulBasisRegistry,
    get_current_tenant_id,
    get_current_user,
    get_db,
    get_lawful_basis_registry,
)
from .schemas import AuditLogEntry, AuditTrailRequest, AuditTrailResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])


def _build_audit_query(
    tenant_id: str, request: AuditTrailRequest, user_id: int
) -> Select[Any]:  # TODO(TYPE): replace Any with concrete type
    """Build audit log query with filters."""
    query = select(AuditLog).filter(AuditLog.tenant_id == tenant_id)
    # Regels VAN de persoon en regels OVER hem (een rol die hij kreeg of verloor), ADR-039.
    query = query.filter(audit_rows_about_user(user_id))

    start_date = request.start_date or (datetime.now(timezone.utc) - timedelta(days=90))
    query = query.filter(AuditLog.timestamp >= start_date)

    if request.end_date:
        query = query.filter(AuditLog.timestamp <= request.end_date)

    if request.action_type:
        query = query.filter(AuditLog.action.ilike("%" + request.action_type + "%"))

    return query


def _convert_audit_logs_to_entries(
    audit_logs: Sequence[AuditLog],
) -> list[AuditLogEntry]:
    """Convert AuditLog database models to API response models."""
    return [
        AuditLogEntry(
            id=str(log.id),
            timestamp=log.timestamp,
            action=log.action if log.action is not None else "unknown",
            resource=log.resource,
            user_id=str(log.user_id) if log.user_id else "system",
            client_ip=log.client_ip,
            details=log.details,
        )
        for log in audit_logs
    ]


@router.get(
    "/audit-trail",
    response_model=AuditTrailResponse,
    summary="Access Audit Trail (GDPR Article 15)",
    description="""
    Retrieve audit trail of all data access and modifications.

    **GDPR Article 15 - Right of Access:**
    - User has right to know what data is being processed
    - User can access audit logs showing data access

    **Features:**
    - Paginated results (max 1000 per page)
    - Filter by date range
    - Filter by action type (create, read, update, delete)

    **Retention:**
    - Audit logs retained for 90 days
    - GDPR-related actions retained for 7 years
    """,
)
async def audit_trail(
    request: AuditTrailRequest = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry),
) -> AuditTrailResponse:
    """Retrieve audit trail for GDPR compliance (Article 15)."""
    try:
        await registry.validate_endpoint_access("/api/gdpr/audit-trail")
    except LawfulBasisMissingError as e:
        logger.error(
            "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=451,
            detail="Data processing is not authorized for this endpoint",
        ) from e
    logger.info("Audit trail requested by user %s for tenant %s", current_user.id, tenant_id)

    try:
        query = _build_audit_query(tenant_id, request, user_id=current_user.id)

        count_query = select(func.count()).select_from(query.subquery())
        total_logs_result = await db.execute(count_query)
        total_logs = total_logs_result.scalar() or 0

        total_pages = (total_logs + request.page_size - 1) // request.page_size
        offset = (request.page - 1) * request.page_size

        query = query.order_by(AuditLog.timestamp.desc()).limit(request.page_size).offset(offset)

        result = await db.execute(query)
        audit_logs = result.scalars().all()

        log_entries = _convert_audit_logs_to_entries(audit_logs)

        logger.info(
            "Audit trail returned %s logs (page %s/%s)",
            len(log_entries),
            request.page,
            total_pages,
        )

        return AuditTrailResponse(
            tenant_id=tenant_id,
            total_logs=total_logs,
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages,
            logs=log_entries,
        )

    except Exception as e:
        logger.error(
            "Audit trail retrieval failed for tenant %s: %s: %s",
            tenant_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal error")
