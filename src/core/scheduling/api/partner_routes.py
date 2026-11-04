"""
API endpoints for Design Partner Program.

Admin-only endpoints for managing partners and viewing feedback.
Partner users can submit feedback via specific endpoints.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user, require_admin
from src.core.database.database import get_db
from src.core.governance.audit import AuditService
from src.core.middleware.rate_limiter import get_limiter

limiter = get_limiter("scheduling")
from src.core.scheduling.partners.repository import PartnerFeedbackRepository, PartnerRepository
from src.core.scheduling.partners.service import PartnerService
from src.core.scheduling.schemas import (
    FeedbackCreateRequest,
    PartnerCreateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduling/partners",
    tags=["Design Partners"],
)


def get_partner_service(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> PartnerService:
    """Dependency to get partner service."""
    return PartnerService(db, current_user.tenant_id)


def get_partner_repo(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> PartnerRepository:
    """Dependency to get partner repository."""
    return PartnerRepository(db, current_user.tenant_id)


def get_feedback_repo(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> PartnerFeedbackRepository:
    """Dependency to get feedback repository."""
    return PartnerFeedbackRepository(db, current_user.tenant_id)


# ========================================================================
# Partner Management (Admin only)
# ========================================================================


@router.post(
    "",
    response_model=dict,
    summary="Register a new design partner",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("10/minute")
async def register_partner(
    request: Request,  # Required by slowapi
    response: Response,
    data: PartnerCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Register a new design partner (admin only).

    Creates a new partner entry and associates it with a tenant.
    """
    try:
        partner = await service.register_partner(
            tenant_id=current_user.tenant_id,
            name=data.name,
            industry=data.industry,
            contact_email=data.contact_email,
            start_date=data.start_date,
            end_date=data.end_date,
            contact_name=data.contact_name,
            max_users=data.max_users,
            allowed_features=data.allowed_features or [],
        )

        # Audit log
        await AuditService.log_action(
            session=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="CREATE",
            resource=f"partner:{partner.id}",
            details={"partner_name": partner.name, "industry": partner.industry},
            description=f"Partner registered: {partner.name}",
        )

        return {
            "success": True,
            "partner_id": partner.id,
            "name": partner.name,
            "status": partner.status,
        }

    except ValueError as exc:
        logger.error("register_partner mislukt: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )


@router.get(
    "",
    response_model=dict,
    summary="List all design partners",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("60/minute")
async def list_partners(
    request: Request,  # Required by slowapi
    response: Response,
    status: str | None = Query(None),
    industry: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    repo: PartnerRepository = Depends(get_partner_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all design partners with optional filters and pagination (admin only)."""
    partners, total = await repo.list_all(
        status=status, industry=industry, page=page, page_size=page_size
    )

    return {
        "partners": [
            {
                "id": p.id,
                "name": p.name,
                "industry": p.industry,
                "contact_email": p.contact_email,
                "status": p.status,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "metrics": {
                    "total_events": p.total_events_created,
                    "api_calls": p.api_calls_count,
                },
            }
            for p in partners
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/overview",
    response_model=dict,
    summary="Get program overview",
    dependencies=[Depends(require_admin)],
)
async def get_program_overview(
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get overview of entire design partner program (admin only)."""
    return await service.get_program_overview()


@router.get(
    "/{partner_id}",
    response_model=dict,
    summary="Get partner details",
    dependencies=[Depends(require_admin)],
)
async def get_partner(
    partner_id: str,
    current_user: UserResponse = Depends(get_current_user),
    repo: PartnerRepository = Depends(get_partner_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed information about a specific partner (admin only)."""
    partner = await repo.get_by_id(partner_id)

    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner not found: {partner_id}",
        )

    return {
        "id": partner.id,
        "tenant_id": partner.tenant_id,
        "name": partner.name,
        "industry": partner.industry,
        "contact_email": partner.contact_email,
        "contact_name": partner.contact_name,
        "status": partner.status,
        "start_date": partner.start_date.isoformat() if partner.start_date else None,
        "end_date": partner.end_date.isoformat() if partner.end_date else None,
        "max_users": partner.max_users,
        "allowed_features": partner.allowed_features,
        "metrics": {
            "total_events_created": partner.total_events_created,
            "total_conflicts_detected": partner.total_conflicts_detected,
            "api_calls_count": partner.api_calls_count,
            "error_count": partner.error_count,
        },
    }


@router.post(
    "/{partner_id}/activate",
    response_model=dict,
    summary="Activate a partner",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("10/minute")
async def activate_partner(
    request: Request,  # Required by slowapi
    response: Response,
    partner_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Activate a partner (move from onboarding to active)."""
    success = await service.activate_partner(partner_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner not found: {partner_id}",
        )

    # Audit log
    await AuditService.log_action(
        session=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="UPDATE",
        resource=f"partner:{partner_id}",
        details={"status_change": "activated"},
        description=f"Partner activated: {partner_id}",
    )

    return {"success": True, "partner_id": partner_id, "status": "active"}


@router.post(
    "/{partner_id}/suspend",
    response_model=dict,
    summary="Suspend a partner",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("10/minute")
async def suspend_partner(
    request: Request,  # Required by slowapi
    response: Response,
    partner_id: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Suspend a partner from the program."""
    reason = data.get("reason", "No reason provided")
    success = await service.suspend_partner(partner_id, reason)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner not found: {partner_id}",
        )

    # Audit log
    await AuditService.log_action(
        session=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="UPDATE",
        resource=f"partner:{partner_id}",
        details={"status_change": "suspended", "reason": reason},
        description=f"Partner suspended: {partner_id}",
    )

    return {"success": True, "partner_id": partner_id, "status": "suspended"}


# ========================================================================
# Feedback Management
# ========================================================================


@router.post(
    "/{partner_id}/feedback",
    response_model=dict,
    summary="Submit feedback",
)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,  # Required by slowapi
    response: Response,
    partner_id: str,
    data: FeedbackCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Submit feedback for a design partner.

    Available to partner users (not just admins).
    """
    try:
        feedback = await service.submit_feedback(
            partner_id=partner_id,
            feedback_type=data.feedback_type,
            severity=data.severity,
            category=data.category,
            title=data.title,
            description=data.description,
            reported_by=str(current_user.id),
            reporter_email=current_user.email,
            reproduction_steps=data.reproduction_steps,
            expected_behavior=data.expected_behavior,
            actual_behavior=data.actual_behavior,
            environment=data.environment,
        )

        # Audit log
        await AuditService.log_action(
            session=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="CREATE",
            resource=f"feedback:{feedback.id}",
            details={
                "partner_id": partner_id,
                "feedback_type": data.feedback_type,
                "severity": data.severity,
            },
            description=f"Feedback submitted for partner {partner_id}",
        )

        return {
            "success": True,
            "feedback_id": feedback.id,
            "priority": feedback.priority,
            "status": feedback.status,
        }

    except ValueError as exc:
        logger.error("submit_feedback mislukt: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )


@router.get(
    "/{partner_id}/feedback",
    response_model=dict,
    summary="List feedback for a partner",
)
@limiter.limit("60/minute")
async def list_partner_feedback(
    request: Request,  # Required by slowapi
    response: Response,
    partner_id: str,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    repo: PartnerFeedbackRepository = Depends(get_feedback_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List feedback entries for a specific partner with pagination."""
    feedback_list, total = await repo.list_by_partner(
        partner_id=partner_id,
        status=status,
        severity=severity,
        page=page,
        page_size=page_size,
    )

    return {
        "feedback": [
            {
                "id": f.id,
                "title": f.title,
                "type": f.feedback_type,
                "severity": f.severity,
                "category": f.category,
                "status": f.status,
                "priority": f.priority,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "assigned_to": f.assigned_to,
            }
            for f in feedback_list
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/feedback/all",
    response_model=dict,
    summary="List all feedback",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("60/minute")
async def list_all_feedback(
    request: Request,  # Required by slowapi
    response: Response,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    repo: PartnerFeedbackRepository = Depends(get_feedback_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all feedback across all partners (admin only) with pagination."""
    feedback_list, total = await repo.list_all(
        status=status,
        severity=severity,
        category=category,
        page=page,
        page_size=page_size,
    )

    return {
        "feedback": [
            {
                "id": f.id,
                "partner_id": f.partner_id,
                "title": f.title,
                "type": f.feedback_type,
                "severity": f.severity,
                "category": f.category,
                "status": f.status,
                "priority": f.priority,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in feedback_list
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/feedback/statistics",
    response_model=dict,
    summary="Get feedback statistics",
    dependencies=[Depends(require_admin)],
)
async def get_feedback_statistics(
    current_user: UserResponse = Depends(get_current_user),
    repo: PartnerFeedbackRepository = Depends(get_feedback_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get feedback statistics (admin only)."""
    return await repo.get_statistics()


@router.post(
    "/feedback/{feedback_id}/assign",
    response_model=dict,
    summary="Assign feedback to engineer",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("20/minute")
async def assign_feedback(
    request: Request,  # Required by slowapi
    response: Response,
    feedback_id: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Assign feedback to an engineer (admin only)."""
    engineer_id = data.get("engineer_id")
    if not engineer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="engineer_id is required",
        )

    success = await service.assign_feedback(feedback_id, engineer_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback not found: {feedback_id}",
        )

    # Audit log
    await AuditService.log_action(
        session=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="UPDATE",
        resource=f"feedback:{feedback_id}",
        details={"assigned_to": engineer_id},
        description=f"Feedback assigned to engineer: {engineer_id}",
    )

    return {"success": True, "feedback_id": feedback_id, "assigned_to": engineer_id}


@router.post(
    "/feedback/{feedback_id}/resolve",
    response_model=dict,
    summary="Resolve feedback",
    dependencies=[Depends(require_admin)],
)
@limiter.limit("20/minute")
async def resolve_feedback(
    request: Request,  # Required by slowapi
    response: Response,
    feedback_id: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Mark feedback as resolved (admin only)."""
    notes = data.get("notes")
    success = await service.resolve_feedback(feedback_id, notes)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback not found: {feedback_id}",
        )

    # Audit log
    await AuditService.log_action(
        session=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="UPDATE",
        resource=f"feedback:{feedback_id}",
        details={"notes": notes},
        description=f"Feedback resolved: {feedback_id}",
    )

    return {"success": True, "feedback_id": feedback_id, "status": "resolved"}


# ========================================================================
# Partner Dashboard
# ========================================================================


@router.get(
    "/{partner_id}/dashboard",
    response_model=dict,
    summary="Get partner dashboard",
)
async def get_partner_dashboard(
    partner_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get dashboard data for a partner."""
    try:
        return await service.get_partner_dashboard(partner_id)
    except ValueError as exc:
        logger.error("get_partner_dashboard mislukt: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Niet gevonden.",
        )
