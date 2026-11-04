"""Goal API Router - Fase 3.3

REST endpoints for goal management with hierarchy support.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.auth.api_deps import get_current_user
from src.core.company.goal_service import GoalService
from src.core.company.schemas import (
    GoalAncestryResponse,
    GoalCreate,
    GoalResponse,
    GoalTreeResponse,
    GoalUpdate,
)
from src.core.container import TenantContext, container
from src.core.models.rbac_models import User
import logging
from src.core.exceptions import ValidatieFout

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/goals",
    tags=["goals"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_goal_service(current_user: User = Depends(get_current_user)) -> GoalService:
    """Get goal service with tenant context from current user."""
    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )
    return GoalService(
        db_manager=container.database_manager(),
        tenant_context=tenant_context,
    )


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal",
)
async def create_goal(
    company_id: UUID,
    data: GoalCreate,
    service: GoalService = Depends(get_goal_service),
) -> GoalResponse:
    """Create a new goal with hierarchy validation.

    Goal types must follow hierarchy: mission -> strategic -> project -> task
    - Mission: no parent, max 1 per company
    - Strategic: parent must be mission
    - Project: parent must be strategic
    - Task: parent must be project
    """
    try:
        return await service.create_goal(company_id, data)
    except ValueError as e:
        # Check error type for appropriate status code
        logger.error("create_goal mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        # Besturing op de tekst van de eigen validatiefout; de tekst zelf gaat niet naar de klant.
        if "already has a mission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflict.",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ongeldige invoer.",
        )


@router.get(
    "/tree",
    response_model=GoalTreeResponse,
    summary="Get goal tree for company",
)
async def get_goal_tree(
    company_id: UUID,
    service: GoalService = Depends(get_goal_service),
) -> GoalTreeResponse:
    """Get all goals for a company as a tree structure."""
    return await service.get_goal_tree(company_id)


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Get goal by ID",
)
async def get_goal(
    goal_id: UUID,
    service: GoalService = Depends(get_goal_service),
) -> GoalResponse:
    """Get goal by ID."""
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    return goal


@router.get(
    "/{goal_id}/ancestry",
    response_model=GoalAncestryResponse,
    summary="Get goal ancestry chain",
)
async def get_goal_ancestry(
    goal_id: UUID,
    service: GoalService = Depends(get_goal_service),
) -> GoalAncestryResponse:
    """Get goal ancestry chain from goal up to mission.

    Returns the complete chain of parent goals, useful for context building.
    """
    return await service.get_ancestry(goal_id)


@router.put(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Update goal",
)
async def update_goal(
    goal_id: UUID,
    data: GoalUpdate,
    service: GoalService = Depends(get_goal_service),
) -> GoalResponse:
    """Update goal fields.

    Note: goal_type cannot be changed after creation.
    Parent changes require careful consideration of hierarchy.
    """
    try:
        return await service.update_goal(goal_id, data)
    except ValueError as e:
        logger.error("update_goal mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Niet gevonden.",
        )


@router.put(
    "/{goal_id}/progress",
    response_model=GoalResponse,
    summary="Update goal progress",
)
async def update_progress(
    goal_id: UUID,
    progress: int = Query(..., ge=0, le=100, description="Progress percentage (0-100)"),
    service: GoalService = Depends(get_goal_service),
) -> GoalResponse:
    """Update goal progress and propagate to parents.

    Progress is automatically propagated up the goal hierarchy:
    - Parent progress = average of all children
    """
    try:
        return await service.update_progress(goal_id, progress)
    except ValueError as e:
        logger.error("update_progress mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete goal",
    response_class=Response,
)
async def delete_goal(
    goal_id: UUID,
    service: GoalService = Depends(get_goal_service),
) -> None:
    """Delete goal if it has no children.

    Goals with children cannot be deleted to maintain hierarchy integrity.
    """
    try:
        await service.delete_goal(goal_id)
    except ValidatieFout as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ValueError as e:
        logger.error("delete_goal mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )
