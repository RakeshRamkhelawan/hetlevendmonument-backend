"""Tenant custom data domain dependencies (ADR-033 Laag 1)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db as get_db  # noqa: F401
from src.core.services.tenant_custom_data_repository import (
    TenantCustomDataRepository as TenantCustomDataRepository,
)  # noqa: F401
from src.core.services.tenant_custom_data_service import (
    TenantCustomDataService as TenantCustomDataService,
)  # noqa: F401


def get_tenant_custom_data_service(
    db: AsyncSession = Depends(get_db),
) -> TenantCustomDataService:
    return TenantCustomDataService(TenantCustomDataRepository(db))
