"""
Pydantic schemas for Tenant CRUD operations.

Canonical location for tenant schemas. Routers may continue to import from
``src.core.api.v1.tenants.schemas`` (backward-compat re-export), but the
service layer imports from here to avoid circular imports via the tenants
package ``__init__.py``.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _valideer_llm_keuze(waarde: dict[str, object] | None) -> dict[str, object] | None:
    """Weiger een taalmodelkeuze die niet bestaat (`deepseek`, `mock`, ...) bij het OPSLAAN.

    Alleen op Create en Update, niet op `TenantBase`: `TenantResponse` erft daarvan en een tenant met
    een oude, ongeldige waarde moet nog leesbaar blijven. Zie `src/core/shared/tenant_llm_keuze.py`.
    """
    if isinstance(waarde, dict):
        from src.core.shared.tenant_llm_keuze import keuze_uit_instellingen

        keuze_uit_instellingen(waarde)  # OnbekendeLLMKeuzeError is een ValueError: pydantic maakt er een 422 van
    return waarde


class TenantBase(BaseModel):
    """Base Tenant schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Tenant name")
    slug: str = Field(..., min_length=1, max_length=100, description="Unique slug for URL")
    domain: str | None = Field(None, max_length=255, description="Custom domain")
    settings: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Tenant-specific settings"
    )  # TODO(TYPE): replace Any with concrete type

    @field_validator("settings", mode="before")
    @classmethod
    def coerce_null_settings(
        cls, v: Any  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Coerce NULL (from direct DB inserts) to empty dict."""
        return v if isinstance(v, dict) else {}

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is URL-friendly. Delegates to canonical validator."""
        from src.core.schemas.validators import validate_slug as canonical_validate_slug

        return canonical_validate_slug(v)


class TenantCreate(TenantBase):
    """Schema for creating a new tenant."""

    @field_validator("slug")
    @classmethod
    def reject_reserved_slug(cls, v: str) -> str:
        """Weiger gereserveerde slugs -- alleen bij AANMAKEN (ADR-036 OP-229).

        Deze toets staat op `TenantCreate` en niet op `TenantBase`, omdat
        `TenantResponse` ook van `TenantBase` erft. Op de basis gezet maakt hij bestaande
        tenants met zo'n slug onleesbaar in plaats van onaanmaakbaar.
        """
        from src.core.schemas.validators import RESERVED_TENANT_SLUGS
        from src.core.schemas.validators import validate_slug as canonical_validate_slug

        return canonical_validate_slug(v, reserved=RESERVED_TENANT_SLUGS)

    @field_validator("settings")
    @classmethod
    def valideer_llm_keuze(cls, v: dict[str, object]) -> dict[str, object]:
        return _valideer_llm_keuze(v) or {}

    max_users: int = Field(default=10, ge=1, description="Maximum number of users")
    max_agents: int = Field(default=50, ge=1, description="Maximum number of agents")
    max_storage_gb: int = Field(default=5, ge=1, description="Maximum storage in GB")
    subscription_tier: str = Field(default="free", description="Subscription tier")
    data_residency: Literal["global", "eu-only"] = Field(
        default="global", description="Data residency: global or EU-only"
    )


class TenantUpdate(BaseModel):
    """Schema for updating an existing tenant."""

    name: str | None = Field(None, min_length=1, max_length=255)
    domain: str | None = Field(None, max_length=255)
    settings: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    @field_validator("settings", mode="before")
    @classmethod
    def coerce_null_settings(
        cls, v: Any  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Coerce NULL to empty dict; keep explicit dicts unchanged."""
        return {} if v is None else v

    @field_validator("settings")
    @classmethod
    def valideer_llm_keuze(cls, v: dict[str, object] | None) -> dict[str, object] | None:
        return _valideer_llm_keuze(v)

    is_active: bool | None = None
    max_users: int | None = Field(None, ge=1)
    max_agents: int | None = Field(None, ge=1)
    max_storage_gb: int | None = Field(None, ge=1)
    subscription_tier: str | None = None
    subscription_status: str | None = None
    data_residency: Literal["global", "eu-only"] | None = Field(
        None, description="Data residency: global or EU-only"
    )
    twin_hard_delete_max_hours: int | None = Field(
        None, ge=1, le=720, description="Hard-delete max hours override"
    )


class TenantResponse(TenantBase):
    """Schema for tenant response."""

    id: int
    is_active: bool
    max_users: int
    max_agents: int
    max_storage_gb: int
    subscription_tier: str
    subscription_status: str
    data_residency: str
    twin_hard_delete_max_hours: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    """Schema for list of tenants with pagination."""

    data: list[TenantResponse]
    total: int
    page: int
    per_page: int


class TenantStats(BaseModel):
    """Statistics for a tenant."""

    user_count: int
    agent_count: int
    storage_used_gb: float
    last_activity: datetime | None = None


class TenantStatusUpdate(BaseModel):
    """Schema for updating tenant activation status."""

    is_active: bool
