"""Board API Router - REST endpoints for board governance.

Provides endpoints for:
- Getting approval queue
- Approving/rejecting decisions
- Viewing decision history

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md section 7.4
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md section 7.1
"""

from typing import Any, List, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.auth.api_deps import get_current_user
from src.core.company.schemas import (
    BoardApproveRequest,
    BoardDecisionResponse,
    BoardQueueResponse,
    BoardRejectRequest,
)
from src.core.container import container
from src.core.api.v1.company.dependencies import (
    COUNCIL_TURNS_TOTAL,
    BoardRoleError,
    BoardService,
    BoardServiceError,
    DatabaseManager,
    GoldenRuleR3Violation,
    PolicyEngine,
)
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.core.models.rbac_models import User

router = APIRouter(
    prefix="/board",
    tags=["board-governance"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_board_service(
    current_user: User = Depends(get_current_user),
) -> BoardService:
    """Get board service with tenant context."""
    from src.core.container import TenantContext

    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )

    # Get policy engine from container or create default
    policy_engine = getattr(container, "policy_engine", None)
    if policy_engine is None:
        policy_engine = PolicyEngine()

    # Cast container's DatabaseManager to the expected type from database module
    # Both classes have compatible interfaces (get_session(), health_check())
    db_manager = cast(DatabaseManager, container.database_manager())

    return BoardService(
        db_manager=db_manager,
        policy_engine=policy_engine,
        tenant_context=tenant_context,
    )


@router.get(
    "/queue",
    response_model=BoardQueueResponse,
    summary="Get approval queue for current user",
    responses={
        200: {"description": "Pending decisions for user's board roles"},
        401: {"description": "Not authenticated"},
    },
)
async def get_approval_queue(
    current_user: User = Depends(get_current_user),
    service: BoardService = Depends(get_board_service),
) -> BoardQueueResponse:
    """Get pending board decisions for the current user's board roles.

    Returns all pending decisions that the current user is authorized
    to approve or reject based on their board role assignments.
    """
    try:
        return await service.get_queue(current_user.id)
    except BoardServiceError as e:
        # Council observability: track board/queue errors (B-003 fix)
        COUNCIL_TURNS_TOTAL.labels(
            tenant_id=str(current_user.tenant_id),
            verdict="error",
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/decisions/{decision_id}/approve",
    response_model=BoardDecisionResponse,
    summary="Approve a board decision",
    responses={
        200: {"description": "Decision approved"},
        403: {"description": "User doesn't have required board role"},
        404: {"description": "Decision not found"},
        409: {"description": "Decision already decided"},
    },
)
async def approve_decision(
    decision_id: UUID,
    request: BoardApproveRequest,
    current_user: User = Depends(get_current_user),
    service: BoardService = Depends(get_board_service),
) -> BoardDecisionResponse:
    """Approve a pending board decision.

    The current user must have the required board role for the decision.
    Reason is optional for approvals.
    """
    try:
        decision = await service.approve(
            decision_id=decision_id,
            user_id=current_user.id,
            reason=request.reason,
        )
        return BoardDecisionResponse.model_validate(decision)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except BoardRoleError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except BoardServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/decisions/{decision_id}/reject",
    response_model=BoardDecisionResponse,
    summary="Reject a board decision",
    responses={
        200: {"description": "Decision rejected"},
        403: {"description": "User doesn't have required board role"},
        404: {"description": "Decision not found"},
        409: {"description": "Decision already decided"},
        422: {"description": "Reason is required for rejection"},
    },
)
async def reject_decision(
    decision_id: UUID,
    request: BoardRejectRequest,
    current_user: User = Depends(get_current_user),
    service: BoardService = Depends(get_board_service),
) -> BoardDecisionResponse:
    """Reject a pending board decision.

    The current user must have the required board role for the decision.
    Reason is **required** for rejections.
    """
    try:
        decision = await service.reject(
            decision_id=decision_id,
            user_id=current_user.id,
            reason=request.reason,
        )
        return BoardDecisionResponse.model_validate(decision)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except BoardRoleError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    except BoardServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/decisions",
    response_model=list[BoardDecisionResponse],
    summary="Get decision history for company",
    responses={
        200: {"description": "List of decisions"},
        401: {"description": "Not authenticated"},
    },
)
async def get_decision_history(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BoardService = Depends(get_board_service),
) -> list[BoardDecisionResponse]:
    """Get all board decisions for a company.

    Returns all decisions (pending, approved, rejected) sorted by date
    (newest first).
    """
    try:
        decisions = await service.get_history(company_id)
        return decisions
    except BoardServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Additional utility endpoint for checking board roles
@router.get(
    "/roles",
    response_model=list[str],
    summary="Get current user's board roles",
)
async def get_my_board_roles(
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """Get the board roles assigned to the current user.

    Useful for debugging and UI adaptation based on user's
    governance permissions.
    """
    # Map user roles to board roles
    board_roles: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for role in current_user.roles:
        role_name = role.name.lower()
        if role_name in ["cfo", "cto", "ceo", "chro", "ciso"]:
            board_roles.append(role_name.upper())
        elif role_name in ["admin", "system_admin", "tenant_admin"]:
            # Admin has all board roles
            board_roles.extend(["CFO", "CTO", "CEO", "CHRO", "CISO"])
        elif "finance" in role_name:
            board_roles.append("CFO")
        elif "tech" in role_name or "it" in role_name:
            board_roles.append("CTO")
        elif "hr" in role_name or "people" in role_name:
            board_roles.append("CHRO")
        elif "security" in role_name:
            board_roles.append("CISO")

    return list(set(board_roles))
