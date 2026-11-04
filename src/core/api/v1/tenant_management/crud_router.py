# orphan:exempt reason: actief geimporteerd door middleware/agents/v1/; TODO(SP-VOLGENDE): migreer symbolen naar eigen module
"""
Tenant Management API - RESTful CRUD endpoints for tenant administration

Production-ready tenant management with:
- Full CRUD operations (Create, Read, Update, Delete)
- RBAC authorization (admin only)
- Audit logging
- Multi-tenant isolation
- Input validation
- Comprehensive error handling

Endpoints:
  - POST   /api/v1/tenants/           - Create new tenant (admin only)
  - GET    /api/v1/tenants/           - List all tenants (admin only)
  - GET    /api/v1/tenants/{id}       - Get tenant details (admin only)
  - PUT    /api/v1/tenants/{id}       - Update tenant (admin only)
  - DELETE /api/v1/tenants/{id}       - Delete tenant (admin only)
  - PATCH  /api/v1/tenants/{id}/status - Toggle tenant active status

Security:
  - All endpoints require admin role
  - Audit logging on all mutations
  - Tenant isolation bypassed for admin operations
  - Input sanitization and validation
"""
# orphan:exempt -- legacy shim, superseded by v1/tenants/router.py

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user
from src.core.models.rbac_models import Tenant, with_four_eyes_defaults
from src.core.schemas.validators import RESERVED_TENANT_SLUGS, slug_from_name, validate_slug
from src.core.api.v1.tenant_management.dependencies import (
    audit_service,
    get_db,
    PranaService,
    require_admin,
    TenantFilterBypass,
    zaai_standaardrollen,
)
from src.core.utils.best_effort import best_effort


router = APIRouter()


def _normalize_subscription_tier(value: str) -> str:
    """Accept legacy client labels while storing canonical subscription tiers."""
    aliases = {"professional": "pro"}
    return aliases.get(value, value)


# ==================== SCHEMAS ====================


class TenantCreate(BaseModel):
    """Schema for creating a new tenant"""

    name: str = Field(..., min_length=3, max_length=255, description="Tenant name")
    slug: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        description="URL-friendly slug (auto-generated if not provided)",
    )
    domain: str | None = Field(None, max_length=255, description="Custom domain")
    settings: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Tenant-specific configuration"
    )
    max_users: int = Field(10, ge=1, le=10000, description="Maximum number of users")
    max_agents: int = Field(50, ge=1, le=1000, description="Maximum number of agents")
    max_storage_gb: int = Field(5, ge=1, le=1000, description="Maximum storage in GB")
    subscription_tier: str = Field(
        "free", description="Subscription tier (free, starter, pro, enterprise)"
    )
    industry: str | None = Field(None, max_length=100, description="Industry vertical")
    country_code: str | None = Field(
        None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code"
    )
    primary_locale: str = Field("en_US", description="Primary locale (ISO 639-1)")
    primary_timezone: str = Field("UTC", description="Primary timezone (IANA)")
    primary_currency: str = Field(
        "USD", min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    data_residency: str = Field("global", description="Data residency: global or eu-only")

    @field_validator("slug")
    @classmethod
    def reject_reserved_slug(cls, v: str | None) -> str | None:
        """Valideer en normaliseer de slug, en weiger gereserveerde woorden (OP-229).

        Dit schema had geen enkele slug-validator: `create_tenant` bouwde er rechtstreeks
        een `Tenant`-rij uit, langs `TenantBase.validate_slug` heen. De canonieke validator
        kleint de waarde ook, zodat 'Acme' en 'acme' niet als twee tenants naast elkaar
        kunnen bestaan.
        """
        if v is None:
            return None

        return validate_slug(v, reserved=RESERVED_TENANT_SLUGS)

    @model_validator(mode="after")
    def leid_ontbrekende_slug_af_en_toets_hem(self) -> "TenantCreate":
        """Leid de slug uit de naam af zodra hij ontbreekt, en toets hem dan alsnog.

        `slug` is optioneel op dit schema, en zonder deze stap komt `POST {"name": "Static"}`
        de reserved-toets hierboven nooit tegen: die krijgt `None` te zien en laat door. De
        slug werd dan pas in het ORM-event `_tenant_validate_slug` (rbac_models.py) gemaakt,
        en dat event roept `validate_slug()` aan ZONDER `reserved`. Gemeten 2026-09-28 op
        commit 15638030: `TenantCreate(name='Static').slug` was None en de rij kreeg na
        `before_insert` de slug 'static' -- een gereserveerd top-level URL-segment.

        Waarom hier en niet in dat ORM-event: het event hangt ook aan `before_update`, dus een
        reserved-toets daar breekt het BIJWERKEN van een bestaande tenant die zo'n slug al
        heeft. De weigering hoort bij AANMAKEN, net als de andere twee reserved-toetsen in
        deze codebase.
        """
        if self.slug is None:
            self.slug = validate_slug(slug_from_name(self.name), reserved=RESERVED_TENANT_SLUGS)
        return self

    @field_validator("subscription_tier")
    @classmethod
    def validate_subscription_tier(cls, v: str) -> str:
        """Validate subscription tier is one of allowed values"""
        normalized = _normalize_subscription_tier(v)
        allowed = ["free", "starter", "pro", "enterprise"]
        if normalized not in allowed:
            allowed_input = ["free", "starter", "pro", "professional", "enterprise"]
            raise ValueError(f"subscription_tier must be one of: {', '.join(allowed_input)}")
        return normalized

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corporation",
                "slug": "acme-corp",
                "domain": "acme.example.com",
                "max_users": 50,
                "max_agents": 100,
                "subscription_tier": "pro",
                "industry": "technology",
                "country_code": "US",
                "primary_locale": "en_US",
                "primary_timezone": "America/New_York",
                "primary_currency": "USD",
            }
        }
    )


class TenantUpdate(BaseModel):
    """Schema for updating an existing tenant"""

    name: str | None = Field(None, min_length=3, max_length=255)
    domain: str | None = Field(None, max_length=255)
    settings: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    max_users: int | None = Field(None, ge=1, le=10000)
    max_agents: int | None = Field(None, ge=1, le=1000)
    max_storage_gb: int | None = Field(None, ge=1, le=1000)
    subscription_tier: str | None = None
    subscription_status: str | None = None
    industry: str | None = Field(None, max_length=100)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    primary_locale: str | None = None
    primary_timezone: str | None = None
    primary_currency: str | None = Field(None, min_length=3, max_length=3)
    data_residency: str | None = Field(None, description="Data residency: global or eu-only")
    twin_hard_delete_max_hours: int | None = Field(
        None, ge=1, le=720, description="Hard-delete max hours override"
    )

    @field_validator("subscription_tier")
    @classmethod
    def validate_subscription_tier(cls, v: str | None) -> str | None:
        """Validate subscription tier"""
        if v is not None:
            normalized = _normalize_subscription_tier(v)
            allowed = ["free", "starter", "pro", "enterprise"]
            if normalized not in allowed:
                allowed_input = ["free", "starter", "pro", "professional", "enterprise"]
                raise ValueError(f"subscription_tier must be one of: {', '.join(allowed_input)}")
            return normalized
        return v

    @field_validator("subscription_status")
    @classmethod
    def validate_subscription_status(cls, v: str | None) -> str | None:
        """Validate subscription status"""
        if v is not None:
            allowed = ["active", "suspended", "cancelled", "past_due"]
            if v not in allowed:
                raise ValueError(f"subscription_status must be one of: {', '.join(allowed)}")
        return v


class TenantResponse(BaseModel):
    """Schema for tenant response"""

    id: int
    name: str
    slug: str
    domain: str | None
    settings: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    is_active: bool
    max_users: int
    max_agents: int
    max_storage_gb: int
    subscription_tier: str
    subscription_status: str
    industry: str | None
    country_code: str | None
    primary_locale: str | None
    primary_timezone: str | None
    primary_currency: str | None
    data_residency: str
    twin_hard_delete_max_hours: int | None
    created_at: str
    updated_at: str | None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Acme Corporation",
                "slug": "acme-corp",
                "domain": "acme.example.com",
                "is_active": True,
                "max_users": 50,
                "max_agents": 100,
                "max_storage_gb": 10,
                "subscription_tier": "pro",
                "subscription_status": "active",
                "industry": "technology",
                "country_code": "US",
                "primary_locale": "en_US",
                "primary_timezone": "America/New_York",
                "primary_currency": "USD",
                "created_at": "2026-02-11T10:00:00Z",
                "updated_at": "2026-02-11T12:00:00Z",
            }
        },
    )


class TenantStatusUpdate(BaseModel):
    """Schema for updating tenant status"""

    is_active: bool


class TenantListResponse(BaseModel):
    """Paginated tenant list response."""

    data: list[TenantResponse]
    total: int
    page: int
    per_page: int


# ==================== DEPENDENCY: REQUIRE ADMIN ====================


@router.post(
    "/",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new tenant",
    description="Create a new tenant organization (admin only)",
)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: UserResponse = Depends(require_admin),
) -> TenantResponse:
    """
    Create a new tenant organization.

    Requires admin privileges.
    Audit logged.
    """
    logger.info("Creating tenant: %s by admin: %s", tenant_data.name, admin_user.email)

    # Bypass tenant filtering for admin operations
    with TenantFilterBypass():
        # Check if tenant with same name or slug already exists
        # `tenant_data.slug` is na de model-validator nooit meer None; de `or`-tak blijft als
        # vangnet staan en gebruikt dezelfde afleiding als het ORM-event, zodat de slug die
        # hier op uniciteit wordt getoetst gelijk is aan de slug die straks wordt opgeslagen.
        slug_to_check = tenant_data.slug or slug_from_name(tenant_data.name)
        existing_query = select(Tenant).where(
            (Tenant.name == tenant_data.name) | (Tenant.slug == slug_to_check)
        )
        existing_result = await db.execute(existing_query)
        existing_tenant = existing_result.scalar_one_or_none()

        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with name '{tenant_data.name}' or slug already exists",
            )

        # Create new tenant
        new_tenant = Tenant(
            name=tenant_data.name,
            slug=tenant_data.slug,  # Will be auto-generated if None
            domain=tenant_data.domain,
            # ADR-039: de vier-ogen-standaard, tenzij de aanmaker zelf iets meegaf.
            settings=with_four_eyes_defaults(tenant_data.settings),
            max_users=tenant_data.max_users,
            max_agents=tenant_data.max_agents,
            max_storage_gb=tenant_data.max_storage_gb,
            subscription_tier=tenant_data.subscription_tier,
            industry=tenant_data.industry,
            country_code=tenant_data.country_code,
            primary_locale=tenant_data.primary_locale,
            primary_timezone=tenant_data.primary_timezone,
            primary_currency=tenant_data.primary_currency,
            is_active=True,
            subscription_status="active",
        )

        db.add(new_tenant)
        await db.commit()
        await db.refresh(new_tenant)

        # De standaardrollen horen bij een nieuwe tenant, niet bij de eerste
        # registratie. Sinds ADR-036 OP-185 maakt create_user geen rollen meer aan, dus
        # een tenant zonder rollen zou niemand meer kunnen aanmaken -- gemeten door de
        # Gate-2-reviewer op 2026-09-11, en de eigen meting bij OP-187 liet zien dat
        # tenant 2 in deze database precies in die toestand staat. Zaaien is geen
        # versoepeling: ensure_default_roles maakt uitsluitend de vaste standaardlijst.
        # best_effort omdat de tenant al is gecommit; een mislukt zaaien mag de
        # tenantcreatie niet terugdraaien, maar het moet wel in het log komen.
        async with best_effort("standaardrollen zaaien voor nieuwe tenant", db_session=db):
            await zaai_standaardrollen(db, new_tenant.id)

        async with best_effort("tenant.created audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=new_tenant.id,
                action="tenant.created",
                resource=f"tenant:{new_tenant.id}",
                user_id=admin_user.id,
                details={"changes": {"name": new_tenant.name, "slug": new_tenant.slug}},
                session=db,
            )

        # ADR-021: seed per-department prana budgets (best_effort -- never block creation).
        async with best_effort("prana provision_tenant", db_session=db):
            await PranaService(db).provision_tenant(new_tenant.id)
            await db.commit()

        logger.info("Tenant created successfully: id=%s, name=%s", new_tenant.id, new_tenant.name)

        return TenantResponse(
            id=new_tenant.id,
            name=new_tenant.name,
            slug=new_tenant.slug,
            domain=new_tenant.domain,
            settings=new_tenant.settings or {},
            is_active=new_tenant.is_active,
            max_users=new_tenant.max_users,
            max_agents=new_tenant.max_agents,
            max_storage_gb=new_tenant.max_storage_gb,
            subscription_tier=new_tenant.subscription_tier or "free",
            subscription_status=new_tenant.subscription_status or "active",
            industry=new_tenant.industry,
            country_code=new_tenant.country_code,
            primary_locale=new_tenant.primary_locale,
            primary_timezone=new_tenant.primary_timezone,
            primary_currency=new_tenant.primary_currency,
            data_residency=new_tenant.data_residency,
            twin_hard_delete_max_hours=new_tenant.twin_hard_delete_max_hours,
            created_at=new_tenant.created_at.isoformat() if new_tenant.created_at else "",
            updated_at=new_tenant.updated_at.isoformat() if new_tenant.updated_at else None,
        )


@router.get(
    "/",
    response_model=TenantListResponse,
    summary="List all tenants",
    description="Get list of all tenants (admin only)",
)
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin_user: UserResponse = Depends(require_admin),
) -> TenantListResponse:
    """
    List all tenants in the system.

    Requires admin privileges.
    Supports pagination.
    """
    logger.debug("Listing tenants: skip=%s, limit=%s by admin: %s", skip, limit, admin_user.email)

    # Bypass tenant filtering for admin operations
    with TenantFilterBypass():
        total_result = await db.execute(select(func.count()).select_from(Tenant))
        total = int(total_result.scalar() or 0)
        query = select(Tenant).offset(skip).limit(limit).order_by(Tenant.created_at.desc())
        result = await db.execute(query)
        tenants = result.scalars().all()

        tenant_items = [
            TenantResponse(
                id=t.id,
                name=t.name,
                slug=t.slug,
                domain=t.domain,
                settings=t.settings or {},
                is_active=t.is_active,
                max_users=t.max_users,
                max_agents=t.max_agents,
                max_storage_gb=t.max_storage_gb,
                subscription_tier=t.subscription_tier or "free",
                subscription_status=t.subscription_status or "active",
                industry=t.industry,
                country_code=t.country_code,
                primary_locale=t.primary_locale,
                primary_timezone=t.primary_timezone,
                primary_currency=t.primary_currency,
                data_residency=t.data_residency,
                twin_hard_delete_max_hours=t.twin_hard_delete_max_hours,
                created_at=t.created_at.isoformat() if t.created_at else "",
                updated_at=t.updated_at.isoformat() if t.updated_at else None,
            )
            for t in tenants
        ]
        page = (skip // limit) + 1 if limit > 0 else 1
        return TenantListResponse(
            data=tenant_items,
            total=total,
            page=page,
            per_page=limit,
        )


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get tenant details",
    description="Get detailed information about a specific tenant (admin only)",
)
async def get_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantResponse:
    """
    Get detailed information about a specific tenant.

    Requires admin privileges.
    """
    logger.debug("Fetching tenant: id=%s by user: %s", tenant_id, current_user.email)

    user_roles = current_user.roles or []
    is_admin = any(role in ["admin", "system_admin"] for role in user_roles)

    if not is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only access your own tenant",
        )

    bypass_context = TenantFilterBypass() if is_admin else None
    if bypass_context is not None:
        bypass_context.__enter__()
    try:
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with id {tenant_id} not found",
            )

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            domain=tenant.domain,
            settings=tenant.settings or {},
            is_active=tenant.is_active,
            max_users=tenant.max_users,
            max_agents=tenant.max_agents,
            max_storage_gb=tenant.max_storage_gb,
            subscription_tier=tenant.subscription_tier or "free",
            subscription_status=tenant.subscription_status or "active",
            industry=tenant.industry,
            country_code=tenant.country_code,
            primary_locale=tenant.primary_locale,
            primary_timezone=tenant.primary_timezone,
            primary_currency=tenant.primary_currency,
            data_residency=tenant.data_residency,
            twin_hard_delete_max_hours=tenant.twin_hard_delete_max_hours,
            created_at=tenant.created_at.isoformat() if tenant.created_at else "",
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
        )
    finally:
        if bypass_context is not None:
            bypass_context.__exit__(None, None, None)


@router.put(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update tenant",
    description="Update tenant information (admin only)",
)
async def update_tenant(
    tenant_id: int,
    tenant_data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: UserResponse = Depends(require_admin),
) -> TenantResponse:
    """
    Update tenant information.

    Requires admin privileges.
    Audit logged.
    """
    logger.info("Updating tenant: id=%s by admin: %s", tenant_id, admin_user.email)

    # Bypass tenant filtering for admin operations
    with TenantFilterBypass():
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with id {tenant_id} not found",
            )

        # Track changes for audit log
        changes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Update fields
        update_data = tenant_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(tenant, field):
                old_value = getattr(tenant, field)
                if old_value != value:
                    changes[field] = {"old": old_value, "new": value}
                    setattr(tenant, field, value)

        if changes:
            await db.commit()
            await db.refresh(tenant)

            async with best_effort("tenant.updated audit log", db_session=db):
                await audit_service.log_action(
                    tenant_id=tenant.id,
                    action="tenant.updated",
                    resource=f"tenant:{tenant.id}",
                    user_id=admin_user.id,
                    details={"changes": changes},
                    session=db,
                )

            logger.info(
                "Tenant updated successfully: id=%s, changes=%s",
                tenant.id,
                list(changes.keys()),
            )
        else:
            logger.debug("No changes detected for tenant: id=%s", tenant.id)

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            domain=tenant.domain,
            settings=tenant.settings or {},
            is_active=tenant.is_active,
            max_users=tenant.max_users,
            max_agents=tenant.max_agents,
            max_storage_gb=tenant.max_storage_gb,
            subscription_tier=tenant.subscription_tier or "free",
            subscription_status=tenant.subscription_status or "active",
            industry=tenant.industry,
            country_code=tenant.country_code,
            primary_locale=tenant.primary_locale,
            primary_timezone=tenant.primary_timezone,
            primary_currency=tenant.primary_currency,
            data_residency=tenant.data_residency,
            twin_hard_delete_max_hours=tenant.twin_hard_delete_max_hours,
            created_at=tenant.created_at.isoformat() if tenant.created_at else "",
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
        )


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete tenant",
    description="Soft delete a tenant by deactivating it (admin only)",
    response_class=Response,
)
async def delete_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user: UserResponse = Depends(require_admin),
) -> None:
    """
    Soft delete a tenant by marking it inactive.

    Requires admin privileges.
    Audit logged.
    """
    logger.warning("DEACTIVATING TENANT: id=%s by admin: %s", tenant_id, admin_user.email)

    # Bypass tenant filtering for admin operations
    with TenantFilterBypass():
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with id {tenant_id} not found",
            )

        if not tenant.is_active:
            return None

        tenant_name = tenant.name

        tenant.is_active = False
        await db.commit()

        async with best_effort("tenant.deleted audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=tenant_id,
                action="tenant.deleted",
                resource=f"tenant:{tenant_id}",
                user_id=admin_user.id,
                details={
                    "changes": {
                        "name": tenant_name,
                        "is_active": {"old": True, "new": False},
                    }
                },
                session=db,
            )

        logger.warning("Tenant DEACTIVATED: id=%s, name=%s", tenant_id, tenant_name)

        return None


@router.patch(
    "/{tenant_id}/status",
    response_model=TenantResponse,
    summary="Toggle tenant status",
    description="Activate or deactivate a tenant (admin only)",
)
async def update_tenant_status(
    tenant_id: int,
    status_update: TenantStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: UserResponse = Depends(require_admin),
) -> TenantResponse:
    """
    Toggle tenant active status.

    Requires admin privileges.
    Audit logged.
    """
    logger.info(
        "Updating tenant status: id=%s, is_active=%s by admin: %s",
        tenant_id,
        status_update.is_active,
        admin_user.email,
    )

    # Bypass tenant filtering for admin operations
    with TenantFilterBypass():
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with id {tenant_id} not found",
            )

        old_status = tenant.is_active
        tenant.is_active = status_update.is_active

        await db.commit()
        await db.refresh(tenant)

        async with best_effort("tenant.status_changed audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=tenant.id,
                action="tenant.status_changed",
                resource=f"tenant:{tenant.id}",
                user_id=admin_user.id,
                details={
                    "changes": {"is_active": {"old": old_status, "new": status_update.is_active}}
                },
                session=db,
            )

        logger.info("Tenant status updated: id=%s, is_active=%s", tenant.id, tenant.is_active)

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            domain=tenant.domain,
            settings=tenant.settings or {},
            is_active=tenant.is_active,
            max_users=tenant.max_users,
            max_agents=tenant.max_agents,
            max_storage_gb=tenant.max_storage_gb,
            subscription_tier=tenant.subscription_tier or "free",
            subscription_status=tenant.subscription_status or "active",
            industry=tenant.industry,
            country_code=tenant.country_code,
            primary_locale=tenant.primary_locale,
            primary_timezone=tenant.primary_timezone,
            primary_currency=tenant.primary_currency,
            data_residency=tenant.data_residency,
            twin_hard_delete_max_hours=tenant.twin_hard_delete_max_hours,
            created_at=tenant.created_at.isoformat() if tenant.created_at else "",
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
        )
