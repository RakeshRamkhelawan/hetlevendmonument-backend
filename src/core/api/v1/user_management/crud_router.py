# orphan:exempt -- flat-file migration shim (SP-API-005 Dag 2)
"""User Management CRUD sub-router.

Routes: POST /, GET /, GET /{user_id}, PUT /{user_id}, DELETE /{user_id}, POST /{user_id}/roles
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse as AuthUserResponse,
    get_current_user_dependency as get_current_user,
    jwt_handler,
)
from src.core.models.rbac_models import Role, Tenant, User, user_roles

from src.core.utils.best_effort import best_effort

from .dependencies import audit_service, get_db, RBACService, require_admin, TenantFilterBypass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


# ==================== SCHEMAS ====================


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: EmailStr = Field(..., description="User email address (unique)")
    password: str = Field(
        ..., min_length=8, max_length=100, description="User password (min 8 chars)"
    )
    full_name: str | None = Field(None, max_length=255, description="User full name")
    is_active: bool = Field(True, description="User active status")
    role_ids: list[int] | None = Field(None, description="List of role IDs to assign")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john.doe@example.com",
                "password": "SecurePass123!",
                "full_name": "John Doe",
                "is_active": True,
                "role_ids": [1, 2],
            }
        }
    )


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


class RoleAssignment(BaseModel):
    """Schema for assigning roles to user."""

    role_ids: list[int] = Field(..., description="List of role IDs to assign")


class UserListResponse(BaseModel):
    """Paginated user list response."""

    data: list[UserResponseSchema]
    total: int
    page: int
    per_page: int


# ==================== ENDPOINTS ====================


@router.post(
    "/",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user (admin only)",
)
async def create_user(
    user_data: UserCreate,
    target_tenant_id: int = Query(..., ge=1, description="Tenant ID to create the user in"),
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserResponseSchema:
    """Create a new user. Requires admin privileges. Password will be hashed automatically."""
    logger.info(
        "Creating user: %s in tenant: %s by admin: %s",
        user_data.email,
        target_tenant_id,
        admin_user.email,
    )

    with TenantFilterBypass():
        tenant_query = select(Tenant).where(Tenant.id == target_tenant_id)
        tenant_result = await db.execute(tenant_query)
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with id {target_tenant_id} not found",
            )

        existing_query = select(User).where(User.email == user_data.email)
        existing_result = await db.execute(existing_query)
        existing_user = existing_result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{user_data.email}' already exists",
            )

        hashed_password = await jwt_handler.hash_password(user_data.password)

        new_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            tenant_id=target_tenant_id,
            is_active=user_data.is_active,
        )

        db.add(new_user)
        await db.flush()

        if user_data.role_ids:
            for role_id in user_data.role_ids:
                role_query = select(Role).where(
                    Role.id == role_id, Role.tenant_id == target_tenant_id
                )
                role_result = await db.execute(role_query)
                role = role_result.scalar_one_or_none()

                if not role:
                    logger.warning(
                        "Role %s not found or doesn't belong to tenant %s",
                        role_id,
                        target_tenant_id,
                    )
                    continue

                await db.execute(
                    user_roles.insert().values(
                        user_id=new_user.id, role_id=role_id, tenant_id=new_user.tenant_id
                    )
                )

        await db.commit()
        await db.refresh(new_user)

        role_names_query = (
            select(Role.name).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == new_user.id)
        )
        role_names_result = await db.execute(role_names_query)
        role_names = [row[0] for row in role_names_result.fetchall()]

        async with best_effort("user.created audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=new_user.tenant_id,
                action="user.created",
                resource=f"user:{new_user.id}",
                user_id=admin_user.id,
                details={
                    "changes": {
                        "email": new_user.email,
                        "tenant_id": new_user.tenant_id,
                        "roles": role_names,
                    }
                },
                session=db,
            )

        logger.info("User created successfully: id=%s, email=%s", new_user.id, new_user.email)

        return UserResponseSchema(
            id=new_user.id,
            email=new_user.email,
            full_name=None,
            tenant_id=new_user.tenant_id,
            tenant_name=tenant.name,
            is_active=new_user.is_active,
            created_at=new_user.created_at.isoformat() if new_user.created_at else None,
            roles=role_names,
        )


@router.get(
    "/",
    response_model=UserListResponse,
    summary="List all users",
    description="Get list of all users (admin only, supports filtering by tenant)",
)
async def list_users(
    tenant_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserListResponse:
    """List all users in the system, optionally filtered by tenant. Supports pagination."""
    logger.debug(
        "Listing users: tenant_id=%s, skip=%s, limit=%s by admin: %s",
        tenant_id,
        skip,
        limit,
        admin_user.email,
    )

    with TenantFilterBypass():
        total_query = select(func.count()).select_from(User)
        query = select(User)

        if tenant_id is not None:
            query = query.where(User.tenant_id == tenant_id)
            total_query = total_query.where(User.tenant_id == tenant_id)

        total_result = await db.execute(total_query)
        total = int(total_result.scalar() or 0)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await db.execute(query)
        users = result.scalars().all()

        user_responses: list[UserResponseSchema] = []
        for user in users:
            tenant_query = select(Tenant.name).where(Tenant.id == user.tenant_id)
            tenant_result = await db.execute(tenant_query)
            tenant_name = tenant_result.scalar_one_or_none()

            role_names_query = (
                select(Role.name).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == user.id)
            )
            role_names_result = await db.execute(role_names_query)
            role_names = [row[0] for row in role_names_result.fetchall()]

            user_responses.append(
                UserResponseSchema(
                    id=user.id,
                    email=user.email,
                    full_name=None,
                    tenant_id=user.tenant_id,
                    tenant_name=tenant_name,
                    is_active=user.is_active,
                    created_at=user.created_at.isoformat() if user.created_at else None,
                    roles=role_names,
                )
            )

        page = (skip // limit) + 1 if limit > 0 else 1
        return UserListResponse(
            data=user_responses,
            total=total,
            page=page,
            per_page=limit,
        )


@router.get(
    "/{user_id}",
    response_model=UserResponseSchema,
    summary="Get user details",
    description="Get detailed information about a specific user (admin only)",
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserResponseSchema:
    """Get detailed information about a specific user. Requires admin privileges."""
    logger.debug("Fetching user: id=%s by admin: %s", user_id, admin_user.email)

    with TenantFilterBypass():
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found",
            )

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


@router.put(
    "/{user_id}",
    response_model=UserResponseSchema,
    summary="Update user",
    description="Update user information (admin only)",
)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserResponseSchema:
    """Update user information. Requires admin privileges. Password will be hashed if changed."""
    logger.info("Updating user: id=%s by admin: %s", user_id, admin_user.email)

    with TenantFilterBypass():
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found",
            )

        changes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
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

            async with best_effort("user.updated audit log", db_session=db):
                await audit_service.log_action(
                    tenant_id=user.tenant_id,
                    action="user.updated",
                    resource=f"user:{user.id}",
                    user_id=admin_user.id,
                    details={"changes": changes},
                    session=db,
                )

            logger.info(
                "User updated successfully: id=%s, changes=%s", user.id, list(changes.keys())
            )
        else:
            logger.debug("No changes detected for user: id=%s", user.id)

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


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete user",
    description="Delete a user (admin only, CAUTION: irreversible)",
    response_class=Response,
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUserResponse = Depends(get_current_user),
) -> None:
    """Delete a user. WARNING: This is irreversible! Requires admin privileges."""
    logger.warning("DELETING USER: id=%s by user: %s", user_id, current_user.email)

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users cannot delete their own account",
        )

    user_roles_list = current_user.roles or []
    has_admin_role = any(role in ["admin", "system_admin"] for role in user_roles_list)
    if not has_admin_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required for user management",
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

        user_email = user.email
        user_tenant_id = user.tenant_id

        await db.delete(user)
        await db.commit()

        async with best_effort("user.deleted audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=user_tenant_id,
                action="user.deleted",
                resource=f"user:{user_id}",
                user_id=current_user.id,
                details={"changes": {"email": user_email, "deleted": True}},
                session=db,
            )

        logger.warning("User DELETED: id=%s, email=%s", user_id, user_email)

        return None


@router.post(
    "/{user_id}/roles",
    response_model=UserResponseSchema,
    summary="Assign roles to user",
    description="Assign or update roles for a user (admin only)",
)
async def assign_user_roles(
    user_id: int,
    role_assignment: RoleAssignment,
    db: AsyncSession = Depends(get_db),
    admin_user: AuthUserResponse = Depends(require_admin),
) -> UserResponseSchema:
    """Assign roles to a user. Replaces existing roles with the new list."""
    logger.info(
        "Assigning roles to user: id=%s, role_ids=%s by admin: %s",
        user_id,
        role_assignment.role_ids,
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

        # De schrijfactie gaat door DE dienst, niet langs rauwe SQL hier (ADR-036 OP-258).
        # Tot 2026-09-18 stond hier een tweede implementatie van "rollen toewijzen":
        # `user_roles.delete()` gevolgd door N `insert()`, die `RBACService` nooit aanraakte.
        # Dat was geen lek -- de klantcontrole en de auditregel stonden er -- maar het is de
        # vorm waardoor OP-254 kon ontstaan: daar zat een noodzakelijke stap op EEN van de
        # zes schrijfplekken omdat de andere vijf niet door dezelfde deur gingen.
        # `vervang_rollen` houdt het gedrag identiek, inclusief het overslaan van een rol die
        # niet bij deze klant hoort.
        rbac = RBACService(db)
        role_names = await rbac.vervang_rollen(user_id, role_assignment.role_ids, user.tenant_id)

        async with best_effort("user.roles_updated audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=user.tenant_id,
                action="user.roles_updated",
                resource=f"user:{user.id}",
                user_id=admin_user.id,
                details={"changes": {"roles": role_names}},
                session=db,
            )

        logger.info("User roles updated: id=%s, roles=%s", user.id, role_names)

        tenant_query = select(Tenant.name).where(Tenant.id == user.tenant_id)
        tenant_result = await db.execute(tenant_query)
        tenant_name = tenant_result.scalar_one_or_none()

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
