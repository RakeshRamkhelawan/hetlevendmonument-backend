"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
Integrity Status sub-router (ADR-033 Laag 1).

Routes:
- GET /integrity/status
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger

from src.core.api.v1.compliance.dependencies import (
    HashChainVerifier,
    get_current_user,
    get_hash_chain_verifier,
    governance_read_limit,
)
from src.core.api.v1.compliance.schemas import ChainStatusResponse
from src.core.models.rbac_models import User

integrity_status_router = APIRouter()


@integrity_status_router.get(
    "/integrity/status",
    response_model=ChainStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chain health status",
    description="""
    Returns the overall health status of the audit log hash chain.

    Status values:
    - healthy: No broken entries
    - unverified: Some entries broken (less than 10%)
    - broken: Significant portion of entries broken (10%+)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "Chain status retrieved successfully",
            "model": ChainStatusResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_chain_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    verifier: HashChainVerifier = Depends(get_hash_chain_verifier),
) -> ChainStatusResponse:
    """Get chain health status for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching chain health status",
        tenant_id=tenant_id,
        user_id=current_user.id,
    )

    try:
        result = await verifier.get_chain_status(tenant_id=tenant_id)

        logger.info(
            "Chain status retrieved successfully",
            tenant_id=tenant_id,
            status=result.status,
            total_entries=result.total_entries,
            broken_entries=result.broken_entries_count,
        )

        return ChainStatusResponse(
            status=result.status,
            last_verified_at=result.last_verified_at,
            total_entries=result.total_entries,
            broken_entries_count=result.broken_entries_count,
            unhashed_entries=result.unhashed_entries,
            health_percentage=result.health_percentage,
            tenant_id=result.tenant_id,
            generated_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve chain status: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chain status",
        )
