"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
User detail/update/delete sub-router (ADR-033 Laag 1).

Routes:
- GET /{user_id}
- PUT /{user_id}
- DELETE /{user_id}
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.api.v1.users.dependencies import RBACService, get_current_user, get_db
from src.core.api.v1.users.schemas import UserResponse, UserUpdate
from src.core.api.v1.users.shared import (
    _get_tenant_scoped_roles,
    can_manage_users,
    eis_dat_gebruiker_uitgeschakeld_mag_worden,
    eis_dat_profiel_gewijzigd_mag_worden,
    eis_dat_rollen_gewijzigd_mag_worden,
    has_role,
)
from src.core.api.v1.users.dependencies import is_platform_superuser
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

users_detail_router = APIRouter()


@users_detail_router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Get detailed information about a specific user.",
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get a specific user by ID."""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    if not is_platform_superuser(current_user):
        if current_user.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access users in your own tenant",
            )
        if current_user.id != user_id and not has_role(current_user, "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own user data",
            )

    return UserResponse.model_validate(user)


@users_detail_router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
    description="Update user information.",
)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    *,
    request: Request,
) -> UserResponse:
    """Update a user's information."""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    if not is_platform_superuser(current_user):
        if current_user.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only modify users in your own tenant",
            )
        if current_user.id != user_id and not can_manage_users(current_user, int(user.tenant_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to modify this user",
            )

    if data.email and data.email != user.email:
        # Het adres van een platformbeheerder wijzigt alleen wie de platformrol zelf heeft: zonder dit is
        # "wachtwoord vergeten" een accountovername (brief 2026-10-19). Voor de eerste `setattr`.
        await eis_dat_profiel_gewijzigd_mag_worden(
            db, request, int(current_user.id), int(user.id), int(user.tenant_id)
        )
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{data.email}' is already in use",
            )
        setattr(user, "email", data.email)

    if data.is_active is not None and data.is_active != user.is_active:
        if not can_manage_users(current_user, int(user.tenant_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user active status",
            )
        # Een beheerder deactiveren mag de tenant nooit zonder beheerder laten (ADR-039).
        if not data.is_active:
            # Een platformbeheerder zet alleen uit wie de platformrol zelf heeft (brief 2026-10-17).
            await eis_dat_gebruiker_uitgeschakeld_mag_worden(
                db, request, int(current_user.id), int(user.id), int(user.tenant_id)
            )
            voor = await RBACService(db).begin_admin_check(int(user.tenant_id))
            setattr(user, "is_active", data.is_active)
            await RBACService(db).finish_admin_check(int(user.tenant_id), voor)
        else:
            setattr(user, "is_active", data.is_active)

    if data.role_ids is not None:
        if not can_manage_users(current_user, int(user.tenant_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user roles",
            )
        # De rollen van een platformbeheerder (rol OF vlag) wijzigt alleen wie zelf de platformrol heeft.
        await eis_dat_rollen_gewijzigd_mag_worden(
            db, request, int(current_user.id), int(user.id), int(user.tenant_id)
        )
        roles = await _get_tenant_scoped_roles(
            db,
            int(user.tenant_id),
            data.role_ids,
            actor_id=int(current_user.id),
            doel_user_id=int(user.id),
        )
        # Het vervangen van de rollen mag de tenant nooit zonder beheerder laten (ADR-039).
        voor = await RBACService(db).begin_admin_check(int(user.tenant_id))
        user.roles = roles
        await RBACService(db).finish_admin_check(int(user.tenant_id), voor)

    await db.commit()
    await db.refresh(user)

    logger.info("User %s updated by user %s", user_id, current_user.id)
    return UserResponse.model_validate(user)


@users_detail_router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user (soft delete)",
    description="Deactivate a user (soft delete). Admins only.",
    response_class=Response,
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    *,
    request: Request,
) -> None:
    """Soft delete a user by deactivating them."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    if not is_platform_superuser(current_user):
        if current_user.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete users in your own tenant",
            )
        if not can_manage_users(current_user, int(user.tenant_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete users",
            )

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    # Een platformbeheerder verwijdert alleen wie de platformrol zelf heeft (brief 2026-10-17).
    await eis_dat_gebruiker_uitgeschakeld_mag_worden(
        db, request, int(current_user.id), int(user.id), int(user.tenant_id)
    )
    # Een beheerder verwijderen mag de tenant nooit zonder beheerder laten (ADR-039).
    voor = await RBACService(db).begin_admin_check(int(user.tenant_id))
    setattr(user, "is_active", False)
    await RBACService(db).finish_admin_check(int(user.tenant_id), voor)
    await db.commit()

    logger.info("User %s deactivated by user %s", user_id, current_user.id)
