"""
# orphan:exempt reason: legacy pre-ADR-033 endpoint, pending Strangler Fig migration
FastAPI Router for Domain Packs API
Provides REST endpoints for managing domain packs
"""

from typing import Any
from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.auth.api_deps import is_platform_superuser
from src.core.observability.evaluation_repository import EvaluationRepository
from src.core.procedures.domain_pack_repository import DomainPackRepository
from src.core.procedures.schemas import DomainPackCreate, DomainPackRead, DomainPackUpdate


async def get_domain_pack_repo(
    db: AsyncSession = Depends(get_db),
) -> DomainPackRepository:
    return DomainPackRepository(db)


async def get_evaluation_repo(
    db: AsyncSession = Depends(get_db),
) -> EvaluationRepository:
    return EvaluationRepository(db)


async def require_domain_pack_admin(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Rolcontrole voor de vier schrijfroutes, als dependency (plan nazorg, punt d).

    Stond tot 2026-10-08 letterlijk in elke handler, dus NA de validatie van de body: een
    niet-beheerder kreeg 422 met het schema in plaats van 403. De controle zelf is ongewijzigd:
    de spelling `tenant_admin` met underscore is een eigen vocabulaire, zie
    `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` in
    `tests/architecture/test_admin_checks_use_the_central_definition.py`.
    """
    if "tenant_admin" not in current_user.roles and not is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user


_ALLEEN_BEHEERDER = [Depends(require_domain_pack_admin)]


router = APIRouter(
    prefix="/api/v1/domain-packs",
    tags=["domain-packs"],
    responses={401: {"description": "Unauthorized"}, 404: {"description": "Not found"}},
)


@router.get("/stats", response_model=dict[str, Any])  # TODO(TYPE): replace Any with concrete type
async def get_domain_pack_stats(
    current_user: UserResponse = Depends(get_current_user),
    eval_repo: EvaluationRepository = Depends(get_evaluation_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get overall domain pack statistics for current tenant."""
    return await eval_repo.get_overall_stats(current_user.tenant_id)


@router.get("", response_model=list[DomainPackRead])
async def list_domain_packs(
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
) -> Sequence[DomainPackRead]:
    """List domain packs for current tenant."""
    packs = await repo.list_by_tenant(current_user.tenant_id)
    paged = packs[offset : offset + limit]
    return [DomainPackRead.model_validate(p) for p in paged]


@router.get("/{pack_id}", response_model=DomainPackRead)
async def get_domain_pack(
    pack_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
) -> DomainPackRead:
    """Get a specific domain pack."""
    pack = await repo.get_by_id(current_user.tenant_id, pack_id)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    return DomainPackRead.model_validate(pack)


@router.post("", response_model=DomainPackRead, status_code=status.HTTP_201_CREATED, dependencies=_ALLEEN_BEHEERDER)
async def create_domain_pack(
    data: DomainPackCreate,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
    db: AsyncSession = Depends(get_db),
) -> DomainPackRead:
    """Create a new domain pack. Requires tenant_admin role."""
    pack = await repo.create(current_user.tenant_id, data)
    await db.commit()
    return DomainPackRead.model_validate(pack)


@router.put("/{pack_id}", response_model=DomainPackRead, dependencies=_ALLEEN_BEHEERDER)
async def update_domain_pack(
    pack_id: UUID,
    data: DomainPackUpdate,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
    db: AsyncSession = Depends(get_db),
) -> DomainPackRead:
    """Update a domain pack."""
    pack = await repo.update(current_user.tenant_id, pack_id, data)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    await db.commit()
    return DomainPackRead.model_validate(pack)


@router.post("/{pack_id}/archive", status_code=status.HTTP_200_OK, response_model=DomainPackRead, dependencies=_ALLEEN_BEHEERDER)
async def archive_domain_pack(
    pack_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
    db: AsyncSession = Depends(get_db),
) -> DomainPackRead:
    """Archive (deprecate) a domain pack."""
    pack = await repo.archive(current_user.tenant_id, pack_id)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    await db.commit()
    return DomainPackRead.model_validate(pack)


@router.get("/{pack_id}/health", response_model=dict[str, Any])  # TODO(TYPE): replace Any with concrete type
async def get_domain_pack_health(
    pack_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
    eval_repo: EvaluationRepository = Depends(get_evaluation_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get health status of a specific domain pack."""
    pack = await repo.get_by_id(current_user.tenant_id, pack_id)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    return await eval_repo.get_pack_health(pack_id, current_user.tenant_id)


@router.post("/{pack_id}/restore", status_code=status.HTTP_200_OK, response_model=DomainPackRead, dependencies=_ALLEEN_BEHEERDER)
async def restore_domain_pack(
    pack_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    repo: DomainPackRepository = Depends(get_domain_pack_repo),
    db: AsyncSession = Depends(get_db),
) -> DomainPackRead:
    """Restore a deprecated domain pack to active status."""
    pack = await repo.get_by_id(current_user.tenant_id, pack_id)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    update_data = DomainPackUpdate(status="active", department=None, description=None)
    pack = await repo.update(current_user.tenant_id, pack_id, update_data)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain pack {pack_id} not found",
        )
    await db.commit()
    return DomainPackRead.model_validate(pack)
