"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
User Me sub-router (ADR-033 Laag 1).

Routes:
- GET /me
- PUT /me
- PUT /{user_id}/password
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.api.v1.users.schemas import (
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
)
from src.core.api.v1.users.shared import can_manage_users, eis_dat_profiel_gewijzigd_mag_worden
from src.core.api.v1.users.dependencies import (
    get_current_user,
    get_db,
    jwt_handler,
)
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

me_router = APIRouter()


@me_router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the currently authenticated user's information.",
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get the current user's information."""
    return UserResponse.model_validate(current_user)


@me_router.put(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
    description="Update the currently authenticated user's profile.",
)
async def update_current_user_profile(
    data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Update the current user's profile."""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if data.email and data.email != user.email:
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{data.email}' is already in use",
            )
        user.email = data.email

    await db.commit()
    await db.refresh(user)

    logger.info("User %s updated their profile", user.id)
    return UserResponse.model_validate(user)


@me_router.put(
    "/{user_id}/password",
    status_code=status.HTTP_200_OK,
    summary="Change user password",
    description="Change a user's password. Users can change their own, admins can change any in tenant.",
    response_class=Response,
)
async def change_user_password(
    user_id: int,
    data: UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    *,
    request: Request,
) -> None:
    """Change a user's password."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    if current_user.id == user_id:
        if not await jwt_handler.verify_password(
            data.current_password,
            str(user.hashed_password),
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
    elif not can_manage_users(current_user, int(user.tenant_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to change this user's password",
        )
    else:
        # Het wachtwoord van een platformbeheerder zet alleen wie de platformrol zelf heeft (brief
        # 2026-10-19): een gezet wachtwoord is meteen een inlog op dat account.
        await eis_dat_profiel_gewijzigd_mag_worden(
            db, request, int(current_user.id), int(user.id), int(user.tenant_id)
        )

    new_hash = await jwt_handler.hash_password(data.new_password)
    setattr(user, "hashed_password", new_hash)
    await db.commit()

    logger.info("Password changed for user %s by user %s", user_id, current_user.id)
