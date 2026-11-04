# orphan:exempt -- imported by user_management/router.py (Laag 2). Gemeten 2026-09-09
# (security-review OP-40): de eerdere toelichting "geregistreerd via auth_admin registry" was
# onjuist -- geen enkele registry importeert dit package, en het pakket zelf is vandaag dode
# code (zie ADR-036 OP-224). Deze exemptie geldt dus op importniveau (voorkomt een orphan-
# melding binnen het package), niet op registratie-niveau.
"""User Management profile sub-router: PUT /me, PATCH /{user_id}/status."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse as AuthUserResponse,
    get_current_user_dependency as get_current_user,
    jwt_handler,
)
from src.core.models.rbac_models import Role, Tenant, User, user_roles

from src.core.utils.best_effort import best_effort

from .dependencies import audit_service, get_db, require_admin, TenantFilterBypass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


class UserUpdate(BaseModel):
    """Schema for updating an existing user."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=100)
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str | None) -> str | None:
        """Validate password strength."""
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserResponseSchema(BaseModel):
    """Schema for user response."""

    id: int
    email: str
    full_name: str | None
    tenant_id: int
    tenant_name: str | None = None
    is_active: bool
    created_at: str | None
    roles: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class UserStatusUpdate(BaseModel):
    """Schema for updating user status."""

    is_active: bool


@router.put(
    "/me",
    response_model=UserResponseSchema,
    summary="Update own profile",
    description="Update the authenticated user's own profile",
)
async def update_my_profile(
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUserResponse = Depends(get_current_user),
) -> UserResponseSchema:
    """Allow an authenticated user to update their own profile."""
    query = select(User).where(User.id == current_user.id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {current_user.id} not found",
        )

    update_data = user_data.model_dump(exclude_unset=True)
    allowed_fields = {"email", "full_name", "password"}
    changes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    for field, value in update_data.items():
        if field not in allowed_fields:
            continue
        if field == "password" and value is not None:
            hashed = await jwt_handler.hash_password(value)
            if user.hashed_password != hashed:
                changes["password"] = "changed"
                user.hashed_password = hashed
        elif hasattr(user, field):
            old_value = getattr(user, field)
            if old_value != value:
                changes[field] = {"old": old_value, "new": value}
                setattr(user, field, value)

    if changes:
        await db.commit()
        await db.refresh(user)

    tenant_query = select(Tenant.name).where(Tenant.id == user.tenant_id)
    tenant_result = await db.execute(tenant_query)
    tenant_name = tenant_result.scalar_one_or_none()

    role_names_query = select(Role.name).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == user.id)
    role_names_result = await db.execute(role_names_query)
    role_names = [row[0] for row in role_names_result.fetchall()]

    return UserResponseSchema(
        id=user.id,
        email=user.email,
        full_name=getattr(user, "full_name", None),
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else None,
        roles=role_names,
    )


@router.patch(
    "/{user_id}/status",
    response_model=UserResponseSchema,
    summary="Toggle user status",
    description="Activate or deactivate a user (admin only)",
)
async def update_user_status(
    user_id: int,
    status_update: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserResponseSchema:
    """Toggle user active status. Requires admin privileges."""
    logger.info(
        "Updating user status: id=%s, is_active=%s by admin: %s",
        user_id,
        status_update.is_active,
        admin_user.email,
    )

    with TenantFilterBypass():
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found",
            )

        old_status = user.is_active
        user.is_active = status_update.is_active

        await db.commit()
        await db.refresh(user)

        async with best_effort("user.status_changed audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=user.tenant_id,
                action="user.status_changed",
                resource=f"user:{user.id}",
                user_id=admin_user.id,
                details={
                    "changes": {"is_active": {"old": old_status, "new": status_update.is_active}}
                },
                session=db,
            )

        logger.info("User status updated: id=%s, is_active=%s", user.id, user.is_active)

        tenant_query = select(Tenant.name).where(Tenant.id == user.tenant_id)
        tenant_result = await db.execute(tenant_query)
        tenant_name = tenant_result.scalar_one_or_none()

        role_names_query = select(Role.name).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == user.id)
        role_names_result = await db.execute(role_names_query)
        role_names = [row[0] for row in role_names_result.fetchall()]

        return UserResponseSchema(
            id=user.id,
            email=user.email,
            full_name=None,
            tenant_id=user.tenant_id,
            tenant_name=tenant_name,
            is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else None,
            roles=role_names,
        )
