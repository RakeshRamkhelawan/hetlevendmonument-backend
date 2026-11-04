# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/company/
# orphan:exempt -- registered dynamically via importlib in company registry
"""
Pack Feedback API Endpoints -- deprecated proxy stubs.

Verboden imports (ADR-033) vervangen door v1/company/dependencies.py facade.
Gebruik v1/company/ routers wanneer beschikbaar (SP-API-011).
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.api.dependencies import get_db
from src.core.api.v1.company.dependencies import (
    GlobalPack,
    PackFeedback,
    audit_service,
    controleer_resource_recht,
    require_resource_permission,
    validate_csrf_token,
)
from src.core.middleware.tenant_context import require_tenant_id
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pack-feedback", tags=["pack-feedback"])


# =============================================================================
# Pydantic Models
# =============================================================================


class PackFeedbackRequest(BaseModel):
    """User feedback on a pack template match"""

    session_id: str = Field(..., description="Chat/session ID")
    pack_id: str = Field(..., description="ID of the pack that was used")
    original_prompt: str = Field(..., description="Original user prompt")
    was_helpful: bool = Field(..., description="Whether the pack was helpful")
    rating: int | None = Field(None, ge=1, le=5, description="1-5 star rating")
    feedback_text: str | None = Field(None, description="Optional detailed feedback")
    used_as_is: bool = Field(False, description="Whether user used template without changes")
    customizations_made: list[str] = Field(
        default_factory=list, description="List of customizations made"
    )


class PackFeedbackResponse(BaseModel):
    """Response after submitting feedback"""

    success: bool
    message: str
    feedback_id: str | None = None


class GlobalPackContributionRequest(BaseModel):
    """Request to contribute an AI-customized pack to global repository"""

    name: str = Field(..., description="Name for the new pack")
    description: str = Field(..., description="Description of what this pack does")
    department: str = Field(..., description="Department category")
    source_pack_ids: list[str] = Field(default_factory=list, description="Source packs used")
    workflow_definition: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="React Flow graph definition"
    )  # TODO(TYPE): replace Any with concrete type
    intent_tags: list[str] = Field(default_factory=list, description="Keywords for matching")
    capabilities: list[str] = Field(default_factory=list, description="Pack capabilities")
    is_public: bool = Field(True, description="Whether other tenants can see this")


class GlobalPackContributionResponse(BaseModel):
    """Response after contributing a pack"""

    success: bool
    pack_id: str
    message: str
    review_status: str = Field("pending", description="pending, approved, or rejected")


class GlobalPackSearchRequest(BaseModel):
    """Search global packs"""

    query: str
    department: str | None = None
    limit: int = Field(10, ge=1, le=50)


class GlobalPackInfo(BaseModel):
    """Info about a global pack"""

    id: str
    name: str
    description: str
    department: str
    capabilities: list[str]
    intent_tags: list[str]
    usage_count: int
    average_rating: float
    contributed_by: str | None = None
    created_at: str


# =============================================================================
# Helper functions
# =============================================================================


async def _kan_pakketten_beheren(db: AsyncSession, current_user: UserResponse, tenant_id: int) -> bool:
    """Heeft deze gebruiker `packs:manage` (beheer)? Alleen dan ziet hij ook wachtende pakketten.

    Dezelfde controle als de route-dependency `require_resource_permission("packs", "manage")`,
    maar als ja/nee: zoeken en ophalen zijn er voor iedereen, alleen de uitkomst verschilt.
    """
    try:
        await controleer_resource_recht(db, int(current_user.id), tenant_id, "packs", "manage")
    except HTTPException:
        return False
    return True


def _global_pack_to_info(
    pack: GlobalPack,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Serialize a GlobalPack ORM object to a plain dict."""
    data: dict[str, Any] = pack.pack_data
    total_ratings = data.get("total_ratings", 0)
    sum_ratings = data.get("sum_ratings", 0)
    avg_rating = sum_ratings / max(total_ratings, 1) if total_ratings > 0 else 0.0
    return {
        "id": str(pack.id),
        "name": pack.name,
        "description": pack.description or "",
        "department": data.get("department", ""),
        "capabilities": data.get("capabilities", []),
        "intent_tags": data.get("intent_tags", []),
        "usage_count": data.get("usage_count", 0),
        "average_rating": avg_rating,
        "contributed_by": str(pack.contributor_user_id) if pack.contributor_user_id else None,
        "created_at": pack.created_at.isoformat() if pack.created_at else "",
    }


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/submit", response_model=PackFeedbackResponse)
async def submit_feedback(
    request: PackFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: UserResponse = Depends(get_current_user),
) -> PackFeedbackResponse:
    """
    Submit feedback on a pack template match.
    Used to improve pack matching accuracy over time.
    """
    if request.rating is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Rating is required",
        )

    try:
        feedback = PackFeedback(
            tenant_id=tenant_id,
            user_id=current_user.id,
            pack_id=request.pack_id,
            rating=request.rating,
            comment=request.feedback_text,
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)

        async with best_effort("pack feedback audit", db_session=db):
            logger.info(
                "Pack feedback submitted: tenant_id=%s user_id=%s pack_id=%s rating=%s",
                tenant_id,
                current_user.id,
                request.pack_id,
                request.rating,
            )

        return PackFeedbackResponse(
            success=True,
            message="Thank you for your feedback! It helps improve pack matching.",
            feedback_id=str(feedback.id),
        )

    except Exception as e:
        logger.error(
            "Failed to submit feedback: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback",
        ) from e


@router.get("/stats/{pack_id}")
async def get_pack_feedback_stats(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get feedback statistics for a specific pack."""
    result = await db.execute(
        select(
            func.count().label("total_feedback"),
            func.avg(PackFeedback.rating).label("average_rating"),
            func.count(PackFeedback.rating).label("total_ratings"),
        ).where(
            PackFeedback.pack_id == pack_id,
            PackFeedback.tenant_id == tenant_id,
        )
    )
    row = result.one()

    return {
        "success": True,
        "data": {
            "pack_id": pack_id,
            "total_feedback": row.total_feedback,
            "average_rating": (
                float(row.average_rating) if row.average_rating is not None else None
            ),
            "total_ratings": row.total_ratings,
        },
    }


@router.post("/contribute", response_model=GlobalPackContributionResponse)
async def contribute_global_pack(
    request: GlobalPackContributionRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: UserResponse = Depends(get_current_user),
) -> GlobalPackContributionResponse:
    """
    Contribute an AI-customized workflow as a global pack.
    Other tenants can then use this pack as a template.
    """
    try:
        pack = GlobalPack(
            tenant_id=tenant_id,
            contributor_user_id=current_user.id,
            name=request.name,
            description=request.description,
            pack_data={
                "department": request.department,
                "workflow_definition": request.workflow_definition,
                "capabilities": request.capabilities,
                "intent_tags": request.intent_tags,
                "source_pack_ids": request.source_pack_ids,
                "is_public": request.is_public,
                "status": "pending_review",
                "usage_count": 0,
                "total_ratings": 0,
                "sum_ratings": 0,
            },
        )
        db.add(pack)
        await db.commit()
        await db.refresh(pack)

        async with best_effort("pack contribution audit", db_session=db):
            logger.info(
                "Global pack contributed: tenant_id=%s user_id=%s pack_id=%s",
                tenant_id,
                current_user.id,
                pack.id,
            )

        return GlobalPackContributionResponse(
            success=True,
            pack_id=str(pack.id),
            message=(
                f"Thank you! Your pack '{request.name}' has been submitted for review. "
                f"Once approved, other users can benefit from your workflow."
            ),
            review_status="pending",
        )

    except Exception as e:
        logger.error(
            "Failed to contribute global pack: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to contribute pack",
        ) from e


@router.post("/global/search")
async def search_global_packs(
    request: GlobalPackSearchRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: UserResponse = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Search the global pack repository.

    Een gewone gebruiker vindt alleen goedgekeurde pakketten; wie `packs:manage` heeft ook de
    wachtende. Het totaal telt het verborgen werk niet mee, anders verraadt het dat het bestaat.
    """
    query_lower = f"%{request.query.lower()}%"

    # Build base filter
    stmt = select(GlobalPack).where(GlobalPack.tenant_id == tenant_id)
    if not await _kan_pakketten_beheren(db, current_user, tenant_id):
        stmt = stmt.where(GlobalPack.pack_data["status"].astext == "approved")

    if request.department:
        stmt = stmt.where(GlobalPack.pack_data["department"].astext == request.department)

    stmt = stmt.where(
        (func.lower(GlobalPack.name).like(query_lower))
        | (func.lower(GlobalPack.description).like(query_lower))
    )

    # Total count for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar() or 0

    # Paginated results
    stmt = stmt.order_by(GlobalPack.created_at.desc()).offset(offset).limit(request.limit)
    result = await db.execute(stmt)
    packs = result.scalars().all()

    return {
        "success": True,
        "data": [_global_pack_to_info(p) for p in packs],
        "total": total_count,
        "limit": request.limit,
        "offset": offset,
    }


@router.get(
    "/global/pending",
    dependencies=[Depends(require_resource_permission("packs", "manage"))],
)
async def get_pending_packs(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get packs pending review (alleen met `packs:manage`, het beheer van pakketten)."""
    stmt = (
        select(GlobalPack)
        .where(
            GlobalPack.tenant_id == tenant_id,
            GlobalPack.pack_data["status"].astext == "pending_review",
        )
        .order_by(GlobalPack.created_at.desc())
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar() or 0

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    packs = result.scalars().all()

    return {
        "success": True,
        "data": [_global_pack_to_info(p) for p in packs],
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/global/{pack_id}/approve",
    dependencies=[
        Depends(require_resource_permission("packs", "manage")),
        Depends(validate_csrf_token),
    ],
)
async def approve_global_pack(
    pack_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Approve a pending global pack (admin only).

    Dit is BEHEER (een pakket vrijgeven voor de hele klant), geen procesgoedkeuring: het vraagt
    `packs:manage`, dat alleen de beheerder (`*:*`) heeft (ADR-039; Rakesh 2026-10-09: "een
    beheerder ... beheert het pakket"). De rol- en CSRF-controle staan als route-dependency, dus
    een geweigerde aanvraag raakt het pakket niet.
    """
    result = await db.execute(
        select(GlobalPack).where(
            GlobalPack.id == pack_id,
            GlobalPack.tenant_id == tenant_id,
        )
    )
    pack = result.scalar_one_or_none()
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pack not found",
        )

    pack.pack_data = {**pack.pack_data, "status": "approved"}
    flag_modified(pack, "pack_data")
    await db.commit()

    # Een ECHTE auditregel (hash-keten). Hier stond alleen een `logger.info` in `best_effort`,
    # wat geen spoor in de audit-tabel achterlaat. De primaire wijziging is hierboven al
    # vastgelegd; faalt de auditregel, dan blijft de vrijgave staan (best_effort). De regel zelf
    # wordt door `get_db` vastgelegd (`database.py`: `await session.commit()` na de `yield`, gelezen 2026-10-10).
    async with best_effort("global_pack.approved audit log", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="global_pack.approved",
            resource=f"global_pack:{pack_id}",
            user_id=current_user.id,
            details={"pack_name": pack.name},
            session=db,
        )
    logger.info(
        "Global pack approved: tenant_id=%s pack_id=%s approved_by=%s",
        tenant_id,
        pack_id,
        current_user.id,
    )

    return {
        "success": True,
        "data": {"message": f"Pack {pack_id} approved"},
    }


@router.get("/global/{pack_id}")
async def get_global_pack(
    pack_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get a specific global pack.

    Een gewone gebruiker krijgt een pakket dat nog niet is goedgekeurd als 404 (niet 403: het
    bestaan wordt niet prijsgegeven); wie `packs:manage` heeft ziet alles.
    """
    result = await db.execute(
        select(GlobalPack).where(
            GlobalPack.id == pack_id,
            GlobalPack.tenant_id == tenant_id,
        )
    )
    pack = result.scalar_one_or_none()
    if pack is not None and pack.pack_data.get("status") != "approved":
        if not await _kan_pakketten_beheren(db, current_user, tenant_id):
            pack = None
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pack not found",
        )

    _pd: dict[str, Any] = pack.pack_data  # TODO(TYPE): replace Any with concrete type
    pack.pack_data = {**_pd, "usage_count": _pd.get("usage_count", 0) + 1}
    flag_modified(pack, "pack_data")
    await db.commit()

    return {"success": True, "data": _global_pack_to_info(pack)}
