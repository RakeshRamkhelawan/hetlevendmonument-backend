"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
User list/create sub-router (ADR-033 Laag 1).

Routes:
- POST /
- GET /
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.api.v1.users.dependencies import (
    AuthService,
    AuthUserCreate,
    get_current_user,
    get_db,
    stuur_uitnodiging,
)
from src.core.api.v1.users.schemas import UserCreate, UserListResponse, UserResponse
from src.core.api.v1.users.shared import (
    _get_tenant_scoped_roles,
    can_manage_users,
    has_role,
    require_user_manager,
)
from src.core.api.v1.users.dependencies import is_platform_superuser
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

users_list_router = APIRouter()


@users_list_router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user in a tenant. Requires admin or superuser privileges.",
    dependencies=[Depends(require_user_manager)],
)
async def create_user(
    data: UserCreate,
    target_tenant_id: int = Query(..., ge=1, description="Tenant ID to create the user in"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Create a new user in a tenant."""
    # Dubbel met `require_user_manager` op de route (403 voor de body).
    if not can_manage_users(current_user, target_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create users in this tenant",
        )

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{data.email}' already exists",
        )

    # De rollen EERST toetsen (een platformrol mag deze aanvrager niet uitdelen), voor er een gebruiker bestaat:
    # een 403 mag geen half aangemaakte gebruiker achterlaten.
    gevraagde_rollen = (
        await _get_tenant_scoped_roles(
            db, target_tenant_id, data.role_ids, actor_id=int(current_user.id)
        )
        if data.role_ids
        else []
    )

    # Zonder wachtwoord wordt de medewerker UITGENODIGD: een willekeurig, onbekend startwachtwoord (met
    # hoofdletter, kleine letter en cijfer, zodat het aan de regels voldoet) en een eenmalige link
    # waarmee hij zelf een wachtwoord kiest. Zonder die link kan niemand inloggen.
    uitnodigen = data.password is None
    wachtwoord = data.password if data.password is not None else secrets.token_urlsafe(24) + "Aa1"
    auth_service = AuthService()
    auth_payload = AuthUserCreate(email=data.email, password=wachtwoord, role_name="user")
    created_user = await auth_service.create_user(
        db=db,
        user_data=auth_payload,
        tenant_id=target_tenant_id,
        request_path="/api/v1/users",
    )

    if not created_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create user",
        )

    created_user_result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == created_user.id)
    )
    user = created_user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create user",
        )

    if gevraagde_rollen:
        user.roles.extend(gevraagde_rollen)
        await db.commit()

    await db.refresh(user, attribute_names=["roles"])

    logger.info("User %s created by user %s", user.id, current_user.id)
    antwoord = UserResponse.model_validate(user)
    if uitnodigen:
        antwoord.invitation_email_sent = await stuur_uitnodiging(user.email, user.id)
    return antwoord


@users_list_router.get(
    "/",
    response_model=UserListResponse,
    summary="List users",
    description="List users in a tenant. Regular users see only themselves, admins see all in tenant.",
)
async def list_users(
    tenant_id: int | None = Query(None, description="Filter by tenant ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of items"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserListResponse:
    """List users with filtering and pagination."""
    if is_platform_superuser(current_user):
        target_tenant_id = tenant_id
    else:
        target_tenant_id = int(current_user.tenant_id)

        if not has_role(current_user, "admin") and not has_role(current_user, "TenantAdmin"):
            own_result = await db.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == current_user.id, User.tenant_id == target_tenant_id)
            )
            own_user = own_result.scalar_one_or_none()
            if own_user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            return UserListResponse(
                data=[UserResponse.model_validate(own_user)],
                total=1,
                page=1,
                per_page=limit,
            )

    query = select(User).options(selectinload(User.roles))
    count_query = select(func.count(User.id))

    if target_tenant_id:
        query = query.where(User.tenant_id == target_tenant_id)
        count_query = count_query.where(User.tenant_id == target_tenant_id)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        data=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        per_page=limit,
    )
